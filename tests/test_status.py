"""สถานะการดึงรายพื้นที่: fetch_parcels เขียน cache/status/<name>.json (ไม่เรียก API จริง)
ฝั่ง dashboard ที่อ่านไฟล์นี้อยู่ใน test_dashboard_status.py"""

import itertools
import json
import os

import geopandas as gpd
import pytest
from shapely.geometry import box

from landsmaps import pipeline
from landsmaps.area import Area
from landsmaps.pipeline import Geometries
from landsmaps.status import pid_alive, read_status, status_file, write_status
from landsmaps.zones import Zone

E, N = 700_000, 1_700_000
DEAD_PID = 2 ** 30            # เลข process ที่ไม่มีอยู่จริง


# ─────────────────────── อ่าน/เขียนไฟล์สถานะ ───────────────────────

def test_write_status_merges_with_previous_fields(tmp_path):
    write_status(tmp_path, "site", state="running", pid=123)
    data = write_status(tmp_path, "site", state="done")

    assert data["state"] == "done" and data["pid"] == 123 and data["name"] == "site"
    assert read_status(status_file(tmp_path, "site")) == data
    assert not list(status_file(tmp_path, "site").parent.glob("*.tmp"))   # ไม่ทิ้งไฟล์ชั่วคราว


def test_status_json_is_plain_and_readable(tmp_path):
    write_status(tmp_path, "t", state="done")
    raw = json.loads(status_file(tmp_path, "t").read_text(encoding="utf-8"))
    assert raw["state"] == "done" and isinstance(raw["updated_at"], float)


@pytest.mark.parametrize("content", [None, "{not json", "[1, 2]"])
def test_read_status_returns_none_for_missing_or_broken_file(tmp_path, content):
    path = tmp_path / "x.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    assert read_status(path) is None


@pytest.mark.parametrize("pid, expected", [(os.getpid(), True), (DEAD_PID, False),
                                           (None, False), (0, False), ("12", False)])
def test_pid_alive(pid, expected):
    assert pid_alive(pid) is expected


# ─────────────────────── run_area เขียนสถานะ ───────────────────────

def fake_area(path, layer=None, name=None) -> Area:
    return Area(name=name or "t", lonlat=box(101.5, 15.4, 101.51, 15.41),
                native=box(E, N, E + 300, N + 100), zone=Zone(47))


def two_parcels() -> Geometries:
    rows = [{"parcel_seq": i, "land_no": str(i), "geometry": box(E + 200 * (i - 1), N, E + 200 * (i - 1) + 100, N + 100)}
            for i in (1, 2)]
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=24047)
    ns3k = gpd.GeoDataFrame({"land_no": []}, geometry=[], crs=24047)
    return Geometries(gdf, ns3k, [])


class SeqAPI:
    """ตอบผลตรงแปลงตามลำดับ 1, 2, ... และเรียก hook ก่อนตอบ (ไว้แอบดูไฟล์สถานะกลางทาง)"""

    def __init__(self, hook=None):
        self.seq = itertools.count(1)
        self.hook = hook

    def parcel_at(self, lat, lon):
        if self.hook:
            self.hook()
        return {"parcel_seq": str(next(self.seq))}


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """ตัด WFS/API ออก -> คืน (ที่ใส่ API ปลอม, tmp_path)"""
    monkeypatch.setattr(pipeline, "SLEEP_SEC", 0)
    monkeypatch.setattr(pipeline, "load_area", fake_area)
    monkeypatch.setattr(pipeline, "fetch_geometries", lambda area, cache_dir: two_parcels())
    monkeypatch.setattr(pipeline, "read_token", lambda: "tok")
    monkeypatch.setattr(pipeline, "check_token", lambda token: "ok")
    slot = {"api": SeqAPI()}
    monkeypatch.setattr(pipeline, "LandsMapsAPI", lambda token: slot["api"])
    return slot, tmp_path


def run(tmp_path, **kw):
    return pipeline.run_area(tmp_path / "areas" / "t.geojson", out_dir=tmp_path / "output",
                             cache_dir=tmp_path / "cache", **kw)


def current(tmp_path) -> dict:
    return read_status(status_file(tmp_path / "cache", "t"))


def test_completed_run_is_marked_done(offline):
    _, tmp_path = offline
    run(tmp_path)

    st = current(tmp_path)
    assert st["state"] == "done"
    assert (st["total"], st["pending"], st["source"], st["pid"]) == (2, 0, "t.geojson", os.getpid())
    assert st["ended_at"] >= st["started_at"]


def test_status_is_running_while_details_are_fetched(offline):
    slot, tmp_path = offline
    seen = []
    slot["api"] = SeqAPI(hook=lambda: seen.append(current(tmp_path)))

    run(tmp_path)

    assert seen[0]["state"] == "running" and seen[0]["total"] == 2
    assert seen[0]["progress"] == {"n": 0, "todo": 2}


def test_quota_hit_is_marked_quota_with_pending_count(offline):
    slot, tmp_path = offline

    class QuotaAPI:
        def parcel_at(self, lat, lon):
            raise pipeline.QuotaExceeded("เกินโควตาค้นหาต่อวัน")
    slot["api"] = QuotaAPI()

    result = run(tmp_path)

    st = current(tmp_path)
    assert result.quota_hit is True
    assert (st["state"], st["pending"], st["total"]) == ("quota", 2, 2)


def test_no_detail_run_leaves_parcels_pending(offline):
    _, tmp_path = offline
    run(tmp_path, fetch_detail=False)
    assert current(tmp_path)["state"] == "partial"


def test_crash_is_marked_error_and_still_raised(offline, monkeypatch):
    _, tmp_path = offline

    def boom(area, cache_dir):
        raise RuntimeError("WFS ล่ม")
    monkeypatch.setattr(pipeline, "fetch_geometries", boom)

    with pytest.raises(RuntimeError):
        run(tmp_path)

    st = current(tmp_path)
    assert st["state"] == "error" and "WFS ล่ม" in st["error"]


def test_status_write_failure_does_not_stop_the_run(offline, monkeypatch):
    _, tmp_path = offline

    def denied(*a, **kw):
        raise PermissionError("ไฟล์ถูกล็อก")
    monkeypatch.setattr(pipeline, "write_status", denied)

    assert run(tmp_path).n_parcel == 2          # เขียนสถานะไม่ได้ ต้องไม่ทำให้การดึงพัง
