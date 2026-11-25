"""ตั้งค่าผลลัพธ์ parcel: ฟิลด์หลักจาก LandsMaps + ฟิลด์ add-on (กรอกเอง) + แปลงตัวอย่างสำหรับพรีวิว

user_schema.json ส่วน parcel:
    base_fields  [{field, name}]   ฟิลด์หลักที่ติ๊กไว้ (catalog_parcel.json: base_fields) — Remark ต้องมีเสมอ
    addon_fields [{name, type}]    คอลัมน์ว่างไว้กรอกเอง (LandsMaps ไม่มีข้อมูล) type = str/int/float
    extra_fields [{source, name}]  ฟิลด์เสริมจาก LandsMaps (catalog groups)
ไฟล์รูปแบบเดิมที่ไม่มี base_fields = preset ANIS POWER (14 ฟิลด์เดิมครบ)
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from landsmaps import config

logger = logging.getLogger("dashboard.parcel_schema")
router = APIRouter()

CACHE_DIR = config.CACHE_DIR
SHP_NAME_MAX = 10
ADDON_TYPES = ("str", "int", "float")
SAMPLE_SCAN_LINES = 5000        # หาแปลงตัวอย่างไม่เกินกี่บรรทัดต่อไฟล์ (ไฟล์ใหญ่หลาย MB)


def has_layout(cfg: Any) -> bool:
    return isinstance(cfg, dict) and "base_fields" in cfg


def normalize(cfg: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    """คืน dict ใหม่: ตัดช่องว่างในชื่อ + เติมฟิลด์ locked (Remark) ถ้าขาด — ไม่แก้ของเดิม"""
    base = [{"field": str(b.get("field", "")), "name": str(b.get("name", "")).strip()}
            for b in cfg.get("base_fields") or [] if isinstance(b, dict)]
    have = {b["field"] for b in base}
    base += [{"field": d["field"], "name": d["field"]}
             for d in catalog.get("base_fields") or [] if d.get("locked") and d["field"] not in have]
    addons = [{"name": str(a.get("name", "")).strip(), "type": str(a.get("type", "str"))}
              for a in cfg.get("addon_fields") or [] if isinstance(a, dict)]
    return {**cfg, "base_fields": base, "addon_fields": addons}


def core_problems(cfg: dict[str, Any], catalog: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(ชื่อฟิลด์หลัก + add-on ที่จะออกใน output, รายการปัญหา) — cfg ต้องผ่าน normalize แล้ว"""
    known = {d["field"] for d in catalog.get("base_fields") or []}
    problems = [f"parcel: ไม่รู้จักฟิลด์หลัก '{b['field']}'" for b in cfg["base_fields"] if b["field"] not in known]
    problems += [f"parcel: add-on '{a['name']}' ชนิด '{a['type']}' ใช้ไม่ได้ (ใช้ได้: {', '.join(ADDON_TYPES)})"
                 for a in cfg["addon_fields"] if a["type"] not in ADDON_TYPES]
    entries = [(f"ฟิลด์หลัก {b['field']}", b["name"]) for b in cfg["base_fields"]]
    entries += [(f"add-on ช่องที่ {i}", a["name"]) for i, a in enumerate(cfg["addon_fields"], 1)]
    names: list[str] = []
    seen: dict[str, str] = {}
    for label, name in entries:
        key = name.casefold()                    # DBF ถือว่า 'rai' กับ 'Rai' เป็นชื่อเดียวกัน
        if not name:
            problems.append(f"parcel: {label} ยังไม่ได้ตั้งชื่อ")
        elif len(name) > SHP_NAME_MAX:
            problems.append(f"parcel: ชื่อ '{name}' ({label}) เกิน {SHP_NAME_MAX} ตัวอักษร")
        elif key in seen:
            problems.append(f"parcel: ชื่อ '{name}' ซ้ำกัน ({seen[key]} กับ {label})")
        else:
            seen[key] = label
            names.append(name)
    return names, problems


# ─────────────────────── แปลงตัวอย่างสำหรับพรีวิว ───────────────────────

@router.get("/api/schema/sample")
def schema_sample() -> JSONResponse:
    """แปลงจริง 1 แปลงจาก cache (ข้อมูลดิบ LandsMaps + รูปแปลง WFS) — ยังไม่เคยดึง = null (หน้าเว็บใช้ค่าตัวอย่างแทน)"""
    return JSONResponse({"sample": find_sample(CACHE_DIR)})


def find_sample(cache_dir: Path) -> dict[str, Any] | None:
    if not cache_dir.is_dir():
        return None
    for detail in sorted(cache_dir.glob("*_detail.jsonl"), key=lambda p: p.stat().st_size):
        site = detail.name[: -len("_detail.jsonl")]
        polys = _wfs_polygons(cache_dir, site)
        if not polys:
            continue
        for rec in _records(detail):
            info, seq = rec.get("info"), str(rec.get("seq"))
            if isinstance(info, dict) and str(info.get("parcel_seq")) == seq and seq in polys:
                land_no, geometry = polys[seq]
                return {"site": site, "seq": seq, "land_no": land_no, "info": info, "geometry": geometry}
    return None


def _records(path: Path) -> Iterator[dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if i >= SAMPLE_SCAN_LINES:
                    return
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict):
                    yield rec
    except OSError as e:
        logger.warning("อ่าน %s ไม่ได้: %s", path.name, e)


def _wfs_polygons(cache_dir: Path, site: str) -> dict[str, tuple[str, Any]]:
    """{parcel_seq: (land_no, geometry)} จาก cache/parcel_<ระวาง>_<site>.json"""
    pattern = re.compile(rf"parcel_\d+_{re.escape(site)}\.json")
    found: dict[str, tuple[str, Any]] = {}
    for f in cache_dir.glob("parcel_*.json"):
        if not pattern.fullmatch(f.name):
            continue
        try:
            feats = json.loads(f.read_text(encoding="utf-8")).get("features") or []
        except (OSError, ValueError, AttributeError) as e:
            logger.warning("อ่าน %s ไม่ได้: %s", f.name, e)
            continue
        for feat in feats:
            props = feat.get("properties") or {}
            if props.get("parcel_seq") is not None and feat.get("geometry"):
                found[str(props["parcel_seq"])] = (str(props.get("land_no") or ""), feat["geometry"])
    return found
