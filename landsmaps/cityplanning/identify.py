"""ดึงผังเมืองผ่าน /identify แบบซอยกรอบ (quadtree) — ทางสำรองเมื่อ /query ใช้ไม่ได้

บาง service (เช่น PLLU36 ชัยภูมิ) เปิด capability แค่ ``Map,Query`` ไม่มี ``Data``
ทำให้ /query และ /find ตอบ 400 "The requested capability is not supported."
แต่ /identify ยังใช้ได้ และคืน polygon เต็มรูป + attribute ครบ เพียงแต่คืนได้
ไม่เกิน maxRecordCount (เช่น 500) ต่อคำขอ

วิธีดึงให้ครบ:
  1. เริ่มจากกรอบทั้งจังหวัด (หรือกรอบพื้นที่โครงการ) เรียก identify ด้วย envelope
  2. คืนมาเต็มเพดาน (>= maxRecordCount) = อาจตกหล่น -> ผ่ากรอบเป็น 4 ส่วนแล้วถามใหม่
  3. กรอบที่คืนน้อยกว่าเพดาน = ได้ครบทุกรูปที่แตะกรอบนั้นแล้ว
  4. รวมผลทุกกรอบ ตัดตัวซ้ำด้วย FID/OBJECTID (รูปที่คร่อมหลายกรอบจะถูกคืนซ้ำ)

ผลลัพธ์อยู่ในรูป GeoJSON feature (EPSG:4326) แบบเดียวกับ service.fetch_features
จึงส่งต่อให้ export.build ได้ทันที
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable

from pyproj import Transformer
from shapely.geometry import Point, Polygon

from . import service
from .service import CapabilityNotSupported, ServiceError, TokenRequired

PAUSE = 0.3                                 # หน่วงระหว่างคำขอ (วินาที) ถนอมเซิร์ฟเวอร์/เลี่ยง WAF
MAX_DEPTH = 16                              # ผ่ากรอบลึกสุด (1/65536 ของกรอบตั้งต้น ≈ ไม่กี่เมตร)
TILE_RETRY_WAITS = (5, 15, 30, 60, 120)     # ลองกรอบเดิมซ้ำเมื่อเซิร์ฟเวอร์ตอบผิดปกติชั่วคราว
EXTENT_PAD_DEG = 0.001                      # ขยายกรอบตั้งต้นเล็กน้อย กันรูปที่ชิดขอบ
IMAGE_DISPLAY = "2048,2048,96"              # identify บังคับต้องมี (tolerance=0 จึงไม่มีผลกับผล)
ID_FIELDS = ("OBJECTID", "FID", "OBJECTID_1")
NULL_TEXT = frozenset({"Null", "null", ""})
DROP_FIELDS = frozenset({"Shape", "SHAPE"})
# identify คืนช่องตัวเลขที่ว่าง (null) เป็น 0 ขณะที่ /query คืน null -> FAR/BCR = 0 ไม่มีความหมาย
# ทางผัง (สร้างอาคารไม่ได้เลย) จึงถือ 0 เป็น "ไม่ระบุ" ให้ตรงกับผลของ /query
ZERO_AS_NULL = frozenset({"PL_FAR_MAX", "PL_BCR_MAX"})
PROGRESS_EVERY = 25


@dataclass(frozen=True)
class Box:
    """กรอบสี่เหลี่ยมใน lon/lat (EPSG:4326)"""
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    def split(self) -> tuple[Box, Box, Box, Box]:
        mx = (self.xmin + self.xmax) / 2
        my = (self.ymin + self.ymax) / 2
        return (Box(self.xmin, self.ymin, mx, my), Box(mx, self.ymin, self.xmax, my),
                Box(self.xmin, my, mx, self.ymax), Box(mx, my, self.xmax, self.ymax))

    def pad(self, d: float) -> Box:
        return Box(self.xmin - d, self.ymin - d, self.xmax + d, self.ymax + d)

    def as_param(self) -> str:
        return "{:.8f},{:.8f},{:.8f},{:.8f}".format(self.xmin, self.ymin, self.xmax, self.ymax)


@dataclass(frozen=True)
class HarvestReport:
    tiles: int                      # จำนวนคำขอ identify ทั้งหมด
    splits: int                     # จำนวนครั้งที่ผ่ากรอบ
    raw_hits: int                   # ผลรวมก่อนตัดตัวซ้ำ
    features: int                   # จำนวนรูปหลังตัดตัวซ้ำ
    saturated: tuple[Box, ...]      # กรอบที่ผ่าจนสุดแล้วยังเต็มเพดาน (อาจตกหล่น)

    @property
    def complete(self) -> bool:
        return not self.saturated


# ───────────────────────────── กรอบตั้งต้น ─────────────────────────────

def extent_box(extent: tuple[float, float, float, float] | None, wkid: int) -> Box:
    """fullExtent ของ service (CRS ใดก็ได้) -> กรอบ lon/lat ที่ขยายขอบเล็กน้อยแล้ว"""
    if not extent:
        raise ServiceError("service ไม่มี fullExtent -> ใช้ identify ทั้งจังหวัดไม่ได้ (ลองใส่ --area)")
    xmin, ymin, xmax, ymax = extent
    if wkid not in (0, 4326):
        xmin, ymin, xmax, ymax = Transformer.from_crs(wkid, 4326, always_xy=True).transform_bounds(
            xmin, ymin, xmax, ymax)
    return Box(xmin, ymin, xmax, ymax).pad(EXTENT_PAD_DEG)


# ───────────────────────────── Esri JSON -> GeoJSON ─────────────────────────────

def _signed_area(ring: list[list[float]]) -> float:
    """> 0 = วนตามเข็มนาฬิกา (Esri ใช้เป็นวงนอก), <= 0 = ทวนเข็ม (รู)"""
    return sum((x2 - x1) * (y2 + y1) for (x1, y1), (x2, y2) in zip(ring, ring[1:]))


def esri_to_geojson(geom: dict | None) -> dict | None:
    """geometry แบบ Esri (rings) -> GeoJSON Polygon/MultiPolygon

    Esri เก็บวงนอกตามเข็ม รูทวนเข็ม ทุกวงอยู่ใน list เดียว -> จัดรูเข้ากับวงนอกที่ครอบมัน
    """
    rings = [[[float(p[0]), float(p[1])] for p in r]
             for r in (geom or {}).get("rings") or [] if len(r) >= 4]
    if not rings:
        return None
    outers = [r for r in rings if _signed_area(r) > 0]
    holes = [r for r in rings if _signed_area(r) <= 0]
    if not outers:                          # ทิศวงกลับด้านทั้งหมด -> ถือทุกวงเป็นวงนอก
        outers, holes = holes, []

    polygons = [[o] for o in outers]
    shells = [Polygon(o) for o in outers]
    for hole in holes:
        pt = Point(hole[0])
        owner = next((i for i, s in enumerate(shells) if s.covers(pt)), None)
        if owner is None:
            polygons.append([hole])         # ไม่อยู่ในวงนอกใด -> ถือเป็นรูปแยก
        else:
            polygons[owner].append(hole)

    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    return {"type": "MultiPolygon", "coordinates": polygons}


def _is_null(name: str, value) -> bool:
    if isinstance(value, str):
        return value.strip() in NULL_TEXT
    return name in ZERO_AS_NULL and value == 0


def _clean(attrs: dict) -> dict:
    """ตัดฟิลด์ Shape ทิ้ง และแปลงค่าว่างแบบ identify ('Null', FAR/BCR = 0) ให้เป็น None"""
    return {k: (None if _is_null(k, v) else v)
            for k, v in (attrs or {}).items() if k not in DROP_FIELDS}


def _key(props: dict, geometry: dict) -> str:
    for name in ID_FIELDS:
        if props.get(name) is not None:
            return f"{name}:{props[name]}"
    return "geom:" + json.dumps(geometry, sort_keys=True)


def to_feature(result: dict) -> tuple[str, dict] | None:
    """ผล identify 1 รายการ -> (คีย์ตัดซ้ำ, GeoJSON feature) ไม่มีรูป -> None"""
    geometry = esri_to_geojson(result.get("geometry"))
    if geometry is None:
        return None
    props = _clean(result.get("attributes") or {})
    return _key(props, geometry), {"type": "Feature", "properties": props, "geometry": geometry}


# ───────────────────────────── เรียก identify ─────────────────────────────

def identify_tile(map_url: str, layer_id: int, box: Box, token: str | None) -> list[dict]:
    """identify 1 กรอบ คืนผลเฉพาะของชั้นที่ขอ (geometry เป็น lon/lat)"""
    bbox = box.as_param()
    params = service._params(
        token, geometry=bbox, geometryType="esriGeometryEnvelope", sr="4326",
        layers=f"all:{layer_id}", tolerance="0", mapExtent=bbox, imageDisplay=IMAGE_DISPLAY,
        returnGeometry="true", returnFieldName="true", returnUnformattedValues="true",
        returnZ="false", returnM="false")
    data = service._request(f"{map_url}/identify", params)
    return [r for r in data.get("results") or [] if r.get("layerId") == layer_id]


def _with_retry(fetch: Callable[[Box], list[dict]], box: Box,
                sleep: Callable[[float], None]) -> list[dict]:
    """ลองกรอบเดิมซ้ำเมื่อเจอ error ชั่วคราว (WAF/body ว่าง/5xx) — token/capability ไม่ลองซ้ำ"""
    last: ServiceError | None = None
    for wait in (0, *TILE_RETRY_WAITS):
        if wait:
            sleep(wait)
        try:
            return fetch(box)
        except (TokenRequired, CapabilityNotSupported):
            raise
        except ServiceError as e:
            last = e
    raise ServiceError(
        f"identify กรอบ {box.as_param()} ล้มเหลว {len(TILE_RETRY_WAITS) + 1} ครั้ง: {last}")


def harvest(fetch: Callable[[Box], list[dict]], start: Box, *, max_records: int,
            max_depth: int = MAX_DEPTH, pause: float = PAUSE,
            sleep: Callable[[float], None] = time.sleep,
            log: Callable[[str], None] = print) -> tuple[list[dict], HarvestReport]:
    """ไล่ identify แบบ quadtree จนทุกกรอบคืนผลน้อยกว่าเพดาน แล้วรวมผลแบบไม่ซ้ำ"""
    found: dict[str, dict] = {}
    stack: list[tuple[Box, int]] = [(start, 0)]
    tiles = splits = raw = 0
    saturated: list[Box] = []

    while stack:
        box, depth = stack.pop()
        if tiles and pause:
            sleep(pause)
        results = _with_retry(fetch, box, sleep)
        tiles += 1
        raw += len(results)
        for res in results:
            item = to_feature(res)
            if item is not None:
                found.setdefault(item[0], item[1])

        if len(results) >= max_records:
            if depth < max_depth:
                stack.extend((child, depth + 1) for child in box.split())
                splits += 1
            else:
                saturated.append(box)

        if tiles % PROGRESS_EVERY == 0:
            log(f"    identify: {tiles:,} กรอบ | รอคิว {len(stack):,} | ได้ {len(found):,} รูป")

    report = HarvestReport(tiles, splits, raw, len(found), tuple(saturated))
    return list(found.values()), report


def fetch_by_identify(map_url: str, layer_id: int, token: str | None, start: Box, *,
                      max_records: int, log: Callable[[str], None] = print) -> list[dict]:
    """ดึงทุกรูปของชั้น layer_id ที่แตะกรอบ start ผ่าน identify แล้วรายงานความครบ"""
    def fetch(box: Box) -> list[dict]:
        return identify_tile(map_url, layer_id, box, token)

    features, rep = harvest(fetch, start, max_records=max_records, log=log)
    log(f"  identify เสร็จ: {rep.tiles:,} คำขอ | ผ่ากรอบ {rep.splits:,} ครั้ง | "
        f"ผลดิบ {rep.raw_hits:,} -> ไม่ซ้ำ {rep.features:,} รูป")
    if not rep.complete:
        log(f"  [เตือน] มี {len(rep.saturated)} กรอบที่ผ่าจนสุดแล้วยังเต็มเพดาน "
            f"{max_records} -> อาจตกหล่น: " + "; ".join(b.as_param() for b in rep.saturated[:5]))
    return features
