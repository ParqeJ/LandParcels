"""LandParcels Dashboard - FastAPI backend

หน้าเดียวจบ: input + output + schema + cityplanning + run + monitor + map
รัน: python -m uvicorn dashboard.server:app --host 127.0.0.1 --port 8765
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger("dashboard")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = ROOT / "schema"
AREAS_DIR = ROOT / "areas"
OUTPUT_DIR = ROOT / "output"
DASHBOARD_DIR = Path(__file__).resolve().parent

SHP_NAME_MAX = 10


@dataclass
class Job:
    id: str
    kind: str
    cmd: list[str]
    args: dict[str, Any]
    status: str = "pending"
    started_at: float = 0.0
    ended_at: float = 0.0
    returncode: int | None = None
    lines: list[str] = field(default_factory=list)
    progress: dict[str, Any] = field(default_factory=dict)
    _subscribers: list[asyncio.Queue] = field(default_factory=list)
    _process: Any = None

    def publish(self, event: dict[str, Any]) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except Exception:
                pass


JOBS: dict[str, Job] = {}


class ParcelArgs(BaseModel):
    areas: list[str] = []
    no_detail: bool = False
    refetch: str = "none"
    layer: str | None = None
    name: str | None = None


class CityArgs(BaseModel):
    provinces: list[str]
    area: str | None = None
    layer: str | None = None
    token: str | None = None
    format: str = "both"
    method: str = "auto"


class RunRequest(BaseModel):
    kind: str
    parcel: ParcelArgs | None = None
    cityplanning: CityArgs | None = None


class UserSchemaIn(BaseModel):
    parcel: dict[str, Any] | None = None
    cityplanning: dict[str, Any] | None = None


app = FastAPI(title="LandParcels Dashboard", version="0.1")


@app.get("/")
def root() -> FileResponse:
    return FileResponse(DASHBOARD_DIR / "index.html")


@app.get("/api/catalog/{section}")
def get_catalog(section: str) -> JSONResponse:
    if section not in ("parcel", "cityplanning"):
        raise HTTPException(400, "section ต้องเป็น parcel หรือ cityplanning")
    path = SCHEMA_DIR / f"catalog_{section}.json"
    if not path.exists():
        raise HTTPException(404, f"ไม่พบ {path.name}")
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


@app.get("/api/user-schema")
def get_user_schema() -> JSONResponse:
    path = SCHEMA_DIR / "user_schema.json"
    if not path.exists():
        return JSONResponse({"_missing": True, "parcel": {"extra_fields": []}, "cityplanning": {"extra_fields": []}})
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


@app.post("/api/user-schema")
def save_user_schema(body: UserSchemaIn) -> JSONResponse:
    data = {
        "_generated_by": "dashboard",
        "_generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "parcel": body.parcel or {"extra_fields": []},
        "cityplanning": body.cityplanning or {"extra_fields": []},
    }
    _validate_schema(data)
    SCHEMA_DIR.mkdir(exist_ok=True)
    (SCHEMA_DIR / "user_schema.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return JSONResponse({"ok": True, "path": str(SCHEMA_DIR / "user_schema.json")})


def _validate_schema(data: dict[str, Any]) -> None:
    for key in ("parcel", "cityplanning"):
        for f in (data.get(key, {}) or {}).get("extra_fields", []) or []:
            if not isinstance(f, dict) or "source" not in f or "name" not in f:
                raise HTTPException(400, f"{key}: extra_fields ต้องมี source และ name")
            if len(str(f["name"])) > SHP_NAME_MAX:
                raise HTTPException(400, f"{key}: ชื่อ '{f['name']}' เกิน {SHP_NAME_MAX} ตัวอักษร")


AREA_SUFFIXES = {".kmz", ".kml", ".geojson", ".json", ".shp"}


@app.get("/api/areas")
def list_areas() -> JSONResponse:
    if not AREAS_DIR.exists():
        return JSONResponse({"items": [], "note": "ไม่พบ areas/ - สร้างโฟลเดอร์แล้ววางไฟล์"})
    items = []
    for p in sorted(AREAS_DIR.iterdir()):
        if p.name.startswith("."):
            continue
        is_gdb = p.is_dir() and p.suffix.lower() == ".gdb"
        if not (p.is_file() or is_gdb):
            continue
        if p.is_file() and p.suffix.lower() not in AREA_SUFFIXES:
            continue
        items.append({
            "name": p.name,
            "kind": "gdb" if is_gdb else p.suffix.lower().lstrip("."),
            "size": _safe_size(p),
            "mtime": int(p.stat().st_mtime),
        })
    return JSONResponse({"items": items})


def _safe_size(p: Path) -> int:
    try:
        if p.is_file():
            return p.stat().st_size
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    except Exception:
        return 0


@app.get("/api/areas/{name}/geojson")
def area_geojson(name: str) -> JSONResponse:
    path = _safe_area_path(name)
    try:
        import geopandas as gpd
    except ImportError:
        raise HTTPException(500, "ต้อง pip install geopandas")
    try:
        gdf = gpd.read_file(path)
    except Exception as e:
        raise HTTPException(500, f"อ่านไฟล์ไม่สำเร็จ: {e}")
    try:
        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(4326)
    except Exception:
        pass
    cols = [c for c in gdf.columns if c != gdf.geometry.name]
    if cols:
        gdf = gdf[[gdf.geometry.name]]
    return JSONResponse(json.loads(gdf.to_json()))


def _safe_area_path(name: str) -> Path:
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(400, "ชื่อไฟล์ไม่ถูกต้อง")
    p = (AREAS_DIR / name).resolve()
    try:
        p.relative_to(AREAS_DIR.resolve())
    except ValueError:
        raise HTTPException(400, "path traversal ไม่อนุญาต")
    if not p.exists():
        raise HTTPException(404, f"ไม่พบ {name}")
    return p


@app.get("/api/provinces")
def list_provinces() -> JSONResponse:
    sys.path.insert(0, str(ROOT))
    try:
        from landsmaps.cityplanning.provinces import PROVINCES
    except Exception as e:
        raise HTTPException(500, f"import provinces ไม่สำเร็จ: {e}")
    items = [{"code": c, "name": n} for c, n in PROVINCES.items()]
    return JSONResponse({"items": items})


@app.get("/api/output")
def list_output() -> JSONResponse:
    if not OUTPUT_DIR.exists():
        return JSONResponse({"items": []})
    items = []
    for p in sorted(OUTPUT_DIR.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".shp", ".gpkg", ".geojson"}:
            continue
        try:
            rel = p.relative_to(OUTPUT_DIR).as_posix()
        except ValueError:
            continue
        items.append({
            "path": rel,
            "size": p.stat().st_size,
            "mtime": int(p.stat().st_mtime),
        })
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return JSONResponse({"items": items[:200]})


@app.post("/api/run")
async def run_job(req: RunRequest) -> JSONResponse:
    if req.kind == "parcel":
        if not req.parcel:
            raise HTTPException(400, "ต้องส่ง parcel args")
        cmd = _build_parcel_cmd(req.parcel)
        args = req.parcel.model_dump()
    elif req.kind == "cityplanning":
        if not req.cityplanning:
            raise HTTPException(400, "ต้องส่ง cityplanning args")
        cmd = _build_city_cmd(req.cityplanning)
        args = req.cityplanning.model_dump()
    else:
        raise HTTPException(400, "kind ต้องเป็น parcel หรือ cityplanning")

    job = Job(id=uuid.uuid4().hex[:8], kind=req.kind, cmd=cmd, args=args)
    JOBS[job.id] = job
    asyncio.create_task(_execute_job(job))
    return JSONResponse({"job_id": job.id, "cmd": cmd})


def _build_parcel_cmd(p: ParcelArgs) -> list[str]:
    cmd = [sys.executable, "-u", "fetch_parcels.py"]
    for a in p.areas:
        if "/" in a or "\\" in a:
            raise HTTPException(400, f"ชื่อไฟล์ไม่ถูกต้อง: {a}")
        cmd.append(f"areas/{a}")
    if p.no_detail:
        cmd.append("--no-detail")
    if p.refetch and p.refetch != "none":
        cmd += ["--refetch", p.refetch]
    if p.layer:
        cmd += ["--layer", p.layer]
    if p.name:
        cmd += ["--name", p.name]
    return cmd


def _build_city_cmd(c: CityArgs) -> list[str]:
    if not c.provinces:
        raise HTTPException(400, "ระบุจังหวัดอย่างน้อย 1")
    cmd = [sys.executable, "-u", "fetch_cityplanning.py", *c.provinces]
    if c.area:
        cmd += ["--area", f"areas/{c.area}"]
    if c.layer:
        cmd += ["--layer", c.layer]
    if c.token:
        cmd += ["--token", c.token]
    if c.format and c.format != "both":
        cmd += ["--format", c.format]
    if c.method and c.method != "auto":
        cmd += ["--method", c.method]
    return cmd


_PROGRESS_PATTERNS = [
    re.compile(r"\[\s*(?P<n>\d+)\s*/\s*(?P<total>\d+)\s*\]"),
    re.compile(r"(?P<n>\d+)\s*/\s*(?P<total>\d+)\s*(parcels|แปลง|features)", re.I),
    re.compile(r"(?P<pct>\d+(?:\.\d+)?)\s*%"),
]


def _parse_progress(line: str) -> dict[str, Any] | None:
    for rx in _PROGRESS_PATTERNS:
        m = rx.search(line)
        if not m:
            continue
        gd = m.groupdict()
        if "n" in gd and "total" in gd and gd.get("n") and gd.get("total"):
            n, total = int(gd["n"]), int(gd["total"])
            if total > 0:
                return {"n": n, "total": total, "percent": round(n * 100 / total, 1)}
        if "pct" in gd and gd.get("pct"):
            return {"percent": float(gd["pct"])}
    return None


async def _execute_job(job: Job) -> None:
    job.status = "running"
    job.started_at = time.time()
    job.publish({"type": "status", "status": "running"})
    try:
        proc = await asyncio.create_subprocess_exec(
            *job.cmd,
            cwd=str(ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        job._process = proc
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").rstrip("\n")
            job.lines.append(line)
            if len(job.lines) > 5000:
                job.lines = job.lines[-4000:]
            event: dict[str, Any] = {"type": "line", "line": line}
            prog = _parse_progress(line)
            if prog:
                job.progress.update(prog)
                event["progress"] = job.progress
            job.publish(event)
        job.returncode = await proc.wait()
        job.status = "done" if job.returncode == 0 else "failed"
    except Exception as e:
        job.status = "failed"
        job.lines.append(f"[runner error] {e}")
        logger.exception("job %s crashed", job.id)
    finally:
        job.ended_at = time.time()
        job.publish({"type": "status", "status": job.status, "returncode": job.returncode})


@app.get("/api/jobs")
def list_jobs() -> JSONResponse:
    items = [
        {
            "id": j.id, "kind": j.kind, "status": j.status,
            "started_at": j.started_at, "ended_at": j.ended_at,
            "returncode": j.returncode, "progress": j.progress,
        }
        for j in sorted(JOBS.values(), key=lambda x: x.started_at, reverse=True)[:50]
    ]
    return JSONResponse({"items": items})


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> JSONResponse:
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "ไม่พบ job")
    return JSONResponse({
        "id": j.id, "kind": j.kind, "status": j.status, "cmd": j.cmd,
        "args": j.args, "started_at": j.started_at, "ended_at": j.ended_at,
        "returncode": j.returncode, "progress": j.progress,
        "lines": j.lines[-200:],
    })


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> JSONResponse:
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "ไม่พบ job")
    if j.status != "running" or not j._process:
        return JSONResponse({"ok": False, "status": j.status})
    try:
        j._process.terminate()
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})
    j.status = "cancelled"
    j.publish({"type": "status", "status": "cancelled"})
    return JSONResponse({"ok": True})


@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str, request: Request) -> StreamingResponse:
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "ไม่พบ job")
    q: asyncio.Queue = asyncio.Queue()
    j._subscribers.append(q)

    async def gen() -> AsyncIterator[bytes]:
        for line in j.lines[-100:]:
            yield f"data: {json.dumps({'type': 'line', 'line': line}, ensure_ascii=False)}\n\n".encode("utf-8")
        yield f"data: {json.dumps({'type': 'status', 'status': j.status, 'progress': j.progress}, ensure_ascii=False)}\n\n".encode("utf-8")
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
                    if event.get("type") == "status" and event.get("status") in {"done", "failed", "cancelled"}:
                        break
                except asyncio.TimeoutError:
                    yield b": ping\n\n"
        finally:
            try:
                j._subscribers.remove(q)
            except ValueError:
                pass

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


if (DASHBOARD_DIR / "static").exists():
    app.mount("/static", StaticFiles(directory=DASHBOARD_DIR / "static"), name="static")
