"""แปลง feature ผังเมือง (GeoJSON EPSG:4326) -> reproject เป็น Indian 1975 UTM -> SHP/GPKG

schema นี้แยกจาก 14 ฟิลด์ของแปลงที่ดิน (landsmaps/export.py) ใช้กับผังเมืองโดยเฉพาะ
CRS ปลายทาง = EPSG 24047/24048 (เมตร) ให้ overlay กับแปลง/buffer ของโปรเจกต์ได้ตรง
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import CRS
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from ..zones import Zone
from . import legend

# ชื่อ field ของ Shapefile ยาวได้ไม่เกิน 10 ตัวอักษร
FIELDS = [
    "PL_USE", "PL_USE_TH", "ZONE_HEX", "FAR_MAX", "BCR_MAX", "DENS_H", "DENS_L",
    "PLAN_NAME", "YEAR", "PROVINCE", "AREA_RAI", "SRC_LAYER",
]
RAI_PER_M2 = 1 / 1600       # 1 ไร่ = 1600 ตร.ม.


def _to_2d(coords):
    """GeoJSON ของ ArcGIS แนบ Z/M (x, y, 0, 0) มาด้วย -> เก็บเฉพาะ x, y"""
    if coords and isinstance(coords[0], (int, float)):
        return [coords[0], coords[1]]
    return [_to_2d(c) for c in coords]


def _geometry(feature: dict) -> BaseGeometry | None:
    geom = feature.get("geometry")
    if not geom or not geom.get("coordinates"):
        return None
    g = shape({"type": geom["type"], "coordinates": _to_2d(geom["coordinates"])})
    if g.is_empty:
        return None
    return g if g.is_valid else g.buffer(0)


def _num(value):
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _row(props: dict, native_geom: BaseGeometry, province_name: str, layer_name: str) -> dict:
    code = props.get("PL_USE")
    code_str = str(code).strip() if code not in (None, "") else None
    return {
        "PL_USE": int(code) if code_str and code_str.lstrip("-").isdigit() else None,
        "PL_USE_TH": legend.label_for(code_str),
        "ZONE_HEX": legend.color_for(code_str),
        "FAR_MAX": _num(props.get("PL_FAR_MAX")),
        "BCR_MAX": _num(props.get("PL_BCR_MAX")),
        "DENS_H": _num(props.get("PL_DENS_H")),
        "DENS_L": _num(props.get("PL_DENS_L")),
        "PLAN_NAME": (props.get("NAME") or "").strip(),
        "YEAR": str(props.get("YEAR") or "").strip(),       # เป็นปี พ.ศ. จาก service
        "PROVINCE": province_name,
        "AREA_RAI": round(native_geom.area * RAI_PER_M2, 2),
        "SRC_LAYER": layer_name,
    }


def build(features: list[dict], zone: Zone, province_name: str, layer_name: str) -> gpd.GeoDataFrame:
    """feature (lon/lat) -> GeoDataFrame ใน EPSG ของ zone (เมตร) พร้อม attribute ผังเมือง"""
    def project(geom: BaseGeometry) -> BaseGeometry:
        return transform(lambda x, y, z=None: zone.transformer.transform(x, y), geom)

    rows, geoms = [], []
    for feat in features:
        g = _geometry(feat)
        if g is None:
            continue
        native = project(g)
        rows.append(_row(feat.get("properties") or {}, native, province_name, layer_name))
        geoms.append(native)

    gdf = gpd.GeoDataFrame(pd.DataFrame(rows, columns=FIELDS), geometry=geoms,
                           crs=CRS.from_epsg(zone.epsg))
    return gdf.astype({"PL_USE": "Int64"})[FIELDS + ["geometry"]]


def save(gdf: gpd.GeoDataFrame, stem: Path, *, formats: tuple[str, ...] = ("shp", "gpkg")) -> list[Path]:
    """บันทึกเป็นไฟล์ตาม formats ที่ขอ คืน path ที่สร้างจริง (ว่าง = ไม่มี feature ไม่สร้างไฟล์)"""
    if not len(gdf):
        return []
    stem.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    if "shp" in formats:
        path = stem.with_suffix(".shp")
        gdf.to_file(path, driver="ESRI Shapefile", encoding="utf-8")
        written.append(path)
    if "gpkg" in formats:
        path = stem.with_suffix(".gpkg")
        gdf.to_file(path, driver="GPKG", layer=stem.name, encoding="utf-8")
        written.append(path)
    return written
