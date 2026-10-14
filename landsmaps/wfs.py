"""รูปแปลงจาก WFS ของกรมที่ดิน (ไม่จำกัดจำนวน ไม่ต้องล็อกอิน)"""

import json
import os
from pathlib import Path

import geopandas as gpd
import requests
from pyproj import CRS
from shapely.geometry import shape

from .area import Area
from .config import MAX_COUNT, TIMEOUT, WFS
from .zones import Zone

ROMAN = {"I": "1", "II": "2", "III": "3", "IV": "4"}


def wfs_get(layer: str, bbox: tuple, **extra) -> dict:
    params = {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeNames": f"LANDSMAPS:{layer}",
        "bbox": "{:.6f},{:.6f},{:.6f},{:.6f},CRS:84".format(*bbox),
        "outputFormat": "application/json",
        **extra,
    }
    r = requests.get(WFS, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def sheet_code(indlabel: str) -> str | None:
    """"5239 IV 2692-00" -> "52394" (ระวาง 1:50,000 + ส่วน)"""
    parts = indlabel.split()
    if len(parts) < 2 or parts[1] not in ROMAN:
        return None
    return parts[0] + ROMAN[parts[1]]


def find_sheets(zone: Zone, bbox: tuple) -> list[str]:
    """ระวางที่ครอบคลุม bbox จากดัชนีระวางของกรมที่ดิน"""
    sheets = set()
    for layer in zone.index_layers:
        for f in wfs_get(layer, bbox, propertyName="utm1,indlabel1")["features"]:
            code = sheet_code(f["properties"].get("indlabel1") or "")
            if code:
                sheets.add(code)
    if not sheets:
        raise RuntimeError("ไม่พบระวางในกรอบนี้ (อยู่นอกประเทศไทยหรือไม่มีข้อมูลกรมที่ดิน)")
    return sorted(sheets)


def fetch_features(layer: str, sheets: list[str], area: Area, cache_dir: Path, kind: str) -> list:
    """ดึงรูปแปลงทีละระวาง เก็บ cache ไว้ (ถ้ากรอบพื้นที่เปลี่ยน จะดึงใหม่เอง)"""
    bbox = [round(v, 6) for v in area.bbox]
    feats = []
    for sheet in sheets:
        cf = cache_dir / f"{kind}_{sheet}_{area.name}.json"
        data = _read_cache(cf)
        if data is None or data.get("_bbox", bbox) != bbox:
            data = wfs_get(layer, area.bbox, viewparams=f"utmmap:{sheet}", count=MAX_COUNT)
            if len(data["features"]) >= MAX_COUNT:
                raise RuntimeError(f"{kind} {sheet}: ข้อมูลถูกตัดที่ MAX_COUNT -> แบ่งพื้นที่ให้เล็กลง")
            tmp = cf.with_suffix(".tmp")                # เขียนไฟล์ชั่วคราวก่อน หยุดกลางทางไฟล์ cache ไม่เสีย
            tmp.write_text(json.dumps({**data, "_bbox": bbox}))
            os.replace(tmp, cf)
        print(f"  {kind} ระวาง {sheet}: {len(data['features']):,} แปลงใน bbox")
        feats.extend(data["features"])
    return feats


def _read_cache(path: Path) -> dict | None:
    """None = ไม่มี cache หรือไฟล์เสีย (ดึงใหม่)"""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except ValueError:
        print(f"  cache เสีย {path.name} -> ดึงใหม่")
        return None


def clip(feats: list, area: Area) -> gpd.GeoDataFrame:
    """เก็บเฉพาะแปลงที่แตะกรอบพื้นที่ ตัดแปลงซ้ำ (แปลงคร่อมระวาง)"""
    rows, seen = [], set()
    for f in feats:
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        seq = int(f["properties"]["parcel_seq"])
        if g.is_empty or seq in seen or not g.intersects(area.native):
            continue
        seen.add(seq)
        rows.append({"parcel_seq": seq, "land_no": f["properties"].get("land_no"), "geometry": g})
    columns = ["parcel_seq", "land_no", "geometry"]     # กำหนดไว้ เผื่อไม่มีแปลงเลย
    return gpd.GeoDataFrame(rows, columns=columns, geometry="geometry", crs=CRS.from_epsg(area.zone.epsg))
