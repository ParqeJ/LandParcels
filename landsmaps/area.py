"""อ่านไฟล์ขอบเขตพื้นที่ (KMZ, KML, SHP, GPKG, GeoJSON, GDB) -> polygon"""

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pyogrio
from shapely import force_2d
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

from .config import AREA_SUFFIXES
from .zones import ZONE_SPLIT_LON, Zone, zone_for_lon


@dataclass(frozen=True)
class Area:
    name: str               # ใช้ตั้งชื่อไฟล์ผลลัพธ์/cache
    lonlat: BaseGeometry    # WGS84
    native: BaseGeometry    # EPSG ของ zone (หน่วยเมตร)
    zone: Zone

    @property
    def bbox(self) -> tuple:
        return self.lonlat.bounds


def safe_name(text: str) -> str:
    """ชื่อที่ใช้เป็นชื่อไฟล์/โฟลเดอร์ได้ปลอดภัย "Site A" -> "site_a" (ภาษาไทยใช้ได้)"""
    name = re.sub(r'[\s<>:"/\\|?*.]+', "_", text).strip("_").lower()
    if not name:
        raise ValueError(f"ใช้ '{text}' เป็นชื่อพื้นที่ไม่ได้ -> ใช้ --name")
    return name


def area_name(path: Path) -> str:
    """"Site A.kmz" -> "site_a" """
    return safe_name(path.stem)


def is_area_file(path: Path) -> bool:
    if path.name.startswith("."):
        return False
    if path.is_dir():
        return path.suffix.lower() == ".gdb"
    return path.suffix.lower() in AREA_SUFFIXES


def find_area_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if is_area_file(p))


def _source(path: Path) -> str:
    """KMZ = zip ที่มี .kml อยู่ข้างใน -> อ่านผ่าน /vsizip/ ของ GDAL"""
    if path.suffix.lower() != ".kmz":
        return str(path)
    with zipfile.ZipFile(path) as z:
        kmls = [n for n in z.namelist() if n.lower().endswith(".kml")]
    if not kmls:
        raise ValueError(f"{path.name}: ไม่พบไฟล์ .kml ใน KMZ")
    return f"/vsizip/{path.resolve().as_posix()}/{kmls[0]}"


def _to_wgs84(gdf: gpd.GeoDataFrame, label: str) -> gpd.GeoDataFrame:
    if gdf.crs is not None:
        return gdf.to_crs(4326)
    minx, miny, maxx, maxy = gdf.total_bounds
    if -180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90:
        print(f"  {label}: ไม่มีข้อมูล CRS -> ถือว่าเป็น lon/lat (EPSG:4326)")
        return gdf.set_crs(4326)
    raise ValueError(f"{label}: ไม่มีข้อมูล CRS (ไฟล์ .prj หาย?) และพิกัดไม่ใช่ lon/lat")


def _polygons(geom):
    """แตก GeometryCollection/Multi* ออกเป็น polygon (KMZ มักมีจุด/เส้นปนมา)"""
    if geom is None or geom.is_empty:
        return
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        yield geom
    elif hasattr(geom, "geoms"):
        for g in geom.geoms:
            yield from _polygons(g)


def read_polygons(path: Path, layer: str | None = None) -> BaseGeometry:
    """รวม polygon ทุก layer (หรือเฉพาะ layer ที่ระบุ) เป็นรูปเดียวใน lon/lat"""
    src = _source(path)
    layers = [layer] if layer else [name for name, _ in pyogrio.list_layers(src)]
    polys = []
    for lyr in layers:
        gdf = gpd.read_file(src, layer=lyr)
        if gdf.empty:
            continue
        gdf = _to_wgs84(gdf, f"{path.name}:{lyr}")
        polys.extend(p for g in gdf.geometry for p in _polygons(g))
    if not polys:
        raise ValueError(f"{path.name}: ไม่พบ polygon (ต้องเป็นรูปปิด ไม่ใช่จุดหรือเส้น)")
    return force_2d(unary_union(polys))


def load_area(path: Path, layer: str | None = None, name: str | None = None) -> Area:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"ไม่พบไฟล์ {path}")
    lonlat = read_polygons(path, layer)
    minx, _, maxx, _ = lonlat.bounds
    zone = zone_for_lon(lonlat.centroid.x)
    if minx < ZONE_SPLIT_LON <= maxx:
        print(f"  คำเตือน: พื้นที่คร่อมเส้นแบ่ง zone 47/48 (102°E) -> ใช้ zone {zone.number} "
              f"ส่วนที่อยู่อีก zone จะไม่มีแปลง แนะนำให้แยกเป็น 2 ไฟล์")
    native = transform(lambda x, y, z=None: zone.transformer.transform(x, y), lonlat)
    return Area(name=safe_name(name) if name else area_name(path), lonlat=lonlat, native=native, zone=zone)
