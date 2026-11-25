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

from .. import user_schema
from ..zones import Zone
from . import legend

# ชื่อ field ของ Shapefile ยาวได้ไม่เกิน 10 ตัวอักษร (source of truth: user_schema.CITY_BASE)
FIELDS = list(user_schema.CITY_BASE_FIELDS)
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


def _extra_values(props: dict, native_geom: BaseGeometry, extras) -> dict:
    """ค่าของฟิลด์เสริม (ต่อท้าย 12 ฟิลด์ล็อก) ตาม user_schema — ดู landsmaps/user_schema"""
    code = props.get("PL_USE")
    code_str = str(code).strip() if code not in (None, "") else None
    label, color = legend.label_for(code_str), legend.color_for(code_str)
    return {c.name: user_schema.cast(
        user_schema.resolve_city(c.source, props, native_geom.area, label, color), c.type)
        for c in extras}


def build(features: list[dict], zone: Zone, province_name: str, layer_name: str,
          *, layout=None, extras=None) -> gpd.GeoDataFrame:
    """feature (lon/lat) -> GeoDataFrame ใน EPSG ของ zone (เมตร) พร้อม attribute ผังเมือง

    layout = CityLayout (base ที่ติ๊ก/เปลี่ยนชื่อ + extras) — ถ้าไม่ส่งทั้ง layout และ extras
             จะโหลดจาก schema/user_schema.json (ไม่มีไฟล์ = preset 12 ฟิลด์เดิม)
    extras = (ทางเดิม) ส่ง extras Columns ตรง ๆ โดย base = 12 ฟิลด์เดิม — ใช้โดย test/โค้ดเดิม"""
    if layout is None and extras is None:
        layout = user_schema.load_city_layout()
    if layout is not None:
        base_cols, extra_cols = layout.base, layout.extras
    else:
        base_cols, extra_cols = user_schema._default_city_base(), tuple(extras or ())
    columns = [c.name for c in base_cols] + [c.name for c in extra_cols]

    def project(geom: BaseGeometry) -> BaseGeometry:
        return transform(lambda x, y, z=None: zone.transformer.transform(x, y), geom)

    rows, geoms = [], []
    for feat in features:
        g = _geometry(feat)
        if g is None:
            continue
        native = project(g)
        props = feat.get("properties") or {}
        full = _row(props, native, province_name, layer_name)   # 12 ฟิลด์เดิม คีย์ = FIELDS
        row = {c.name: full.get(c.source) for c in base_cols}    # เลือก/เปลี่ยนชื่อตาม layout
        if extra_cols:
            row.update(_extra_values(props, native, extra_cols))
        rows.append(row)
        geoms.append(native)

    dtypes = {c.name: "Int64" for c in base_cols if c.type == "int"}
    dtypes.update({c.name: ("Int64" if c.type == "int" else "float64")
                   for c in extra_cols if c.type in ("int", "float")})
    gdf = gpd.GeoDataFrame(pd.DataFrame(rows, columns=columns), geometry=geoms,
                           crs=CRS.from_epsg(zone.epsg))
    return gdf.astype(dtypes)[columns + ["geometry"]]


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
