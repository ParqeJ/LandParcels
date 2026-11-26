"""ขั้นตอนทั้งหมดของ 1 พื้นที่: รูปแปลง (WFS) -> รายละเอียด (API) -> Shapefile"""

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import requests
from shapely.ops import unary_union

from . import user_schema
from .api import (LandsMapsAPI, QuotaExceeded, check_token, is_match, load_detail_cache,
                  open_detail_cache, read_token)
from .area import Area, area_name, load_area, safe_name
from .config import CACHE_DIR, FREE_QUOTA_RANGE, LOG_EVERY, OUTPUT_DIR, SLEEP_SEC, STATUS_EVERY
from .export import (NS3K, REMARK_PENDING, empty_row, ns3k_record, parcel_record, parcel_row,
                     to_shp, to_shp_layout)
from .probe import Item, Probe, probe_parcels, summarize
from .quota import Quota, days_left, quota_for
from .status import write_status
from .wfs import clip, fetch_features, find_sheets, parcel_items

Progress = Callable[[int, int], None]       # (ดึงไปแล้วในรอบนี้, ต้องดึงทั้งหมดในรอบนี้)


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
                  probes: dict[str, Probe], *, refetch: str = "none",
                  quota: Quota = FREE_QUOTA_RANGE,
                  on_progress: Progress | None = None) -> bool:
    """ขั้น 2: รายละเอียดโฉนดทีละแปลง ต่อท้าย cache_file คืน True ถ้าต้องหยุดก่อนครบ (โควตาเต็ม/เน็ตล่ม)"""
    details = load_detail_cache(cache_file)
    todo = [row for row in parcels.itertuples()
            if needs_detail(str(row.parcel_seq), details, refetch)]
    again = sum(1 for row in todo if str(row.parcel_seq) in details)
    note = f" (ในนั้นเป็นการดึงซ้ำด้วยจุดใหม่ {again:,})" if again else ""
    print(f"  รายละเอียด: มี cache {len(details):,} แปลง  เหลือ {len(todo):,} แปลง{note}")
    if todo:
        print(f"    โควตา {quota[0]}-{quota[1]} แปลง/วัน -> ต้องรันอีก {days_left(len(todo), quota)}")
    report = on_progress or (lambda n, total: None)
    report(0, len(todo))
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
                left = len(todo) - i
                print(f"    {i:,}/{len(todo):,}  เหลือ {left:,} แปลง -> {days_left(left, quota)}")
            if i % STATUS_EVERY == 0 or i == len(todo):
                report(i, len(todo))
            time.sleep(SLEEP_SEC)
    return False


def export(geoms: Geometries, area: Area, cache_file: Path, out_dir: Path,
           probes: dict[str, Probe]) -> tuple:
    """ขั้น 3: Shapefile — ตาม user_schema.json ถ้าตั้งค่าไว้ ไม่งั้น 14 ฟิลด์เดิม (preset)
    คืน (parcel_file, ns3k_file, out_parcel, out_ns3k, remark_col) — remark_col ใช้นับแปลงค้าง"""
    details = load_detail_cache(cache_file)
    folder = out_dir / area.name
    suffix = f"epsg{area.zone.epsg}"
    parcel_file = folder / f"{area.name}_parcel_{suffix}.shp"
    ns3k_file = folder / f"{area.name}_ns3k_{suffix}.shp"
    parcels, ns3k = geoms.parcel, geoms.ns3k

    layout = user_schema.load_parcel_layout()
    if layout is None:                                  # preset เดิม — ไม่แตะ output (merge CBD/BNN ปลอดภัย)
        out_parcel = to_shp([parcel_row(r.parcel_seq, r.land_no, details,
                                        covered=is_covered(probes, r.parcel_seq))
                             for r in parcels.itertuples()],
                            parcels.geometry, parcels.crs, parcel_file)
        out_ns3k = to_shp([empty_row(r.land_no, NS3K, "") for r in ns3k.itertuples()],
                          ns3k.geometry, ns3k.crs, ns3k_file)
        return parcel_file, ns3k_file, out_parcel, out_ns3k, "Remark"

    out_parcel = to_shp_layout(
        [user_schema.project_parcel(
            parcel_record(r.parcel_seq, r.land_no, details, covered=is_covered(probes, r.parcel_seq)),
            layout) for r in parcels.itertuples()],
        parcels.geometry, parcels.crs, parcel_file, layout)
    out_ns3k = to_shp_layout(
        [user_schema.project_parcel(ns3k_record(r.land_no), layout) for r in ns3k.itertuples()],
        ns3k.geometry, ns3k.crs, ns3k_file, layout)
    return parcel_file, ns3k_file, out_parcel, out_ns3k, layout.remark_name


def is_covered(probes: dict[str, Probe], parcel_seq) -> bool:
    probe = probes.get(str(parcel_seq))
    return bool(probe and probe.covered)


def run_area(path, *, layer=None, name=None, fetch_detail=True, refetch="none",
             out_dir: Path = OUTPUT_DIR, cache_dir: Path = CACHE_DIR) -> Result:
    """ดึงแปลงที่ดินทั้งหมดในไฟล์ขอบเขต `path` แล้วบันทึกเป็น Shapefile
    (ระหว่างทางเขียนสถานะลง cache/status/<name>.json ให้ dashboard แสดง)"""
    path = Path(path)
    track = _tracker(cache_dir, safe_name(name) if name else area_name(path))
    track(state="running", pid=os.getpid(), source=path.name, started_at=time.time(), ended_at=None,
          total=None, pending=None, progress=None, quota_hit=False, error=None)
    try:
        result = _run_area(path, layer, name, fetch_detail, refetch, out_dir, cache_dir, track)
    except BaseException as e:
        track(state="error" if isinstance(e, Exception) else "cancelled",
              error=str(e)[:500] or type(e).__name__, ended_at=time.time())
        raise
    state = "quota" if result.quota_hit else ("partial" if result.pending else "done")
    track(state=state, total=result.n_parcel, pending=result.pending, quota_hit=result.quota_hit,
          ended_at=time.time())
    return result


def _run_area(path: Path, layer, name, fetch_detail: bool, refetch: str,
              out_dir: Path, cache_dir: Path, track: Callable[..., None]) -> Result:
    area = load_area(path, layer=layer, name=name)
    print(f"[{area.name}] {area.native.area / 1e6:.2f} ตร.กม.  zone {area.zone.number}  "
          f"bbox {tuple(round(v, 5) for v in area.bbox)}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{area.name}_detail.jsonl"

    geoms = fetch_geometries(area, cache_dir)
    track(total=len(geoms.parcel))
    probes = probe_parcels(geoms.parcel, geoms.context)
    if len(geoms.parcel):
        print(f"  จุดค้น: {summarize(probes)}")

    quota_hit = False
    if fetch_detail and len(geoms.parcel):
        token = read_token()
        print(f"  {check_token(token)}")
        quota_hit = fetch_details(geoms.parcel, area, cache_file, LandsMapsAPI(token), probes,
                                  refetch=refetch, quota=quota_for(token),
                                  on_progress=lambda n, todo: track(progress={"n": n, "todo": todo}))

    parcel_file, ns3k_file, out_parcel, out_ns3k, remark_col = export(geoms, area, cache_file, out_dir, probes)
    pending = int((out_parcel[remark_col] == REMARK_PENDING).sum()) if remark_col in out_parcel.columns else 0
    _report(parcel_file, len(out_parcel), f" (ยังไม่มีรายละเอียด {pending:,})" if pending else "")
    _report(ns3k_file, len(out_ns3k))
    return Result(area.name, parcel_file, ns3k_file, len(out_parcel), len(out_ns3k), pending, quota_hit)


def _tracker(cache_dir: Path, name: str) -> Callable[..., None]:
    """เขียนสถานะแบบ best-effort: ไฟล์ถูกล็อก/ดิสก์เต็ม ต้องไม่ทำให้การดึง (ที่เสียโควตา) พัง"""
    warned = False

    def track(**fields: Any) -> None:
        nonlocal warned
        try:
            write_status(cache_dir, name, **fields)
        except OSError as e:
            if not warned:
                print(f"  (เตือน) เขียนไฟล์สถานะไม่ได้: {e} — การดึงยังทำต่อตามปกติ")
                warned = True
    return track


def _report(path: Path, n: int, note: str = "") -> None:
    print(f"  -> {path}: {n:,} แปลง{note}" if n else f"  -> {path.name}: ไม่มีแปลง (ไม่สร้างไฟล์)")
