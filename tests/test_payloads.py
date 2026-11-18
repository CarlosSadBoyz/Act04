import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from payloads import build_items, is_subset  # noqa: E402

with open(ROOT / "config" / "vars.yml", encoding="utf-8") as f:
    CFG = yaml.safe_load(f)


def test_cuatro_recursos():
    assert len(build_items(CFG)) == 4


def test_loopback_ip_en_payload():
    path, body = build_items(CFG)[0]
    assert "Loopback=201" in path
    prim = body["Cisco-IOS-XE-native:Loopback"]["ip"]["address"]["primary"]
    assert prim["address"] == CFG["loopback"]["ip"]


def test_is_subset():
    assert is_subset({"a": 1}, {"a": 1, "b": 2})
    assert not is_subset({"a": 1}, {"a": 2})


def test_rutas_usan_modelo_nativo():
    for path, _ in build_items(CFG):
        assert path.startswith("Cisco-IOS-XE-native:native/")


def test_community_es_solo_lectura():
    path, body = build_items(CFG)[1]
    assert CFG["snmp"]["community"] in path
    assert "RO" in body["Cisco-IOS-XE-snmp:community"]


def test_location_y_contact_en_payload():
    items = build_items(CFG)
    assert items[2][1]["Cisco-IOS-XE-snmp:location"] == CFG["snmp"]["location"]
    assert items[3][1]["Cisco-IOS-XE-snmp:contact"] == CFG["snmp"]["contact"]


def test_is_subset_listas_y_anidados():
    assert is_subset({"x": {"y": 1}}, {"x": {"y": 1, "z": 2}})
    assert not is_subset({"x": {"y": 1}}, {"x": {}})
    assert is_subset({"RO": [None]}, {"RO": [None]})
