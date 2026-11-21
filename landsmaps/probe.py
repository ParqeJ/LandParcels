"""เลือกจุดสำหรับถามรายละเอียดรายแปลง: หลีกส่วนที่แปลงอื่นทับ แล้วเอาจุดที่ลึกที่สุด

รูปแปลงของกรมที่ดินซ้อนทับกันได้ (แปลงรังวัดใหม่ทับแปลงเดิม) ถ้ายิงพิกัดไปตรงบริเวณที่ซ้อนกัน
API จะคืนรายละเอียดของแปลงบนสุด ไม่ใช่แปลงที่เราถาม โมดูลนี้จึงตัดส่วนที่ถูกทับออกก่อน
แล้วเลือกจุดศูนย์กลางวงกลมใหญ่สุดที่บรรจุในส่วนที่เหลือได้ (pole of inaccessibility)
ซึ่งไกลจากขอบทุกด้านมากที่สุด — แก้ทั้งเรื่องซ้อนทับและเรื่องจุดไปติดริมขอบในคราวเดียว

ทั้งโมดูลเป็นเรขาคณิตล้วน ไม่เรียก API และไม่ใช้โควตา
"""

from dataclasses import dataclass
from typing import Iterable, Sequence

import geopandas as gpd
from shapely import STRtree, maximum_inscribed_circle
from shapely.errors import GEOSException
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .config import MAX_PROBE_POINTS, MIN_FREE_AREA_M2, MIN_OVERLAP_M2, SAME_POINT_M

Item = tuple[str, BaseGeometry]     # (parcel_seq, รูปแปลง)


@dataclass(frozen=True)
class Probe:
    """แผนการถาม API ของ 1 แปลง"""

    points: tuple[Point, ...]   # จุดที่จะยิงถาม เรียงตามลำดับ (จุดแรกคือจุดที่ดีที่สุด)
    covered: bool               # True = ถูกแปลงอื่นทับทั้งใบ ยิงไปตรงไหนก็ได้แปลงอื่น
    n_overlap: int              # จำนวนแปลงอื่นที่ทับอยู่


def deep_point(poly: BaseGeometry | None) -> Point | None:
    """จุดศูนย์กลางวงกลมใหญ่สุดที่บรรจุใน poly ได้ (None = คำนวณไม่ได้)"""
    if poly is None or poly.is_empty or poly.area <= 0:
        return None
    try:
        pt = Point(maximum_inscribed_circle(poly).coords[0])
    except (GEOSException, ValueError, IndexError):      # รูปแปลงพิการ -> ให้ผู้เรียกใช้จุดสำรอง
        return None
    return pt if poly.covers(pt) else None


def largest_polygon(geom: BaseGeometry) -> BaseGeometry | None:
    """ชิ้น polygon ที่ใหญ่สุด (ผลของ difference อาจแตกเป็นหลายชิ้นหรือมีเส้นปนมา)"""
    parts = [g for g in getattr(geom, "geoms", [geom])
             if g.geom_type == "Polygon" and not g.is_empty]
    return max(parts, key=lambda g: g.area) if parts else None


def free_part(poly: BaseGeometry, neighbors: Sequence[BaseGeometry]) -> BaseGeometry | None:
    """ส่วนของ poly ที่ไม่มีแปลงอื่นทับ (ชิ้นใหญ่สุด) None = ถูกทับหมดหรือเหลือเล็กเกินไป"""
    if not neighbors:
        return poly
    try:
        rest = poly.difference(unary_union(list(neighbors)))
    except GEOSException:
        return None
    part = largest_polygon(rest)
    return part if part is not None and part.area >= MIN_FREE_AREA_M2 else None


def _unique(points: Iterable[Point | None], poly: BaseGeometry) -> list[Point]:
    """เอาเฉพาะจุดที่อยู่ในแปลงจริง และตัดจุดที่ซ้ำกับจุดก่อนหน้า (ยิงซ้ำที่เดิมเปลืองโควตาเปล่า)"""
    out: list[Point] = []
    for pt in points:
        if pt is None or not poly.covers(pt):
            continue
        if any(pt.distance(seen) < SAME_POINT_M for seen in out):
            continue
        out.append(pt)
    return out


def probe_one(poly: BaseGeometry, neighbors: Sequence[BaseGeometry]) -> Probe:
    """วางแผนจุดถาม API ของแปลงเดียว"""
    fallback = poly.representative_point()          # จุดแบบเดิมของโปรแกรม ใช้เป็นที่พึ่งสุดท้าย
    free = free_part(poly, neighbors)
    if neighbors and free is None:                  # ถูกทับทั้งใบ -> ยิงจุดเดียว ไม่ยิงซ้ำให้เปลืองโควตา
        return Probe((deep_point(poly) or fallback,), True, len(neighbors))

    covering = unary_union(list(neighbors)) if neighbors else None
    ordered = _unique((deep_point(free), deep_point(poly), fallback), poly)
    # จุดที่ตกในแปลงอื่นก็รู้ล่วงหน้าว่าจะได้ผลผิดแปลง ไม่ต้องเสียโควตายิง
    usable = [pt for pt in ordered if covering is None or not covering.intersects(pt)]
    points = usable or ordered or [fallback]
    return Probe(tuple(points[:MAX_PROBE_POINTS]), False, len(neighbors))


def probe_parcels(parcels: gpd.GeoDataFrame,
                  context: Sequence[Item] | None = None) -> dict[str, Probe]:
    """วางแผนจุดถามของทุกแปลงใน `parcels`

    `context` คือรูปแปลงทั้งหมดที่ดึงมา (ก่อน clip ด้วยขอบเขตพื้นที่) ใช้เป็นดัชนีหาเพื่อนบ้าน
    — แปลงที่ทับอยู่อาจอยู่นอกขอบเขตพื้นที่ก็ได้ ไม่ใส่มาจะใช้เฉพาะแปลงใน `parcels` เอง
    """
    source: list[Item] = list(context) if context is not None else [
        (str(row.parcel_seq), row.geometry) for row in parcels.itertuples()]
    items = [(seq, geom) for seq, geom in source if geom is not None and not geom.is_empty]
    tree = STRtree([geom for _, geom in items])

    probes: dict[str, Probe] = {}
    for row in parcels.itertuples():
        seq, poly = str(row.parcel_seq), row.geometry
        if poly is None or poly.is_empty:
            continue
        neighbors = []
        for i in tree.query(poly):
            other_seq, other = items[int(i)]
            if other_seq == seq:
                continue
            try:
                if poly.intersection(other).area > MIN_OVERLAP_M2:
                    neighbors.append(other)
            except GEOSException:                   # รูปแปลงพิการ -> ไม่นับเป็นเพื่อนบ้าน
                continue
        probes[seq] = probe_one(poly, neighbors)
    return probes


def summarize(probes: dict[str, Probe]) -> str:
    """ข้อความสรุปสำหรับ log: ซ้อนทับกี่แปลง เลี่ยงได้กี่แปลง ถูกทับทั้งใบกี่แปลง"""
    overlapped = [p for p in probes.values() if p.n_overlap]
    covered = [p for p in overlapped if p.covered]
    return (f"ซ้อนทับกับแปลงอื่น {len(overlapped):,} แปลง "
            f"(เลี่ยงจุดซ้อนได้ {len(overlapped) - len(covered):,} "
            f"ถูกทับทั้งใบ {len(covered):,})")
