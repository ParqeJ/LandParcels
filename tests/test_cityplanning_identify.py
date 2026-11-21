"""เทสต์ offline ของการดึงผังเมืองผ่าน /identify ซอยกรอบ + การเลือกวิธีใน pipeline"""

import pytest

from landsmaps.cityplanning import identify, pipeline, service
from landsmaps.cityplanning.identify import Box
from landsmaps.cityplanning.service import (CapabilityNotSupported, LayerRef, ServiceError,
                                       ServiceInfo, TokenRequired)

CW_SQUARE = [[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]       # ตามเข็ม = วงนอกของ Esri
CCW_HOLE = [[2, 2], [4, 2], [4, 4], [2, 4], [2, 2]]            # ทวนเข็ม = รู
CW_FAR = [[20, 0], [20, 5], [25, 5], [25, 0], [20, 0]]


# ───────────────────────────── Esri -> GeoJSON ─────────────────────────────

def test_single_ring_becomes_polygon():
    g = identify.esri_to_geojson({"rings": [CW_SQUARE]})
    assert g["type"] == "Polygon" and len(g["coordinates"]) == 1


def test_hole_is_attached_to_its_outer_ring():
    g = identify.esri_to_geojson({"rings": [CW_SQUARE, CCW_HOLE]})
    assert g["type"] == "Polygon"
    assert len(g["coordinates"]) == 2          # วงนอก + รู


def test_two_outer_rings_become_multipolygon():
    g = identify.esri_to_geojson({"rings": [CW_SQUARE, CCW_HOLE, CW_FAR]})
    assert g["type"] == "MultiPolygon"
    assert [len(p) for p in g["coordinates"]] == [2, 1]


def test_reversed_orientation_still_yields_polygon():
    g = identify.esri_to_geojson({"rings": [list(reversed(CW_SQUARE))]})
    assert g["type"] == "Polygon"


@pytest.mark.parametrize("geom", [None, {}, {"rings": []}, {"rings": [[[0, 0], [1, 1]]]}])
def test_empty_or_degenerate_geometry_is_none(geom):
    assert identify.esri_to_geojson(geom) is None


def test_to_feature_cleans_attributes():
    key, feat = identify.to_feature({
        "attributes": {"FID": 7, "Shape": "Polygon", "NAME": "Null", "PL_FAR_MAX": 0,
                       "PL_BCR_MAX": 0.6, "PL_DENS_H": 0, "PL_USE": 1110},
        "geometry": {"rings": [CW_SQUARE]},
    })
    props = feat["properties"]
    assert key == "FID:7"
    assert "Shape" not in props
    assert props["NAME"] is None                # ข้อความ 'Null' -> None
    assert props["PL_FAR_MAX"] is None          # FAR = 0 -> ไม่ระบุ (ตรงกับ /query)
    assert props["PL_BCR_MAX"] == 0.6
    assert props["PL_DENS_H"] == 0              # ฟิลด์อื่นที่เป็น 0 คงค่าไว้


# ───────────────────────────── Box / extent ─────────────────────────────

def test_box_split_covers_parent_exactly():
    parts = Box(0, 0, 4, 2).split()
    assert len(parts) == 4
    assert min(b.xmin for b in parts) == 0 and max(b.xmax for b in parts) == 4
    assert min(b.ymin for b in parts) == 0 and max(b.ymax for b in parts) == 2
    assert sum((b.xmax - b.xmin) * (b.ymax - b.ymin) for b in parts) == pytest.approx(8)


def test_extent_box_converts_mercator_to_lonlat():
    # fullExtent จริงของ PLLU36 (Web Mercator)
    ext = (11278186.39, 1723628.17, 11406265.79, 1889496.40)
    b = identify.extent_box(ext, 3857)
    assert 101.0 < b.xmin < b.xmax < 102.6
    assert 15.2 < b.ymin < b.ymax < 16.8


def test_extent_box_without_extent_raises():
    with pytest.raises(ServiceError):
        identify.extent_box(None, 3857)


# ───────────────────────────── quadtree harvest ─────────────────────────────

def _grid_results(n: int) -> list[dict]:
    """รูปสี่เหลี่ยม n x n รูป บนตาราง 0..n (หน่วยองศาสมมติ) FID ไม่ซ้ำ"""
    out = []
    for i in range(n):
        for j in range(n):
            ring = [[i, j], [i, j + 1], [i + 1, j + 1], [i + 1, j], [i, j]]
            out.append({"layerId": 6, "attributes": {"FID": i * n + j},
                        "geometry": {"rings": [ring]}, "_box": (i, j, i + 1, j + 1)})
    return out


def _fake_server(results: list[dict], cap: int):
    """identify ปลอม: คืนรูปที่แตะกรอบ แต่ตัดไม่เกินเพดาน cap (เหมือนเซิร์ฟเวอร์จริง)"""
    calls = []

    def fetch(box: Box) -> list[dict]:
        calls.append(box)
        hits = [r for r in results
                if r["_box"][0] <= box.xmax and r["_box"][2] >= box.xmin
                and r["_box"][1] <= box.ymax and r["_box"][3] >= box.ymin]
        return hits[:cap]
    return fetch, calls


def test_harvest_splits_until_complete_and_dedupes():
    results = _grid_results(10)                 # 100 รูป เพดาน 15 -> ต้องผ่ากรอบหลายชั้น
    fetch, calls = _fake_server(results, cap=15)
    feats, rep = identify.harvest(fetch, Box(0, 0, 10, 10), max_records=15,
                                  pause=0, log=lambda m: None)
    assert {f["properties"]["FID"] for f in feats} == set(range(100))
    assert rep.complete and rep.features == 100
    assert rep.splits > 0 and rep.tiles == len(calls)
    assert rep.raw_hits > 100                   # รูปที่คร่อมกรอบถูกคืนซ้ำ แต่ตัดซ้ำแล้ว


def test_harvest_single_request_when_under_cap():
    fetch, calls = _fake_server(_grid_results(3), cap=500)
    feats, rep = identify.harvest(fetch, Box(0, 0, 3, 3), max_records=500,
                                  pause=0, log=lambda m: None)
    assert len(feats) == 9 and len(calls) == 1 and rep.splits == 0


def test_harvest_reports_saturated_tiles_at_max_depth():
    # รูปซ้อนกัน 5 รูปในจุดเดียว เพดาน 3 -> ผ่าเท่าไรก็ยังเต็ม
    stacked = [{"layerId": 6, "attributes": {"FID": k},
                "geometry": {"rings": [CW_SQUARE]}, "_box": (0, 0, 10, 10)} for k in range(5)]
    fetch, _ = _fake_server(stacked, cap=3)
    _, rep = identify.harvest(fetch, Box(0, 0, 10, 10), max_records=3, max_depth=2,
                              pause=0, log=lambda m: None)
    assert not rep.complete and len(rep.saturated) == 16      # 4^2 กรอบล่างสุด


def test_retry_recovers_from_transient_error():
    attempts = []

    def flaky(box):
        attempts.append(box)
        if len(attempts) < 3:
            raise ServiceError("service คืนค่าที่ไม่ใช่ JSON")
        return []
    assert identify._with_retry(flaky, Box(0, 0, 1, 1), sleep=lambda s: None) == []
    assert len(attempts) == 3


@pytest.mark.parametrize("exc", [TokenRequired("x"), CapabilityNotSupported("x")])
def test_retry_does_not_repeat_permanent_errors(exc):
    attempts = []

    def fail(box):
        attempts.append(box)
        raise exc
    with pytest.raises(type(exc)):
        identify._with_retry(fail, Box(0, 0, 1, 1), sleep=lambda s: None)
    assert len(attempts) == 1


# ───────────────────────────── service: error / capability ─────────────────────────────

class _Resp:
    def __init__(self, text):
        self.text = text
        self.encoding = None

    def json(self):
        import json
        return json.loads(self.text)


def test_request_raises_capability_not_supported(monkeypatch):
    body = ('{"error":{"code":400,"message":"Requested operation is not supported by this '
            'service.","details":["The requested capability is not supported."]}}')
    monkeypatch.setattr(service, "_get", lambda url, params: _Resp(body))
    with pytest.raises(CapabilityNotSupported) as e:
        service._request("u", {})
    assert "capability is not supported" in str(e.value)


def test_request_forces_utf8(monkeypatch):
    resp = _Resp('{"ok": 1}')
    monkeypatch.setattr(service, "_get", lambda url, params: resp)
    service._request("u", {})
    assert resp.encoding == "utf-8"


@pytest.mark.parametrize("caps, expected", [
    (("Map", "Query", "Data"), True),
    (("Map", "Query"), False),
    ((), True),                                 # ไม่รู้ capability -> ลอง /query ก่อน
])
def test_supports_data_query(caps, expected):
    info = ServiceInfo("36", 3857, 47, [], capabilities=caps)
    assert info.supports_data_query is expected


# ───────────────────────────── pipeline: เลือกวิธีดึง ─────────────────────────────

def _info(caps):
    return ServiceInfo("36", 3857, 47, [LayerRef(6, "PLLU_3600000")], capabilities=caps,
                       max_record_count=500, extent=(11278186.0, 1723628.0, 11406266.0, 1889497.0),
                       extent_wkid=3857)


@pytest.fixture
def spy(monkeypatch):
    used = []
    monkeypatch.setattr(pipeline, "_fetch_identify", lambda *a, **k: used.append("identify") or ["i"])
    monkeypatch.setattr(pipeline, "_fetch_query", lambda *a, **k: used.append("query") or ["q"])
    return used


def test_auto_uses_identify_when_data_capability_missing(spy):
    out = pipeline._fetch("auto", None, _info(("Map", "Query")), LayerRef(6, "L"), "u", None, None)
    assert out == ["i"] and spy == ["identify"]


def test_auto_uses_query_when_data_capability_present(spy):
    out = pipeline._fetch("auto", None, _info(("Map", "Query", "Data")), LayerRef(6, "L"),
                          "u", None, None)
    assert out == ["q"] and spy == ["query"]


def test_auto_falls_back_when_query_rejected(monkeypatch, spy):
    def reject(*a, **k):
        spy.append("query")
        raise CapabilityNotSupported("400")
    monkeypatch.setattr(pipeline, "_fetch_query", reject)
    out = pipeline._fetch("auto", None, _info(("Map", "Query", "Data")), LayerRef(6, "L"),
                          "u", None, None)
    assert out == ["i"] and spy == ["query", "identify"]


def test_forced_query_does_not_fall_back(monkeypatch, spy):
    def reject(*a, **k):
        raise CapabilityNotSupported("400")
    monkeypatch.setattr(pipeline, "_fetch_query", reject)
    with pytest.raises(CapabilityNotSupported):
        pipeline._fetch("query", None, _info(("Map", "Query", "Data")), LayerRef(6, "L"),
                        "u", None, None)


def test_unknown_method_raises():
    with pytest.raises(ValueError):
        pipeline._fetch("magic", None, _info(()), LayerRef(6, "L"), "u", None, None)
