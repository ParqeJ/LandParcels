"""อ่าน schema/user_schema.json แล้ว map ผลลัพธ์ parcel/cityplanning ตามที่ผู้ใช้ตั้งไว้ในหน้า ตั้งค่าผลลัพธ์

กฎทอง (backward-compatible):
  * ไม่มีไฟล์ user_schema.json             -> คืน None/ว่าง = ใช้ preset เดิม (parcel 14 / cityplanning 12 ฟิลด์)
  * parcel ไม่มี base_fields (รูปแบบเดิม)   -> None = preset เดิมเช่นกัน
  * ตั้งค่าไม่ถูกต้อง (ชื่อซ้ำ/ไม่รู้จัก)    -> log เตือนแล้ว fallback เป็น preset เดิม ไม่ทำให้รอบดึง (ที่เปลืองโควตา) พัง

รูปแบบ user_schema.json (สร้างจาก dashboard /api/user-schema):
  parcel.base_fields  [{field, name}]   ฟิลด์หลักที่ติ๊กไว้ (map field -> source/type จาก catalog_parcel.json base_fields)
  parcel.addon_fields [{name, type}]    คอลัมน์ว่างไว้กรอกเอง (LandsMaps ไม่มีข้อมูล) type = str/int/float
  parcel.extra_fields [{source, name}]  ฟิลด์เสริมจาก LandsMaps (map source -> type จาก catalog groups)
  cityplanning.extra_fields [{source, name}]   ฟิลด์เสริมต่อท้าย 12 ฟิลด์ล็อกของผังเมือง
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config
from .export import rawang

logger = logging.getLogger("landsmaps.user_schema")

ADDON_TYPES = ("str", "int", "float")
RAI_PER_M2 = 1 / 1600

# ฟิลด์หลัก 12 ตัวของผังเมือง (ลำดับ + ชนิด) — เดิมล็อกตายตัว ตอนนี้ผู้ใช้ติ๊กออก/เปลี่ยนชื่อได้
# ค่ายังมาจาก cityplanning/export._row() (คีย์ = field ด้านล่าง) layout แค่เลือก/เปลี่ยนชื่อทับ
# เป็น source of truth เดียว (export.FIELDS อ้างจากตรงนี้) กันหลุดกันระหว่างสองที่
CITY_BASE: tuple[tuple[str, str], ...] = (
    ("PL_USE", "int"), ("PL_USE_TH", "str"), ("ZONE_HEX", "str"), ("FAR_MAX", "float"),
    ("BCR_MAX", "float"), ("DENS_H", "float"), ("DENS_L", "float"), ("PLAN_NAME", "str"),
    ("YEAR", "str"), ("PROVINCE", "str"), ("AREA_RAI", "float"), ("SRC_LAYER", "str"),
)
CITY_BASE_FIELDS: tuple[str, ...] = tuple(f for f, _ in CITY_BASE)
CITY_BASE_TYPE: dict[str, str] = dict(CITY_BASE)


@dataclass(frozen=True)
class Column:
    """1 คอลัมน์ใน output shapefile"""
    name: str           # ชื่อฟิลด์จริงใน DBF (≤10 ตัวอักษร ตั้งโดยผู้ใช้)
    source: str         # catalog source เช่น 'info.parcelno', 'virtual.wa_total'; '' = addon (กรอกเอง)
    type: str           # str / int / float
    kind: str           # base / addon / extra


@dataclass(frozen=True)
class ParcelLayout:
    columns: tuple[Column, ...]
    remark_name: str    # ชื่อ output ของฟิลด์ system/Remark (ใช้ให้ pipeline นับแปลงค้าง); '' ถ้าไม่มี


@dataclass(frozen=True)
class CityLayout:
    """ผลลัพธ์ผังเมือง = base (12 ฟิลด์หลักที่ติ๊กไว้/เปลี่ยนชื่อแล้ว) + extras ต่อท้าย
    base Column: source = field เดิม (เช่น 'PL_USE') ใช้ดึงค่าจาก _row(); name = ชื่อ output"""
    base: tuple[Column, ...]
    extras: tuple[Column, ...]


# ─────────────────────────── โหลดไฟล์ ───────────────────────────

def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        logger.warning("อ่าน %s ไม่ได้: %s", getattr(path, "name", path), e)
        return None


def _catalog_path(section: str, override: Path | None) -> Path:
    return override or (config.SCHEMA_DIR / f"catalog_{section}.json")


# ─────────────────────────── parcel ───────────────────────────

def _parcel_catalog_maps(catalog: dict[str, Any]) -> tuple[dict[str, dict], dict[str, dict]]:
    """(base_fields map: field -> def, extra map: source -> def)"""
    base = {str(d.get("field")): d for d in catalog.get("base_fields") or [] if d.get("field")}
    extra: dict[str, dict] = {}
    for g in catalog.get("groups") or []:
        for f in g.get("fields") or []:
            if f.get("source"):
                extra[str(f["source"])] = f
    return base, extra


def build_parcel_layout(parcel_cfg: Any, catalog: dict[str, Any]) -> ParcelLayout | None:
    """สร้าง layout จาก parcel config + catalog — คืน None ถ้าไม่ได้ตั้งค่า (รูปแบบเดิม) หรือตั้งค่าไม่ถูกต้อง"""
    if not isinstance(parcel_cfg, dict) or not isinstance(parcel_cfg.get("base_fields"), list):
        return None                                   # ไม่มี base_fields = preset เดิม
    base_cat, extra_cat = _parcel_catalog_maps(catalog)
    cols: list[Column] = []
    remark_name = ""

    for b in parcel_cfg["base_fields"]:
        if not isinstance(b, dict):
            continue
        field, name = str(b.get("field", "")), str(b.get("name", "")).strip()
        d = base_cat.get(field)
        if not d or not name:
            continue
        cols.append(Column(name, str(d.get("source", "")), str(d.get("type", "str")), "base"))
        if d.get("source") == "system" or field == "Remark":
            remark_name = name

    for a in parcel_cfg.get("addon_fields") or []:
        if not isinstance(a, dict):
            continue
        name = str(a.get("name", "")).strip()
        typ = str(a.get("type", "str"))
        if name:
            cols.append(Column(name, "", typ if typ in ADDON_TYPES else "str", "addon"))

    for x in parcel_cfg.get("extra_fields") or []:
        if not isinstance(x, dict):
            continue
        src, name = str(x.get("source", "")), str(x.get("name", "")).strip()
        f = extra_cat.get(src)
        if f and name:
            cols.append(Column(name, src, str(f.get("type", "str")), "extra"))

    return _finalize_parcel(tuple(cols), remark_name)


def _finalize_parcel(cols: tuple[Column, ...], remark_name: str) -> ParcelLayout | None:
    if not cols:
        return None
    keys = [c.name.casefold() for c in cols]            # DBF ไม่แยกตัวพิมพ์เล็ก/ใหญ่
    if len(set(keys)) != len(keys):
        logger.warning("user_schema.json (parcel) มีชื่อฟิลด์ซ้ำกัน -> ใช้ 14 ฟิลด์เดิมแทน")
        return None
    return ParcelLayout(cols, remark_name)


def load_parcel_layout(schema_file: Path | None = None, catalog_file: Path | None = None) -> ParcelLayout | None:
    data = _load_json(schema_file or config.USER_SCHEMA_FILE)
    if not data:
        return None
    catalog = _load_json(_catalog_path("parcel", catalog_file)) or {}
    try:
        return build_parcel_layout(data.get("parcel"), catalog)
    except Exception as e:                              # กันทุกกรณี ไม่ให้รอบดึงพัง
        logger.warning("ประมวลผล user_schema.json (parcel) ไม่ได้ ใช้ 14 ฟิลด์เดิม: %s", e)
        return None


# ─────────────────────────── resolve ค่าราย parcel ───────────────────────────
# rec = {"seq": str, "land_no": str, "info": dict, "remark": str, "type_default": str}

def _pick(info: dict, dotted: str) -> Any:
    cur: Any = info
    for key in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _wa_total(info: dict) -> float | None:
    if info.get("wa") is None and info.get("subwa") is None:
        return None                                    # ยังไม่มีรายละเอียด -> ว่าง (ไม่ใช่ 0)
    return _to_float(info.get("wa")) + _to_float(info.get("subwa")) / 10


def _area_m2(info: dict) -> float | None:
    wt = _wa_total(info)
    if info.get("rai") is None and info.get("ngan") is None and wt is None:
        return None
    return _to_float(info.get("rai")) * 1600 + _to_float(info.get("ngan")) * 400 + (wt or 0) * 4


def resolve_parcel(source: str, rec: dict[str, Any]) -> Any:
    info = rec.get("info") or {}
    if source == "seq":
        return rec.get("seq")
    if source == "wfs.land_no":
        return rec.get("land_no")
    if source == "system":
        return rec.get("remark")
    if source == "info.parcel_type":
        return info.get("parcel_type") or rec.get("type_default")
    if source == "virtual.wa_total":
        return _wa_total(info)
    if source == "virtual.rawang_short":
        return rawang(info.get("utm"))
    if source == "virtual.area_m2":
        return _area_m2(info)
    if source.startswith("info."):
        return _pick(info, source[len("info."):])
    return None


def project_parcel(rec: dict[str, Any], layout: ParcelLayout) -> dict[str, Any]:
    """สร้าง 1 แถว output ตาม layout (addon = คอลัมน์ว่าง)"""
    row: dict[str, Any] = {}
    for c in layout.columns:
        if c.kind == "addon":
            row[c.name] = "" if c.type == "str" else None
        else:
            row[c.name] = cast(resolve_parcel(c.source, rec), c.type)
    return row


# ─────────────────────────── cityplanning (12 ฟิลด์ล็อก + extra ต่อท้าย) ───────────────────────────

def _city_extra_cat(catalog_file: Path | None) -> dict[str, dict]:
    """source -> field def จาก groups ของ catalog_cityplanning"""
    catalog = _load_json(_catalog_path("cityplanning", catalog_file)) or {}
    out: dict[str, dict] = {}
    for g in catalog.get("groups") or []:
        for f in g.get("fields") or []:
            if f.get("source"):
                out[str(f["source"])] = f
    return out


def _city_extra_cols(cfg: dict[str, Any], reserved: set[str],
                     catalog_file: Path | None) -> tuple[Column, ...]:
    """ฟิลด์เสริมต่อท้าย base — ข้ามชื่อว่าง/ไม่รู้จัก/ชนชื่อที่จองไว้ (base + extra ก่อนหน้า)"""
    extra_cat = _city_extra_cat(catalog_file)
    seen = set(reserved)
    cols: list[Column] = []
    for x in cfg.get("extra_fields") or []:
        if not isinstance(x, dict):
            continue
        src, name = str(x.get("source", "")), str(x.get("name", "")).strip()
        f = extra_cat.get(src)
        if not f or not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        cols.append(Column(name, src, str(f.get("type", "str")), "extra"))
    return tuple(cols)


def load_city_extras(schema_file: Path | None = None, catalog_file: Path | None = None) -> tuple[Column, ...]:
    """ฟิลด์เสริมของผังเมือง (ต่อท้าย 12 ฟิลด์เดิม) — ว่าง = ไม่เพิ่มอะไร (preset เดิม)
    กฎเดิม: ชื่อห้ามชน fixed_fields (12 ฟิลด์ของ catalog) ใช้โดย test/โค้ดที่เรียกตรง"""
    data = _load_json(schema_file or config.USER_SCHEMA_FILE) or {}
    cfg = data.get("cityplanning") or {}
    if not isinstance(cfg, dict):
        return ()
    catalog = _load_json(_catalog_path("cityplanning", catalog_file)) or {}
    reserved = {str(n).casefold() for n in catalog.get("fixed_fields") or []}
    return _city_extra_cols(cfg, reserved, catalog_file)


def _build_city_base(base_cfg: Any) -> tuple[Column, ...] | None:
    """[{field, name}] -> base Columns (source = field เดิม) — None = ตั้งค่าเสีย (ชื่อซ้ำ/ไม่รู้จัก) ให้ fallback preset
    [] ที่ส่งมา (ติ๊กออกครบ) = () ถือว่าตั้งใจ ไม่ fallback"""
    if not isinstance(base_cfg, list):
        return None
    cols: list[Column] = []
    seen: set[str] = set()
    for b in base_cfg:
        if not isinstance(b, dict):
            continue
        field, name = str(b.get("field", "")), str(b.get("name", "")).strip()
        typ = CITY_BASE_TYPE.get(field)
        if typ is None or not name:
            return None                                # ฟิลด์ไม่รู้จัก/ไม่มีชื่อ = เสีย
        if name.casefold() in seen:
            return None                                # ชื่อซ้ำ = เสีย
        seen.add(name.casefold())
        cols.append(Column(name, field, typ, "base"))
    return tuple(cols)


def _default_city_base() -> tuple[Column, ...]:
    """preset = 12 ฟิลด์เดิม ชื่อเดิม (ใช้ merge ได้) — ใช้เมื่อยังไม่เคยตั้งค่า"""
    return tuple(Column(f, f, t, "base") for f, t in CITY_BASE)


def load_city_layout(schema_file: Path | None = None, catalog_file: Path | None = None) -> CityLayout:
    """อ่าน user_schema.json ส่วน cityplanning -> CityLayout (base ที่ติ๊ก + extras)
    ไม่มีไฟล์/ไม่มี base_fields/ตั้งค่าเสีย -> preset 12 ฟิลด์เดิม (backward-compatible, merge ปลอดภัย)"""
    base = _default_city_base()
    data = _load_json(schema_file or config.USER_SCHEMA_FILE) or {}
    cfg = data.get("cityplanning")
    if isinstance(cfg, dict):
        if isinstance(cfg.get("base_fields"), list):
            built = _build_city_base(cfg["base_fields"])
            if built is not None:                      # None = ตั้งค่าเสีย -> คง preset
                base = built
        reserved = {c.name.casefold() for c in base}
        extras = _city_extra_cols(cfg, reserved, catalog_file)
        return CityLayout(base, extras)
    return CityLayout(base, ())


def resolve_city(source: str, props: dict[str, Any], native_area_m2: float,
                 label: str, color: str) -> Any:
    if source == "virtual.pl_use_th":
        return label
    if source == "virtual.zone_hex":
        return color
    if source == "virtual.area_rai":
        return round(native_area_m2 * RAI_PER_M2, 2)
    if source == "virtual.area_m2":
        return round(native_area_m2, 2)
    if source.startswith("props."):
        return props.get(source[len("props."):])
    return None


# ─────────────────────────── cast ชนิดข้อมูล ───────────────────────────

def cast(value: Any, type_: str) -> Any:
    """แปลงค่าเป็นชนิดสำหรับ output; ว่าง -> '' (str) หรือ None (int/float)"""
    if value is None or value == "":
        return "" if type_ == "str" else None
    if type_ == "int":
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None
    if type_ == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)
