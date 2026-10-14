import zipfile
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import GeometryCollection, LineString, Point

from conftest import BOX_47, BOX_48
from landsmaps.area import _polygons, area_name, find_area_files, load_area


@pytest.mark.parametrize("filename, expected", [
    ("Site A.kmz", "site_a"),
    ("plot.kmz", "plot"),
    ("site.v2.shp", "site_v2"),
    ("แปลง ก.kml", "แปลง_ก"),
])
def test_area_name_from_filename(filename, expected):
    assert area_name(Path(filename)) == expected


def test_find_area_files_keeps_supported_files_and_gdb_folders(tmp_path):
    for name in ["a.kmz", "b.shp", "b.dbf", "c.txt", ".hidden.kml"]:
        (tmp_path / name).write_text("")
    (tmp_path / "d.gdb").mkdir()
    (tmp_path / "e").mkdir()
    assert [p.name for p in find_area_files(tmp_path)] == ["a.kmz", "b.shp", "d.gdb"]


def test_find_area_files_missing_folder_returns_empty(tmp_path):
    assert find_area_files(tmp_path / "nope") == []


def test_load_area_zone_47(area_file):
    area = load_area(area_file(BOX_47))
    assert area.name == "my_site"
    assert area.zone.number == 47 and area.zone.epsg == 24047
    # 0.01° x 0.01° ที่ละติจูด 15° ≈ 1.07 x 1.11 กม.
    assert area.native.area == pytest.approx(1.19e6, rel=0.02)


def test_load_area_zone_48(area_file):
    area = load_area(area_file(BOX_48))
    assert area.zone.number == 48
    assert area.zone.parcel_layer == "V_PARCEL48_LANDNO"


def test_load_area_reprojects_projected_input(area_file):
    utm = gpd.GeoSeries([BOX_47], crs=4326).to_crs(32647).iloc[0]
    area = load_area(area_file(utm, crs=32647))
    assert area.lonlat.bounds == pytest.approx(BOX_47.bounds, abs=1e-6)


def test_load_area_reads_kmz(tmp_path):
    kml = tmp_path / "doc.kml"
    gpd.GeoDataFrame(geometry=[BOX_47], crs=4326).to_file(kml, driver="KML")
    kmz = tmp_path / "Site.kmz"
    with zipfile.ZipFile(kmz, "w") as z:
        z.write(kml, "doc.kml")
    area = load_area(kmz)
    assert area.name == "site"
    assert area.lonlat.bounds == pytest.approx(BOX_47.bounds, abs=1e-6)


@pytest.mark.parametrize("name, expected", [("../x", "x"), ("a/b", "a_b"), ("Site 2", "site_2")])
def test_load_area_sanitizes_custom_name(area_file, name, expected):
    assert load_area(area_file(BOX_47), name=name).name == expected


def test_load_area_without_polygon_raises(area_file):
    with pytest.raises(ValueError, match="ไม่พบ polygon"):
        load_area(area_file(Point(101.5, 15.4)))


def test_load_area_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_area(tmp_path / "nope.kmz")


def test_polygons_ignores_points_and_lines_in_collection():
    gc = GeometryCollection([Point(0, 0), LineString([(0, 0), (1, 1)]), BOX_47])
    assert list(_polygons(gc)) == [BOX_47]
