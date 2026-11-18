"""Pruebas de deploy.py, verify.py y restconf_client.py sin tocar el switch.

Se usa un switch falso (FakeClient) para simular las respuestas RESTCONF.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import deploy  # noqa: E402
import restconf_client  # noqa: E402
import verify  # noqa: E402
from payloads import build_items  # noqa: E402

CONFIG = str(ROOT / "config" / "vars.yml")


class FakeClient:
    """Simula el switch: guarda la configuración en un diccionario."""

    def __init__(self, estado=None):
        self.estado = dict(estado or {})
        self.puts = []

    def get(self, path):
        return self.estado.get(path)

    def put(self, path, payload):
        self.puts.append(path)
        code = 204 if path in self.estado else 201
        self.estado[path] = payload
        return code


def switch_configurado():
    import yaml
    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return {path: payload for path, payload in build_items(cfg)}


@pytest.fixture
def fake(monkeypatch):
    """Switch vacío; deploy y verify lo usan en lugar del real."""
    cliente = FakeClient()
    monkeypatch.setattr(deploy, "RestconfClient", lambda *a, **k: cliente)
    monkeypatch.setattr(verify, "RestconfClient", lambda *a, **k: cliente)
    return cliente


def correr_deploy(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["deploy.py", "--config", CONFIG, *args])
    return deploy.main()


# ---------- deploy.py ----------

def test_check_no_modifica_el_switch(fake, monkeypatch, capsys):
    assert correr_deploy(monkeypatch, "--check") == 0
    assert fake.puts == []
    salida = capsys.readouterr().out
    assert salida.count("[CAMBIO]") == 4
    assert "4 cambio(s) pendiente(s)" in salida


def test_deploy_aplica_los_cuatro_recursos(fake, monkeypatch, capsys):
    assert correr_deploy(monkeypatch) == 0
    assert len(fake.puts) == 4
    assert "HTTP 201" in capsys.readouterr().out


def test_deploy_es_idempotente(fake, monkeypatch, capsys):
    correr_deploy(monkeypatch)
    capsys.readouterr()
    correr_deploy(monkeypatch)  # segunda ejecución
    salida = capsys.readouterr().out
    assert len(fake.puts) == 4  # no hubo PUT nuevos
    assert salida.count("[OK]") == 4
    assert "0 cambio(s) aplicado(s)" in salida


def test_deploy_corrige_desviacion(fake, monkeypatch, capsys):
    fake.estado = switch_configurado()
    ruta_location = [p for p in fake.estado if p.endswith("location")][0]
    fake.estado[ruta_location] = {"Cisco-IOS-XE-snmp:location": "OTRO-LUGAR"}
    correr_deploy(monkeypatch)
    assert fake.puts == [ruta_location]
    assert "1 cambio(s) aplicado(s)" in capsys.readouterr().out


# ---------- verify.py ----------

def test_verify_pass_cuando_todo_coincide(fake, monkeypatch, capsys):
    fake.estado = switch_configurado()
    monkeypatch.chdir(ROOT)
    assert verify.main() == 0
    assert capsys.readouterr().out.count("[PASS]") == 4


def test_verify_fail_si_falta_algo(fake, monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    assert verify.main() == 1
    assert "[FAIL]" in capsys.readouterr().out


# ---------- restconf_client.py ----------

class FakeResponse:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self._data = data
        self.text = "x" if data is not None else ""

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def cliente_real(monkeypatch):
    monkeypatch.setenv("SANDBOX_USER", "usuario")
    monkeypatch.setenv("SANDBOX_PASS", "clave")
    return restconf_client.RestconfClient("10.10.20.181")


def test_cliente_arma_url_restconf(cliente_real):
    assert cliente_real.base == "https://10.10.20.181:443/restconf/data"
    assert cliente_real.auth == ("usuario", "clave")


def test_cliente_get_404_devuelve_none(cliente_real, monkeypatch):
    monkeypatch.setattr(restconf_client.requests, "get",
                        lambda *a, **k: FakeResponse(404))
    assert cliente_real.get("algo") is None


def test_cliente_get_devuelve_json(cliente_real, monkeypatch):
    monkeypatch.setattr(restconf_client.requests, "get",
                        lambda *a, **k: FakeResponse(200, {"hostname": "cat9300"}))
    assert cliente_real.get("hostname") == {"hostname": "cat9300"}


def test_cliente_put_devuelve_codigo(cliente_real, monkeypatch):
    monkeypatch.setattr(restconf_client.requests, "put",
                        lambda *a, **k: FakeResponse(201))
    assert cliente_real.put("algo", {}) == 201


def test_cliente_error_http_lanza_excepcion(cliente_real, monkeypatch):
    monkeypatch.setattr(restconf_client.requests, "get",
                        lambda *a, **k: FakeResponse(400))
    with pytest.raises(RuntimeError):
        cliente_real.get("ruta-mala")
