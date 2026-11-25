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

from landsmaps import config
from landsmaps.area import area_name, is_area_file
from landsmaps.export import REMARK_PENDING
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
    return JSONResponse({"items": collect(AREAS_DIR, OUTPUT_DIR, CACHE_DIR), "now": time.time()})


def collect(areas_dir: Path, output_dir: Path, cache_dir: Path) -> list[dict[str, Any]]:
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
        items.append(_describe(p.name, name, st, output_dir))
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


def _describe(area: str, name: str | None, st: dict[str, Any] | None, output_dir: Path) -> dict[str, Any]:
    if st:
        state = st.get("state") or "new"
        if state == "running" and not pid_alive(st.get("pid")):
            state = "stale"                     # process ตายไปแล้ว (ปิดหน้าต่าง / ไฟดับ / ถูก kill)
        return {
            "area": area, "name": st.get("name") or name, "state": state, "from": "status",
            "total": st.get("total"), "pending": st.get("pending"), "progress": st.get("progress"),
            "started_at": st.get("started_at"), "ended_at": st.get("ended_at"),
            "updated_at": st.get("updated_at"), "error": st.get("error"),
        }
    counted = _count_output(output_dir, name) if name else None
    if counted:
        total, pending, mtime = counted
        return {"area": area, "name": name, "state": "partial" if pending else "done", "from": "output",
                "total": total, "pending": pending, "progress": None,
                "started_at": None, "ended_at": mtime, "updated_at": mtime, "error": None}
    return {"area": area, "name": name, "state": "new", "from": None, "total": None, "pending": None,
            "progress": None, "started_at": None, "ended_at": None, "updated_at": None, "error": None}


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
