"""/api/status/areas — สถานะการดึงของแต่ละไฟล์ใน areas/ (อ่านอย่างเดียว)

อ่านจาก cache/status/<name>.json ที่ fetch_parcels.py เขียน (รันจาก dashboard หรือ Task Scheduler ก็ได้)
ถ้าไม่มีไฟล์สถานะ (พื้นที่ที่ดึงไว้ก่อนมีระบบนี้) -> นับจาก output/<name>/<name>_parcel_*.shp แทน
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from landsmaps import config, keystore
from landsmaps.api import read_token
from landsmaps.area import area_name, is_area_file
from landsmaps.export import REMARK_PENDING
from landsmaps.quota import Quota, days_left, quota_for
from landsmaps.status import STATUS_DIRNAME, pid_alive, read_status

logger = logging.getLogger("dashboard.status")
router = APIRouter()

AREAS_DIR = config.AREAS_DIR
OUTPUT_DIR = config.OUTPUT_DIR
CACHE_DIR = config.CACHE_DIR

# (path, mtime) -> (total, pending) — ไม่ต้องอ่าน shapefile ซ้ำทุกครั้งที่หน้าเว็บ refresh
_SHP_COUNTS: dict[tuple[str, float], tuple[int, int]] = {}


@router.get("/api/status/areas")
def areas_status() -> JSONResponse:
    quota = current_quota()
    return JSONResponse({"items": collect(AREAS_DIR, OUTPUT_DIR, CACHE_DIR, quota),
                         "quota": list(quota), "now": time.time()})


def current_quota() -> Quota:
    """โควตา/วันของตอนนี้ — มี token ของบัญชี = โควตาแบบล็อกอิน (อ่านไม่ได้ก็ถือว่าไม่ล็อกอิน)"""
    try:
        return quota_for(read_token())
    except (keystore.KeyFileError, OSError) as e:
        logger.warning("อ่าน token เพื่อดูโควตาไม่ได้: %s", e)
        return config.FREE_QUOTA_RANGE


def remaining_parcels(state: str, pending: int | None, progress: dict[str, Any] | None) -> int | None:
    """แปลงที่ยังต้องดึงอีก — กำลังรัน = ที่เหลือในรอบนี้ · จบแล้ว = ที่ยังค้าง · None = ยังไม่รู้"""
    if state == "running":
        if not progress:
            return None
        todo, n = progress.get("todo"), progress.get("n")
        return max(0, todo - n) if todo is not None and n is not None else None
    return pending


def collect(areas_dir: Path, output_dir: Path, cache_dir: Path,
            quota: Quota = config.FREE_QUOTA_RANGE) -> list[dict[str, Any]]:
    if not areas_dir.exists():
        return []
    statuses = _load_statuses(cache_dir)
    latest_by_source: dict[str, dict[str, Any]] = {}
    for st in statuses.values():
        src = st.get("source")
        if src and st.get("updated_at", 0) >= latest_by_source.get(src, {}).get("updated_at", 0):
            latest_by_source[src] = st
    items = []
    for p in sorted(areas_dir.iterdir()):
        if not is_area_file(p):
            continue
        name = _default_name(p)
        st = latest_by_source.get(p.name) or (statuses.get(name) if name else None)
        items.append(_describe(p.name, name, st, output_dir, quota))
    return items


def _load_statuses(cache_dir: Path) -> dict[str, dict[str, Any]]:
    folder = cache_dir / STATUS_DIRNAME
    if not folder.is_dir():
        return {}
    found = {}
    for f in folder.glob("*.json"):
        st = read_status(f)
        if st:
            found[st.get("name") or f.stem] = st
    return found


def _default_name(p: Path) -> str | None:
    try:
        return area_name(p)
    except ValueError:
        return None


def _days(state: str, pending: int | None, progress: dict[str, Any] | None, quota: Quota) -> str | None:
    """ข้อความ "ต้องรันอีกกี่วัน" หรือ None ถ้าไม่มีอะไรค้าง/ยังไม่รู้จำนวน"""
    left = remaining_parcels(state, pending, progress)
    return days_left(left, quota) if left else None


def _describe(area: str, name: str | None, st: dict[str, Any] | None, output_dir: Path,
              quota: Quota = config.FREE_QUOTA_RANGE) -> dict[str, Any]:
    if st:
        state = st.get("state") or "new"
        if state == "running" and not pid_alive(st.get("pid")):
            state = "stale"                     # process ตายไปแล้ว (ปิดหน้าต่าง / ไฟดับ / ถูก kill)
        return {
            "area": area, "name": st.get("name") or name, "state": state, "from": "status",
            "total": st.get("total"), "pending": st.get("pending"), "progress": st.get("progress"),
            "days": _days(state, st.get("pending"), st.get("progress"), quota),
            "started_at": st.get("started_at"), "ended_at": st.get("ended_at"),
            "updated_at": st.get("updated_at"), "error": st.get("error"),
        }
    counted = _count_output(output_dir, name) if name else None
    if counted:
        total, pending, mtime = counted
        state = "partial" if pending else "done"
        return {"area": area, "name": name, "state": state, "from": "output",
                "total": total, "pending": pending, "progress": None,
                "days": _days(state, pending, None, quota),
                "started_at": None, "ended_at": mtime, "updated_at": mtime, "error": None}
    return {"area": area, "name": name, "state": "new", "from": None, "total": None, "pending": None,
            "progress": None, "days": None,
            "started_at": None, "ended_at": None, "updated_at": None, "error": None}


def _count_output(output_dir: Path, name: str) -> tuple[int, int, float] | None:
    shps = sorted((output_dir / name).glob(f"{name}_parcel_epsg*.shp"))
    if not shps:
        return None
    shp = shps[-1]
    try:
        mtime = shp.stat().st_mtime
        key = (str(shp), mtime)
        if key not in _SHP_COUNTS:
            import pyogrio

            df = pyogrio.read_dataframe(shp, columns=["Remark"], read_geometry=False)
            _SHP_COUNTS[key] = (len(df), int((df["Remark"] == REMARK_PENDING).sum()))
        total, pending = _SHP_COUNTS[key]
    except Exception as e:  # noqa: BLE001 - shapefile เสีย/ถูกล็อก -> แสดงเป็น "ยังไม่เคยดึง" ดีกว่าพังทั้งตาราง
        logger.warning("นับ %s ไม่สำเร็จ: %s", shp, e)
        return None
    return total, pending, mtime
