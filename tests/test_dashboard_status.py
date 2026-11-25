"""dashboard /api/status/areas: อ่านสถานะจาก cache/status/*.json หรือนับจาก shapefile เดิม"""

import os
import time

import geopandas as gpd
import pytest
from shapely.geometry import box

from landsmaps.export import REMARK_PENDING
from landsmaps.status import write_status

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from dashboard import server  # noqa: E402
from dashboard import status as dstatus  # noqa: E402

E, N = 700_000, 1_700_000
DEAD_PID = 2 ** 30


@pytest.fixture
def dash(tmp_path, monkeypatch):
    areas, output, cache = tmp_path / "areas", tmp_path / "output", tmp_path / "cache"
    for d in (areas, output, cache):
        d.mkdir()
    monkeypatch.setattr(dstatus, "AREAS_DIR", areas)
    monkeypatch.setattr(dstatus, "OUTPUT_DIR", output)
    monkeypatch.setattr(dstatus, "CACHE_DIR", cache)
    client = TestClient(server.app, base_url="http://127.0.0.1:8765")

    def get() -> dict:
        r = client.get("/api/status/areas")
        assert r.status_code == 200
        return {it["area"]: it for it in r.json()["items"]}
    return areas, output, cache, get


def touch_area(areas, name):
    (areas / name).write_text("{}", encoding="utf-8")


def write_output_shp(output, name, remarks):
    folder = output / name
    folder.mkdir()
    geoms = [box(E + i * 200, N, E + i * 200 + 100, N + 100) for i in range(len(remarks))]
    gpd.GeoDataFrame({"Remark": remarks}, geometry=geoms, crs=24047).to_file(
        folder / f"{name}_parcel_epsg24047.shp", engine="pyogrio")


def test_area_never_fetched_is_new(dash):
    areas, _, _, get = dash
    touch_area(areas, "new site.kmz")
    item = get()["new site.kmz"]
    assert item["state"] == "new" and item["name"] == "new_site"


def test_old_output_without_status_file_is_read_from_shapefile(dash):
    areas, output, _, get = dash
    touch_area(areas, "bnn.kmz")
    touch_area(areas, "cbd.kmz")
    write_output_shp(output, "bnn", ["", REMARK_PENDING, REMARK_PENDING])
    write_output_shp(output, "cbd", ["", ""])

    items = get()
    assert (items["bnn.kmz"]["state"], items["bnn.kmz"]["total"], items["bnn.kmz"]["pending"]) == ("partial", 3, 2)
    assert (items["cbd.kmz"]["state"], items["cbd.kmz"]["pending"]) == ("done", 0)


def test_running_status_with_live_pid_is_running(dash):
    areas, _, cache, get = dash
    touch_area(areas, "t.kmz")
    write_status(cache, "t", state="running", pid=os.getpid(), source="t.kmz",
                 total=50, progress={"n": 10, "todo": 40})

    item = get()["t.kmz"]
    assert item["state"] == "running" and item["progress"] == {"n": 10, "todo": 40}


def test_running_status_with_dead_pid_is_stale(dash):
    areas, _, cache, get = dash
    touch_area(areas, "t.kmz")
    write_status(cache, "t", state="running", pid=DEAD_PID, source="t.kmz")
    assert get()["t.kmz"]["state"] == "stale"


def test_status_is_matched_by_source_file_when_run_with_custom_name(dash):
    areas, _, cache, get = dash
    touch_area(areas, "Site A.kmz")
    write_status(cache, "old", state="done", source="Site A.kmz", total=1, pending=0)
    time.sleep(0.01)
    write_status(cache, "custom", state="quota", source="Site A.kmz", total=9, pending=4)

    item = get()["Site A.kmz"]
    assert (item["name"], item["state"], item["pending"]) == ("custom", "quota", 4)   # เอารอบล่าสุด


def test_status_of_removed_area_is_not_listed(dash):
    """ไฟล์สถานะของพื้นที่ที่ลบออกจาก areas/ ไปแล้ว ไม่โผล่ในตาราง"""
    _, _, cache, get = dash
    write_status(cache, "gone", state="done", source="gone.kmz")
    assert get() == {}
