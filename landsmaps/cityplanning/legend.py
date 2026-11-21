"""ตาราง PL_USE: รหัสประเภทการใช้ประโยชน์ที่ดิน -> ชื่อไทย + สีทางการของผัง

ค่าตั้งต้นมาจาก renderer ของ service PLLU ของกรมที่ดิน (``data/pl_use_legend.json``)
ตอน export จะ merge กับ legend ที่ service คืนมา ณ เวลานั้นด้วย เผื่อจังหวัดมีคลาสเพิ่ม
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "data" / "pl_use_legend.json"

UNKNOWN_LABEL = "ไม่ระบุประเภท"
DEFAULT_COLOR = "#cccccc"


@lru_cache(maxsize=1)
def _table() -> dict[str, dict[str, str]]:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def label_for(code: str | int | None) -> str:
    """รหัส PL_USE -> ชื่อประเภทภาษาไทย (ไม่รู้จัก -> 'ไม่ระบุประเภท')"""
    entry = _table().get(str(code).strip()) if code is not None else None
    return entry["label"] if entry else UNKNOWN_LABEL


def color_for(code: str | int | None) -> str:
    """รหัส PL_USE -> สี hex ของผัง (ไม่รู้จัก -> สีเทากลาง)"""
    entry = _table().get(str(code).strip()) if code is not None else None
    return (entry.get("color") or DEFAULT_COLOR) if entry else DEFAULT_COLOR


def merge_renderer(unique_value_infos: list[dict]) -> None:
    """เติมคลาสที่ service คืนมา (จาก drawingInfo.renderer.uniqueValueInfos) ลงตารางในหน่วยความจำ

    คลาสที่มีอยู่แล้วในไฟล์ไม่ทับ (ไฟล์เป็น source of truth) เติมเฉพาะรหัสใหม่
    """
    table = _table()
    for info in unique_value_infos or []:
        code = str(info.get("value", "")).strip()
        if not code or code in table:
            continue
        label = info.get("label") or UNKNOWN_LABEL
        parts = label.split(" ", 1)
        if parts[0] == code and len(parts) == 2:        # "3100 อุตสาหกรรม" -> ตัดรหัสนำหน้าออก
            label = parts[1].strip()
        color = info.get("symbol", {}).get("color")
        hex_color = "#%02x%02x%02x" % tuple(color[:3]) if color else DEFAULT_COLOR
        table[code] = {"label": label, "color": hex_color}


def classes() -> dict[str, dict[str, str]]:
    return dict(_table())
