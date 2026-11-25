"""ตั้งค่าผลลัพธ์ parcel: ฟิลด์หลักจาก LandsMaps (ติ๊กออก/เปลี่ยนชื่อได้) + add-on (กรอกเอง) + พรีวิว 1 แปลง"""

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from dashboard import parcel_schema, server  # noqa: E402

BASE = [{"field": f, "source": "x", "type": "str"} for f in ("Rawang", "Rai")] + \
       [{"field": "Remark", "source": "system", "type": "str", "locked": True}]
ADDONS = [{"name": "Owner_Name", "type": "str"}, {"name": "Status", "type": "str"}]


@pytest.fixture
def client(tmp_path, monkeypatch):
    d = tmp_path / "schema"
    d.mkdir()
    cat = {"fixed_fields": ["Rawang", "Rai", "Remark", "Owner_Name", "Status"], "groups": [],
           "base_fields": BASE, "addon_presets": ADDONS}
    (d / "catalog_parcel.json").write_text(json.dumps(cat), encoding="utf-8")
    (d / "catalog_cityplanning.json").write_text(json.dumps({
        "fixed_fields": ["PL_USE", "YEAR"],
        "base_fields": [{"field": "PL_USE", "source": "props.PL_USE", "type": "int"},
                        {"field": "YEAR", "source": "props.YEAR", "type": "str"}],
        "groups": [{"name": "g", "fields": [{"source": "props.NAME", "label": "nm", "type": "str"}]}]}),
        encoding="utf-8")
    monkeypatch.setattr(server, "SCHEMA_DIR", d)
    monkeypatch.setattr(parcel_schema, "CACHE_DIR", tmp_path / "cache")
    c = TestClient(server.app, base_url="http://127.0.0.1:8765")
    c.schema_dir = d
    return c


def save(client, base, addons=(), extras=()):
    body = {"parcel": {"base_fields": [{"field": f, "name": n} for f, n in base],
                       "addon_fields": [{"name": n, "type": t} for n, t in addons],
                       "extra_fields": [{"source": s, "name": n} for s, n in extras]},
            "cityplanning": {"extra_fields": []}}
    return client.post("/api/user-schema", json=body)


def saved(client) -> dict:
    return json.loads((client.schema_dir / "user_schema.json").read_text(encoding="utf-8"))["parcel"]


def test_unticked_base_and_addon_fields_are_simply_left_out(client):
    r = save(client, base=[("Rai", "Rai"), ("Remark", "Remark")], addons=[("Plot", "str")])
    assert r.status_code == 200, r.text
    p = saved(client)
    assert [b["field"] for b in p["base_fields"]] == ["Rai", "Remark"]       # Rawang ติ๊กออกได้
    assert p["addon_fields"] == [{"name": "Plot", "type": "str"}]             # add-on ตั้งเองได้


def test_remark_is_always_kept_even_if_missing(client):
    assert save(client, base=[("Rai", "Rai")]).status_code == 200
    assert [b["field"] for b in saved(client)["base_fields"]] == ["Rai", "Remark"]


def test_base_field_can_be_renamed_and_frees_its_old_name(client):
    r = save(client, base=[("Rai", "AreaRai"), ("Remark", "Remark")], extras=[("info.rai", "Rai")])
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("base, addons, extras, expect", [
    ([("Rai", "Rai")], [("rai", "str")], [], "ซ้ำ"),                       # add-on ชนฟิลด์หลัก (DBF ไม่แยกตัวพิมพ์)
    ([("Rai", "Rai")], [], [("info.a", "RAI")], "ซ้ำ"),                     # ฟิลด์เสริมชนฟิลด์หลัก
    ([("Rai", "Rai")], [("", "str")], [], "ยังไม่ได้ตั้งชื่อ"),
    ([("Rai", "VeryLongName")], [], [], "เกิน 10"),
    ([("Nope", "Nope")], [], [], "ไม่รู้จัก"),
    ([("Rai", "Rai")], [("X", "date")], [], "ชนิด"),
])
def test_bad_layout_is_rejected(client, base, addons, extras, expect):
    r = save(client, base=base, addons=addons, extras=extras)
    assert r.status_code == 400
    assert any(expect in p for p in r.json()["detail"]["problems"]), r.json()
    assert not (client.schema_dir / "user_schema.json").exists()


def test_old_file_without_base_fields_still_uses_the_14_fixed_names(client):
    """ไฟล์รูปแบบเดิม (มีแค่ extra_fields) = preset ANIS POWER -> ชื่อชนฟิลด์เดิมยังถูกปฏิเสธเหมือนก่อน"""
    body = {"parcel": {"extra_fields": [{"source": "info.a", "name": "status"}]}, "cityplanning": {}}
    assert client.post("/api/user-schema", json=body).status_code == 400


# ─────────────────────── พรีวิว: แปลงตัวอย่างจาก cache ───────────────────────

def test_sample_is_null_when_nothing_was_fetched_yet(client):
    r = client.get("/api/schema/sample")
    assert r.status_code == 200 and r.json()["sample"] is None


def test_sample_pairs_detail_record_with_its_wfs_polygon(client, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    lines = [{"seq": "7", "info": {"parcel_seq": "99"}},                    # ชี้ผิดแปลง -> ข้าม
             {"seq": "8", "info": {"parcel_seq": "8", "rai": "2"}}]
    (cache / "site_detail.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    ring = [[0, 0], [10, 0], [10, 5], [0, 0]]
    wfs = {"features": [{"properties": {"parcel_seq": 8, "land_no": "123"},
                         "geometry": {"type": "Polygon", "coordinates": [ring]}}]}
    (cache / "parcel_52394_site.json").write_text(json.dumps(wfs), encoding="utf-8")

    s = client.get("/api/schema/sample").json()["sample"]

    assert (s["seq"], s["land_no"], s["info"]["rai"]) == ("8", "123", "2")
    assert s["geometry"]["coordinates"] == [ring]


# ─────────────── cityplanning: ปลดล็อก base (ติ๊กออก/เปลี่ยนชื่อ) ผ่าน server ───────────────

def _city_save(client, base, extras=()):
    body = {"parcel": {"extra_fields": []},
            "cityplanning": {"base_fields": [{"field": f, "name": n} for f, n in base],
                             "extra_fields": [{"source": s, "name": n} for s, n in extras]}}
    return client.post("/api/user-schema", json=body)


def test_city_save_rename_and_exclude(client):
    r = _city_save(client, [("PL_USE", "LandUse")], extras=[("props.NAME", "PlanNm")])
    assert r.status_code == 200
    saved = json.loads((client.schema_dir / "user_schema.json").read_text(encoding="utf-8"))
    assert saved["cityplanning"]["base_fields"] == [{"field": "PL_USE", "name": "LandUse"}]
    assert saved["cityplanning"]["extra_fields"] == [{"source": "props.NAME", "name": "PlanNm"}]


def test_city_save_rejects_unknown_base_field(client):
    r = _city_save(client, [("NOPE", "X")])
    assert r.status_code == 400
    assert any("ไม่รู้จักฟิลด์หลัก" in p for p in r.json()["detail"]["problems"])


def test_city_save_rejects_extra_colliding_with_renamed_base(client):
    r = _city_save(client, [("PL_USE", "Dup")], extras=[("props.NAME", "Dup")])
    assert r.status_code == 400
