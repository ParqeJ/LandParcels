"""ตั้งค่าผลลัพธ์ cityplanning: ฟิลด์หลัก 12 ตัว (ติ๊กออก/เปลี่ยนชื่อได้) + ฟิลด์เสริม

user_schema.json ส่วน cityplanning:
    base_fields  [{field, name}]   ฟิลด์หลักที่ติ๊กไว้ (catalog_cityplanning.json: base_fields)
    extra_fields [{source, name}]  ฟิลด์เสริมจาก catalog groups
ไม่มี base_fields = preset เดิม (12 ฟิลด์ครบ ชื่อเดิม — ใช้ merge ได้)
ขนานกับ dashboard/parcel_schema.py แต่ไม่มีชั้น add-on (ผังเมืองไม่มีคอลัมน์กรอกเอง)
"""
from __future__ import annotations

from typing import Any

SHP_NAME_MAX = 10


def has_base(cfg: Any) -> bool:
    return isinstance(cfg, dict) and "base_fields" in cfg


def normalize(cfg: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    """คืน dict ใหม่: ตัดช่องว่างชื่อ base_fields — ไม่แก้ของเดิม (ไม่มีฟิลด์ locked เหมือน parcel)"""
    base = [{"field": str(b.get("field", "")), "name": str(b.get("name", "")).strip()}
            for b in cfg.get("base_fields") or [] if isinstance(b, dict)]
    return {**cfg, "base_fields": base}


def core_problems(cfg: dict[str, Any], catalog: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(ชื่อฟิลด์หลักที่จะออกใน output, รายการปัญหา) — cfg ต้องผ่าน normalize แล้ว
    DBF ไม่แยกตัวพิมพ์เล็ก/ใหญ่ ('year' = 'YEAR') จึงเทียบแบบ casefold"""
    known = {d.get("field") for d in catalog.get("base_fields") or []}
    problems = [f"cityplanning: ไม่รู้จักฟิลด์หลัก '{b['field']}'"
                for b in cfg["base_fields"] if b["field"] not in known]
    names: list[str] = []
    seen: dict[str, str] = {}
    for b in cfg["base_fields"]:
        name, label = b["name"], f"ฟิลด์หลัก {b['field']}"
        key = name.casefold()
        if not name:
            problems.append(f"cityplanning: {label} ยังไม่ได้ตั้งชื่อ")
        elif len(name) > SHP_NAME_MAX:
            problems.append(f"cityplanning: ชื่อ '{name}' ({label}) เกิน {SHP_NAME_MAX} ตัวอักษร")
        elif key in seen:
            problems.append(f"cityplanning: ชื่อ '{name}' ซ้ำกัน ({seen[key]} กับ {label})")
        else:
            seen[key] = label
            names.append(name)
    return names, problems
