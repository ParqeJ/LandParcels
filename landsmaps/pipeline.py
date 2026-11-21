"""ขั้นตอนทั้งหมดของ 1 พื้นที่: รูปแปลง (WFS) -> รายละเอียด (API) -> Shapefile"""

import json
import time
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import requests
from shapely.ops import unary_union

from .api import (LandsMapsAPI, QuotaExceeded, check_token, is_match, load_detail_cache,
                  open_detail_cache, read_token)
from .area import Area, load_area
from .config import CACHE_DIR, LOG_EVERY, OUTPUT_DIR, SLEEP_SEC
from .export import NS3K, REMARK_PENDING, empty_row, parcel_row, to_shp
from .probe import Item, Probe, probe_parcels, summarize
from .wfs import clip, fetch_features, find_sheets, parcel_items


@dataclass(frozen=True)
class Result:
    name: str
    parcel_file: Path
    ns3k_file: Path
    n_parcel: int
    n_ns3k: int
    pending: int            # แปลงที่ยังไม่ได้ดึงรายละเอียด
    quota_hit: bool


@dataclass(frozen=True)
class Geometries:
    """ผลขั้น 1: รูปแปลงที่จะใช้ทำงาน + รูปแปลงทั้งหมดที่ดึงมา (ไว้หาแปลงที่ซ้อนทับ)"""

    parcel: gpd.GeoDataFrame
    ns3k: gpd.GeoDataFrame
    context: list[Item]


def fetch_geometries(area: Area, cache_dir: Path) -> Geometries:
    """ขั้น 1: หาระวาง -> รูปแปลงโฉนด + น.ส.3ก ที่แตะกรอบพื้นที่"""
    sheets = find_sheets(area.zone, area.bbox)
    print(f"  ระวาง: {', '.join(sheets)}")
    layers = {
        "parcel": (area.zone.parcel_layer, sheets),                        # โฉนดใช้ 5 หลัก
        "ns3k": (area.zone.ns3k_layer, sorted({s[:4] for s in sheets})),   # น.ส.3ก ใช้ 4 หลัก
    }
    gdfs, context = {}, []
    for kind, (layer, vps) in layers.items():
        feats = fetch_features(layer, vps, area, cache_dir, kind)
        if kind == "parcel":
            context = parcel_items(feats)       # ได้มาฟรีจากที่ดึงแล้ว ไม่เสียโควตาเพิ่ม
        g = clip(feats, area)
        covered = unary_union(list(g.geometry)).intersection(area.native).area / area.native.area if len(g) else 0
        print(f"  {kind}: {len(g):,} แปลงแตะกรอบ (ครอบคลุม {covered:.0%} ของพื้นที่)")
        gdfs[kind] = g
    return Geometries(gdfs["parcel"], gdfs["ns3k"], context)


def needs_detail(seq: str, details: dict, refetch: str) -> bool:
    """แปลงนี้ต้องยิงถาม API ไหม (ผลใน cache ที่ตรงแปลงแล้ว ไม่ยิงซ้ำให้เปลืองโควตา)"""
    if seq not in details:
        return True
    info = details[seq]
    if is_match(seq, info):
        return False
    kind = "notfound" if not info else "mismatch"
    return refetch in (kind, "both")


def fetch_details(parcels: gpd.GeoDataFrame, area: Area, cache_file: Path, api: LandsMapsAPI,
                  probes: dict[str, Probe], *, refetch: str = "none") -> bool:
    """ขั้น 2: รายละเอียดโฉนดทีละแปลง ต่อท้าย cache_file คืน True ถ้าต้องหยุดก่อนครบ (โควตาเต็ม/เน็ตล่ม)"""
    details = load_detail_cache(cache_file)
    todo = [row for row in parcels.itertuples()
            if needs_detail(str(row.parcel_seq), details, refetch)]
    again = sum(1 for row in todo if str(row.parcel_seq) in details)
    note = f" (ในนั้นเป็นการดึงซ้ำด้วยจุดใหม่ {again:,})" if again else ""
    print(f"  รายละเอียด: มี cache {len(details):,} แปลง  เหลือ {len(todo):,} แปลง{note}")
    t0 = time.time()
    with open_detail_cache(cache_file) as fh:
        for i, row in enumerate(todo, 1):
            seq = str(row.parcel_seq)
            probe = probes.get(seq)
            points = probe.points if probe else (row.geometry.representative_point(),)
            for n, pt in enumerate(points, 1):
                if n > 1:
                    time.sleep(SLEEP_SEC)       # ผลเพิ่งไม่ตรงแปลง -> ลองจุดสำรองถัดไป
                lon, lat = area.zone.transformer.transform(pt.x, pt.y, direction="INVERSE")
                try:
                    info = api.parcel_at(lat, lon)
                except QuotaExceeded as e:
                    print(f"  หยุด: LandsMaps แจ้ง [{e}] -> ดึงได้ {i - 1:,} แปลงในรอบนี้ "
                          "รันใหม่วันพรุ่งนี้ (หรือใส่ token ใหม่) จะทำต่อจากเดิม")
                    return True
                except requests.RequestException as e:   # ลองซ้ำครบแล้วยังไม่ได้ -> หยุดแต่ยังบันทึก Shapefile
                    print(f"  หยุด: ติดต่อ LandsMaps ไม่ได้ ({e}) -> ดึงได้ {i - 1:,} แปลง รันใหม่จะทำต่อจากเดิม")
                    return True
                fh.write(json.dumps({"seq": seq, "info": info, "try": n,
                                     "pt": [round(lon, 8), round(lat, 8)]},
                                    ensure_ascii=False) + "\n")
                fh.flush()
                if is_match(seq, info):
                    break
            if i % LOG_EVERY == 0 or i == len(todo):
                rate = (time.time() - t0) / i
                print(f"    {i:,}/{len(todo):,}  เหลือ ~{rate * (len(todo) - i) / 60:.0f} นาที")
            time.sleep(SLEEP_SEC)
    return False


def export(geoms: Geometries, area: Area, cache_file: Path, out_dir: Path,
           probes: dict[str, Probe]) -> tuple:
    """ขั้น 3: Shapefile 14 attributes"""
    details = load_detail_cache(cache_file)
    folder = out_dir / area.name
    suffix = f"epsg{area.zone.epsg}"
    parcel_file = folder / f"{area.name}_parcel_{suffix}.shp"
    ns3k_file = folder / f"{area.name}_ns3k_{suffix}.shp"

    parcels, ns3k = geoms.parcel, geoms.ns3k
    out_parcel = to_shp([parcel_row(r.parcel_seq, r.land_no, details,
                                    covered=is_covered(probes, r.parcel_seq))
                         for r in parcels.itertuples()],
                        parcels.geometry, parcels.crs, parcel_file)
    out_ns3k = to_shp([empty_row(r.land_no, NS3K, "") for r in ns3k.itertuples()],
                      ns3k.geometry, ns3k.crs, ns3k_file)
    return parcel_file, ns3k_file, out_parcel, out_ns3k


def is_covered(probes: dict[str, Probe], parcel_seq) -> bool:
    probe = probes.get(str(parcel_seq))
    return bool(probe and probe.covered)


def run_area(path, *, layer=None, name=None, fetch_detail=True, refetch="none",
             out_dir: Path = OUTPUT_DIR, cache_dir: Path = CACHE_DIR) -> Result:
    """ดึงแปลงที่ดินทั้งหมดในไฟล์ขอบเขต `path` แล้วบันทึกเป็น Shapefile"""
    area = load_area(Path(path), layer=layer, name=name)
    print(f"[{area.name}] {area.native.area / 1e6:.2f} ตร.กม.  zone {area.zone.number}  "
          f"bbox {tuple(round(v, 5) for v in area.bbox)}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{area.name}_detail.jsonl"

    geoms = fetch_geometries(area, cache_dir)
    probes = probe_parcels(geoms.parcel, geoms.context)
    if len(geoms.parcel):
        print(f"  จุดค้น: {summarize(probes)}")

    quota_hit = False
    if fetch_detail and len(geoms.parcel):
        token = read_token()
        print(f"  {check_token(token)}")
        quota_hit = fetch_details(geoms.parcel, area, cache_file, LandsMapsAPI(token), probes,
                                  refetch=refetch)

    parcel_file, ns3k_file, out_parcel, out_ns3k = export(geoms, area, cache_file, out_dir, probes)
    pending = int((out_parcel["Remark"] == REMARK_PENDING).sum())
    _report(parcel_file, len(out_parcel), f" (ยังไม่มีรายละเอียด {pending:,})" if pending else "")
    _report(ns3k_file, len(out_ns3k))
    return Result(area.name, parcel_file, ns3k_file, len(out_parcel), len(out_ns3k), pending, quota_hit)


def _report(path: Path, n: int, note: str = "") -> None:
    print(f"  -> {path}: {n:,} แปลง{note}" if n else f"  -> {path.name}: ไม่มีแปลง (ไม่สร้างไฟล์)")
