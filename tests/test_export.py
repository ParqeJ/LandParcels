import geopandas as gpd
import pytest
from shapely.geometry import box

from landsmaps.config import FIELDS
from landsmaps.export import (REMARK_MISMATCH, REMARK_NOT_FOUND, REMARK_PENDING,
                              parcel_row, rawang, status, to_shp)

INFO = {
    "parcel_seq": "123", "parcel_type": "โฉนดที่ดิน", "utm": "5339 IV 7808-00 (4000)",
    "parcelno": "xxxx19", "rai": "3", "ngan": "2", "wa": "71", "subwa": "9",
    "lands_status": {"obligation": "จำนอง", "freeze": None},
}


def test_rawang_strips_scale():
    assert rawang("5339 IV 7808-00 (4000)") == "5339 IV 7808-00"
    assert rawang(None) == ""


def test_status_joins_non_empty_items():
    assert status(INFO) == "obligation:จำนอง"
    assert status({}) == ""


def test_parcel_row_with_detail():
    row = parcel_row(123, "45", {"123": INFO})
    assert row["Plang"] == "45"
    assert row["Cert_No"] == "xxxx19"
    assert (row["Rai"], row["Ngan"], row["Wa"]) == (3, 2, pytest.approx(71.9))
    assert row["Remark"] == ""
    assert list(row) == FIELDS


@pytest.mark.parametrize("details, remark", [
    ({}, REMARK_PENDING),
    ({"123": None}, REMARK_NOT_FOUND),
    ({"123": {**INFO, "parcel_seq": "999"}}, REMARK_MISMATCH),
])
def test_parcel_row_without_usable_detail(details, remark):
    row = parcel_row(123, "45", details)
    assert row["Remark"] == remark
    assert row["Rai"] is None


def test_to_shp_roundtrip(tmp_path):
    path = tmp_path / "out" / "x.shp"
    to_shp([parcel_row(123, "45", {"123": INFO})], [box(0, 0, 10, 10)], 24047, path)
    back = gpd.read_file(path)
    assert list(back.columns) == FIELDS + ["geometry"]
    assert back.loc[0, "Type_land"] == "โฉนดที่ดิน"
    assert back.crs.to_epsg() == 24047


def test_to_shp_empty_writes_nothing_and_removes_stale_file(tmp_path):
    path = tmp_path / "x.shp"
    to_shp([parcel_row(123, "45", {})], [box(0, 0, 10, 10)], 24047, path)
    assert path.exists()
    out = to_shp([], [], 24047, path)
    assert len(out) == 0
    assert not list(tmp_path.glob("x.*"))
