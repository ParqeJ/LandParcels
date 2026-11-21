"""รวมขั้นตอนดึงผังเมือง 1 จังหวัด: metadata -> feature -> SHP/GPKG

วิธีดึง feature มี 2 แบบ:
  query    = /query (objectId ทั้งหมดแล้วดึงเป็นชุด) เร็ว ใช้ได้เมื่อ service มี capability 'Data'
  identify = /identify ซอยกรอบ (ดู identify.py) ช้ากว่ามาก แต่ใช้ได้กับ service ที่ไม่มี 'Data'
auto (ค่าเริ่มต้น) เลือกให้เองจาก capability และสลับไป identify ถ้า /query ถูกปฏิเสธ
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..area import load_area, safe_name
from ..config import OUTPUT_DIR
from ..zones import Zone
from . import export, identify, legend, service
from .provinces import Province, resolve
from .service import CapabilityNotSupported, LayerRef, ServiceInfo

CITYPLANNING_DIR = OUTPUT_DIR / "cityplanning"
METHODS = ("auto", "query", "identify")


@dataclass(frozen=True)
class Result:
    province: Province
    layer_name: str
    zone: int
    n_features: int
    files: list[Path]


def _folder_name(prov: Province) -> str:
    return f"{prov.code}_{safe_name(prov.name)}"


def describe_service(value: str | int, token: str | None) -> ServiceInfo:
    """ดึง metadata ของ service จังหวัดนั้น (ใช้โดย --list-layers)"""
    prov = resolve(value)
    return service.get_service(prov.code, token)


def _fetch_query(layer_url: str, token: str | None, envelope: tuple | None) -> list[dict]:
    oids = service.all_object_ids(layer_url, token, envelope=envelope)
    print(f"  พบ {len(oids):,} รูปผัง -> ดึงเป็นชุดละ {service.OID_CHUNK}")
    return service.fetch_features(layer_url, token, oids) if oids else []


def _fetch_identify(prov: Province, info: ServiceInfo, layer_ref: LayerRef,
                    token: str | None, envelope: tuple | None) -> list[dict]:
    start = (identify.Box(*envelope) if envelope
             else identify.extent_box(info.extent, info.extent_wkid))
    print(f"  ใช้ /identify ซอยกรอบ (เพดาน {info.max_record_count} รูป/คำขอ) "
          f"-> ช้ากว่าปกติ แต่ดึงได้ครบ")
    return identify.fetch_by_identify(service.service_url(prov.code), layer_ref.id, token,
                                      start, max_records=info.max_record_count)


def _fetch(method: str, prov: Province, info: ServiceInfo, layer_ref: LayerRef,
           layer_url: str, token: str | None, envelope: tuple | None) -> list[dict]:
    if method not in METHODS:
        raise ValueError(f"method ต้องเป็นหนึ่งใน {METHODS}")
    if method == "identify" or (method == "auto" and not info.supports_data_query):
        if method == "auto":
            caps = ",".join(info.capabilities)
            print(f"  service เปิดแค่ capability [{caps}] ไม่มี 'Data' -> /query ใช้ไม่ได้")
        return _fetch_identify(prov, info, layer_ref, token, envelope)
    try:
        return _fetch_query(layer_url, token, envelope)
    except CapabilityNotSupported as e:
        if method == "query":
            raise
        print(f"  /query ถูกปฏิเสธ ({e}) -> สลับไปใช้ /identify")
        return _fetch_identify(prov, info, layer_ref, token, envelope)


def run_province(value: str | int, token: str | None, *, layer: str | int | None = None,
                 area_path: Path | None = None, out_dir: Path = CITYPLANNING_DIR,
                 formats: tuple[str, ...] = ("shp", "gpkg"), method: str = "auto") -> Result:
    """ดึงผังเมืองทั้งจังหวัด (หรือเฉพาะกรอบของ area_path) แล้วบันทึกไฟล์"""
    prov = resolve(value)
    info = service.get_service(prov.code, token)
    zone = Zone(info.zone)
    layer_ref = info.resolve_layer(layer)
    layer_url = f"{service.service_url(prov.code)}/{layer_ref.id}"
    print(f"[{prov.code} {prov.name}] service PLLU{prov.code} | zone {zone.number} "
          f"(EPSG:{zone.epsg}) | ชั้น {layer_ref.id} {layer_ref.name}")

    legend.merge_renderer(service.get_renderer(layer_url, token))

    envelope = None
    if area_path is not None:
        area = load_area(Path(area_path))
        envelope = tuple(round(v, 6) for v in area.bbox)
        print(f"  ตัดด้วยกรอบพื้นที่ {area.name}: {envelope}")

    features = _fetch(method, prov, info, layer_ref, layer_url, token, envelope)
    if not features:
        print("  ไม่มีรูปผังในขอบเขตนี้ (ไม่สร้างไฟล์)")
        return Result(prov, layer_ref.name, zone.number, 0, [])

    gdf = export.build(features, zone, prov.name, layer_ref.name)
    stem = out_dir / _folder_name(prov) / f"{_folder_name(prov)}_cityplanning_epsg{zone.epsg}"
    files = export.save(gdf, stem, formats=formats)

    for f in files:
        print(f"  -> {f}  ({len(gdf):,} รูปผัง)")
    return Result(prov, layer_ref.name, zone.number, len(gdf), files)
