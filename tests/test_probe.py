"""การเลือกจุดถามรายละเอียดรายแปลง — เรขาคณิตล้วน ไม่เรียก API"""

import geopandas as gpd
from shapely.geometry import MultiPolygon, Point, Polygon, box

from landsmaps.config import MAX_PROBE_POINTS
from landsmaps.probe import (deep_point, free_part, largest_polygon, probe_one, probe_parcels,
                             summarize)

# แปลง "หัวโต-หางเรียว": เส้นสแกนกลางรูปตกในหางแคบ ๆ จุดเดิมจึงชิดขอบ
TAIL = Polygon([(0, 0), (100, 0), (100, 40), (54, 40), (50, 120), (46, 120), (46, 40), (0, 40)])


def parcels(*geoms) -> gpd.GeoDataFrame:
    """GeoDataFrame หน้าตาเดียวกับผลของ wfs.clip (parcel_seq เป็นตัวเลขเรียงจาก 1)"""
    rows = [{"parcel_seq": i, "land_no": str(i), "geometry": g} for i, g in enumerate(geoms, 1)]
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=24047)


# ─────────────────────────── จุดลึกสุด ───────────────────────────

def test_deep_point_is_farther_from_edge_than_representative_point():
    deep, old = deep_point(TAIL), TAIL.representative_point()
    assert TAIL.covers(deep)
    assert deep.distance(TAIL.exterior) > old.distance(TAIL.exterior) * 2


def test_deep_point_of_empty_or_missing_geometry_is_none():
    assert deep_point(Polygon()) is None
    assert deep_point(None) is None


def test_largest_polygon_picks_biggest_part():
    multi = MultiPolygon([box(0, 0, 2, 2), box(10, 10, 20, 20)])
    assert largest_polygon(multi).area == 100
    assert largest_polygon(Polygon()) is None


# ─────────────────────────── ส่วนที่ไม่ถูกทับ ───────────────────────────

def test_free_part_without_neighbors_is_the_whole_parcel():
    poly = box(0, 0, 10, 10)
    assert free_part(poly, []) is poly


def test_free_part_is_none_when_covered_completely():
    assert free_part(box(2, 2, 8, 8), [box(0, 0, 10, 10)]) is None


def test_free_part_keeps_the_largest_piece_when_split_in_two():
    """เพื่อนบ้านเป็นแถบพาดกลางแปลง ตัดแปลงเป็น 2 ชิ้น -> เอาชิ้นใหญ่"""
    part = free_part(box(0, 0, 100, 10), [box(20, -1, 30, 11)])
    assert part.area == 700                         # ชิ้นขวา (x 30..100) ใหญ่กว่าชิ้นซ้าย (x 0..20)
    assert part.bounds == (30.0, 0.0, 100.0, 10.0)


# ─────────────────────────── แผนการยิงถาม ───────────────────────────

def test_point_avoids_neighbor_that_covers_the_old_point():
    """แปลงถูกทับครึ่งขวา และจุดเดิม (กลางรูป) ตกในแปลงที่ทับ -> จุดใหม่ต้องหลบไปครึ่งซ้าย"""
    poly, neighbor = box(0, 0, 100, 100), box(40, -10, 150, 110)
    assert neighbor.covers(poly.representative_point())     # ยืนยันว่าของเดิมพลาดจริง

    probe = probe_one(poly, [neighbor])

    assert probe.covered is False
    assert probe.n_overlap == 1
    assert probe.points and not any(neighbor.intersects(pt) for pt in probe.points)
    assert all(poly.covers(pt) for pt in probe.points)


def test_fully_covered_parcel_gets_one_point_only():
    """ถูกทับทั้งใบ -> ยิงจุดเดียว ไม่เสียโควตายิงซ้ำ เพราะยิงตรงไหนก็ได้แปลงอื่น"""
    probe = probe_one(box(2, 2, 8, 8), [box(0, 0, 10, 10)])
    assert probe.covered is True
    assert len(probe.points) == 1


def test_touching_edge_is_not_an_overlap():
    """ขอบชนกันเป็นเรื่องปกติของรูปแปลงกรมที่ดิน ไม่นับว่าซ้อนทับ"""
    probes = probe_parcels(parcels(box(0, 0, 10, 10), box(10, 0, 20, 10)))
    assert [p.n_overlap for p in probes.values()] == [0, 0]


def test_overlap_smaller_than_threshold_is_ignored():
    """ทับกัน 0.5 ตร.ม. (< MIN_OVERLAP_M2) -> ถือว่าแค่คลาดกันเล็กน้อย"""
    probes = probe_parcels(parcels(box(0, 0, 10, 10), box(9.95, 0, 20, 10)))
    assert probes["1"].n_overlap == 0


def test_points_are_capped_and_not_duplicated():
    probe = probe_one(TAIL, [])
    assert 1 <= len(probe.points) <= MAX_PROBE_POINTS
    assert len({(pt.x, pt.y) for pt in probe.points}) == len(probe.points)


def test_single_point_when_candidates_land_on_the_same_spot():
    """สี่เหลี่ยมจัตุรัส: จุดลึกสุดกับจุดเดิมอยู่กลางรูปทั้งคู่ -> เก็บจุดเดียว"""
    probe = probe_one(box(0, 0, 10, 10), [])
    assert len(probe.points) == 1
    assert probe.points[0].equals_exact(Point(5, 5), 0.01)


# ─────────────────────────── ดัชนีเพื่อนบ้าน ───────────────────────────

def test_context_catches_a_neighbor_that_is_outside_the_area():
    """แปลงที่ทับอยู่ถูก clip ออกไปแล้ว (อยู่นอกกรอบพื้นที่) แต่ context ยังรู้จัก"""
    poly, outside = box(0, 0, 100, 100), box(40, -10, 150, 110)
    inside_only = parcels(poly)

    without = probe_parcels(inside_only)
    with_context = probe_parcels(inside_only, [("1", poly), ("99", outside)])

    assert without["1"].n_overlap == 0              # ไม่มี context -> มองไม่เห็นแปลงที่ทับ
    assert with_context["1"].n_overlap == 1
    assert not outside.intersects(with_context["1"].points[0])


def test_identical_geometry_with_another_seq_counts_as_overlap():
    """แปลงรูปเดียวกันเป๊ะ แต่ parcel_seq ต่างกัน (รังวัดใหม่ทับแปลงเดิม) -> ต้องนับว่าทับ"""
    probes = probe_parcels(parcels(box(0, 0, 10, 10), box(0, 0, 10, 10)))
    assert [p.covered for p in probes.values()] == [True, True]


def test_empty_geometry_is_skipped():
    probes = probe_parcels(parcels(box(0, 0, 10, 10), Polygon()))
    assert set(probes) == {"1"}


def test_summarize_counts_overlapped_and_covered():
    probes = probe_parcels(parcels(box(0, 0, 100, 100), box(40, -10, 150, 110),
                                   box(200, 200, 210, 210)))
    text = summarize(probes)
    assert "ซ้อนทับกับแปลงอื่น 2 แปลง" in text
    assert "ถูกทับทั้งใบ 0" in text
