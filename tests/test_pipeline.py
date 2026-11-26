"""การยิงถามรายละเอียดด้วยจุดค้นหลายจุด + กฎว่าแปลงไหนต้องดึง (ไม่เรียก API จริง)"""

import json

import geopandas as gpd
import pytest
from shapely.geometry import box

from landsmaps import pipeline
from landsmaps.api import load_detail_cache
from landsmaps.area import Area
from landsmaps.pipeline import days_left, fetch_details, needs_detail, quota_for
from landsmaps.probe import Probe, probe_parcels
from landsmaps.zones import Zone

# พิกัด UTM 47N แถวภาคกลาง (เมตร) — ค่าอะไรก็ได้ เพราะ FakeAPI ไม่ได้ใช้พิกัดจริง
E, N = 700_000, 1_700_000


def area_47() -> Area:
    """Area ปลอม ใช้แค่ area.zone.transformer ในการแปลงพิกัดกลับเป็น lon/lat"""
    native = box(E, N, E + 100, N + 100)
    return Area(name="t", lonlat=box(101.5, 15.4, 101.51, 15.41), native=native, zone=Zone(47))


def parcels(*geoms) -> gpd.GeoDataFrame:
    rows = [{"parcel_seq": i, "land_no": str(i), "geometry": g} for i, g in enumerate(geoms, 1)]
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=24047)


class FakeAPI:
    """คืนผลตามลำดับที่กำหนด แล้วจำว่าถูกเรียกด้วยพิกัดอะไรไปกี่ครั้ง"""

    def __init__(self, answers: list):
        self.answers = list(answers)
        self.calls = []

    def parcel_at(self, lat, lon):
        self.calls.append((lat, lon))
        return self.answers.pop(0) if self.answers else None


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(pipeline, "SLEEP_SEC", 0)


def records(path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


# ─────────────────────── แปลงไหนต้องยิงถาม ───────────────────────

@pytest.mark.parametrize("details, refetch, expected", [
    ({}, "none", True),                                     # ไม่มีใน cache -> ต้องดึง
    ({"1": {"parcel_seq": "1"}}, "both", False),            # ได้ผลตรงแปลงแล้ว -> ไม่ดึงซ้ำ
    ({"1": None}, "none", False),                           # ไม่พบ แต่ไม่สั่งดึงซ้ำ
    ({"1": None}, "notfound", True),
    ({"1": None}, "mismatch", False),
    ({"1": {"parcel_seq": "99"}}, "none", False),           # ชี้ผิดแปลง แต่ไม่สั่งดึงซ้ำ
    ({"1": {"parcel_seq": "99"}}, "mismatch", True),
    ({"1": {"parcel_seq": "99"}}, "both", True),
])
def test_needs_detail(details, refetch, expected):
    assert needs_detail("1", details, refetch) is expected


# ─────────────────────── ยิงจุดสำรองเมื่อผลไม่ตรงแปลง ───────────────────────

def test_second_point_is_tried_when_first_answer_points_elsewhere(tmp_path):
    """จุดแรกได้แปลงอื่น -> ยิงจุดที่สอง ได้ผลตรงแปลง แล้วหยุด"""
    cache = tmp_path / "t_detail.jsonl"
    gdf = parcels(box(E, N, E + 100, N + 100))
    probes = {"1": Probe(points=(gdf.geometry[0].representative_point(),
                                 gdf.geometry[0].centroid), covered=False, n_overlap=1)}
    api = FakeAPI([{"parcel_seq": "99"}, {"parcel_seq": "1", "rai": "2"}])

    stopped = fetch_details(gdf, area_47(), cache, api, probes)

    assert stopped is False
    assert len(api.calls) == 2
    rows = records(cache)
    assert [r["try"] for r in rows] == [1, 2]
    assert [r["info"]["parcel_seq"] for r in rows] == ["99", "1"]
    assert load_detail_cache(cache) == {"1": {"parcel_seq": "1", "rai": "2"}}   # เก็บผลที่ตรงแปลง


def test_matching_first_answer_does_not_spend_a_second_call(tmp_path):
    cache = tmp_path / "t_detail.jsonl"
    gdf = parcels(box(E, N, E + 100, N + 100))
    probes = {"1": Probe(points=(gdf.geometry[0].centroid, gdf.geometry[0].representative_point()),
                         covered=False, n_overlap=0)}
    api = FakeAPI([{"parcel_seq": "1"}])

    fetch_details(gdf, area_47(), cache, api, probes)

    assert len(api.calls) == 1
    assert [r["try"] for r in records(cache)] == [1]


def test_covered_parcel_is_asked_once_even_though_answer_is_wrong(tmp_path):
    """ถูกทับทั้งใบ: probe ให้จุดเดียว -> ยิงครั้งเดียว ไม่วนยิงจนเปลืองโควตา"""
    cache = tmp_path / "t_detail.jsonl"
    gdf = parcels(box(E + 20, N + 20, E + 80, N + 80))
    probes = probe_parcels(gdf, [("1", gdf.geometry[0]), ("9", box(E, N, E + 100, N + 100))])
    api = FakeAPI([{"parcel_seq": "9"}])

    fetch_details(gdf, area_47(), cache, api, probes)

    assert probes["1"].covered is True
    assert len(api.calls) == 1


def test_query_point_is_written_as_lonlat_in_thailand(tmp_path):
    """พิกัดที่บันทึกต้องเป็น [lon, lat] องศา ไม่ใช่เมตร และต้องตรงกับที่ส่งให้ API"""
    cache = tmp_path / "t_detail.jsonl"
    gdf = parcels(box(E, N, E + 100, N + 100))
    api = FakeAPI([{"parcel_seq": "1"}])

    fetch_details(gdf, area_47(), cache, api, probe_parcels(gdf))

    lon, lat = records(cache)[0]["pt"]
    assert 97 < lon < 106 and 5 < lat < 21
    lat_called, lon_called = api.calls[0]
    assert (lon_called, lat_called) == pytest.approx((lon, lat), abs=1e-6)


def test_cached_parcel_is_skipped_and_quota_hit_stops_the_run(tmp_path):
    cache = tmp_path / "t_detail.jsonl"
    cache.write_text(json.dumps({"seq": "1", "info": {"parcel_seq": "1"}}) + "\n", encoding="utf-8")
    gdf = parcels(box(E, N, E + 100, N + 100), box(E + 200, N, E + 300, N + 100))

    class QuotaAPI:
        def parcel_at(self, lat, lon):
            raise pipeline.QuotaExceeded("เกินโควตาค้นหาต่อวัน")

    stopped = fetch_details(gdf, area_47(), cache, QuotaAPI(), probe_parcels(gdf))

    assert stopped is True
    assert len(records(cache)) == 1                 # แปลงที่ 1 ข้ามไป แปลงที่ 2 ยิงไม่สำเร็จ


# ─────────── ประมาณการเป็น "จำนวนวัน" ไม่ใช่นาที (ตัวคุมคือโควตาต่อวัน) ───────────

@pytest.mark.parametrize("remaining, quota, expected", [
    (1_340, (200, 400), "~4-7 วัน"),     # 1340/400 = 4 วันเร็วสุด, 1340/200 = 7 วันช้าสุด
    (73, (20, 40), "~2-4 วัน"),
    (34, (200, 400), "~1 วัน"),          # น้อยกว่าโควตาขั้นต่ำ -> วันเดียวจบทั้งสองกรณี
    (1, (20, 40), "~1 วัน"),
    (0, (200, 400), "ครบแล้ว"),
])
def test_days_left_counts_days_from_daily_quota(remaining, quota, expected):
    assert days_left(remaining, quota) == expected


def test_quota_for_uses_account_quota_only_when_there_is_a_token():
    assert quota_for("eyJhbGciOi...") == (200, 400)
    assert quota_for("") == (20, 40)


def test_progress_log_reports_days_not_minutes(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(pipeline, "LOG_EVERY", 1)
    cache = tmp_path / "t_detail.jsonl"
    gdf = parcels(box(E, N, E + 100, N + 100), box(E + 200, N, E + 300, N + 100))
    api = FakeAPI([{"parcel_seq": "1"}, {"parcel_seq": "2"}])

    fetch_details(gdf, area_47(), cache, api, probe_parcels(gdf), quota=(20, 40))

    out = capsys.readouterr().out
    assert "นาที" not in out
    assert "โควตา 20-40 แปลง/วัน -> ต้องรันอีก ~1 วัน" in out
    assert "1/2  เหลือ 1 แปลง -> ~1 วัน" in out
    assert "2/2  เหลือ 0 แปลง -> ครบแล้ว" in out
