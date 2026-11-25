"""รับ/ลบไฟล์ขอบเขตใน areas/ และส่งผลลัพธ์ใน output/ ออกทางหน้า dashboard (ไม่ต้องคัดลอกไฟล์เอง)"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from landsmaps import config
from landsmaps.area import is_area_file, read_polygons

router = APIRouter(prefix="/api", tags=["files"])

AREAS_DIR = config.AREAS_DIR
OUTPUT_DIR = config.OUTPUT_DIR
REPLACED_DIR = ".replaced"          # ขึ้นต้นด้วยจุด -> ไม่โผล่ในรายการ areas และ fetch_parcels ไม่อ่าน
DELETED_DIR = ".deleted"            # ไฟล์ที่กดลบจากหน้า dashboard (กู้คืนได้ ไม่ลบทิ้งจริง)

SHP_PARTS = {".shp", ".shx", ".dbf", ".prj", ".cpg"}
# นามสกุลคู่ของ shapefile ทั้งหมด (รวม index / metadata ของ ArcGIS-QGIS) — ใช้แยก "a.shp" ออกจาก "a.b.shp"
SHP_SIDECARS = {"shp", "shx", "dbf", "prj", "cpg", "sbn", "sbx", "qix", "fix", "xml", "qmd",
                "aih", "ain", "atx", "ixs", "mxs", "avl", "qpj"}
SHP_REQUIRED = (".shx", ".dbf")
AREA_FILE_SUFFIXES = set(config.AREA_SUFFIXES) | SHP_PARTS
UPLOAD_SUFFIXES = AREA_FILE_SUFFIXES | {".zip"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_UNZIPPED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ZIP_MEMBERS = 5000
CHUNK = 1024 * 1024
BAD_CHARS = set('<>:"/\\|?*')
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
SKIP_SUFFIX = ".lock"               # ArcGIS/QGIS lock file ไม่ใช่ข้อมูล


# ─────────────────────────── path ที่ปลอดภัย ───────────────────────────

def clean_name(raw: str | None) -> str:
    """ชื่อไฟล์จาก browser -> ชื่อเปล่า ๆ ที่เขียนบน Windows ได้ (ภาษาไทยใช้ได้)"""
    name = PurePosixPath((raw or "").replace("\\", "/")).name.strip()
    bad = (not name or name.startswith(".")
           or any(c in BAD_CHARS or ord(c) < 32 for c in name)
           or name.split(".")[0].upper() in RESERVED)
    if bad:
        raise HTTPException(400, f"ชื่อไฟล์ใช้ไม่ได้: {raw!r}")
    return name


def safe_child(base: Path, rel: str) -> Path:
    """path ใต้ base เท่านั้น (กัน ../ และ path เต็ม) ไม่มีอยู่จริง -> 404"""
    root = base.resolve()
    p = (root / rel).resolve() if rel else root
    if not p.is_relative_to(root):
        raise HTTPException(400, "path อยู่นอกโฟลเดอร์ที่อนุญาต")
    if not p.exists():
        raise HTTPException(404, f"ไม่พบ {rel or base.name}")
    return p


def _suffix(name: str) -> str:
    return PurePosixPath(name).suffix.lower()


# ─────────────────────────── upload ───────────────────────────

def _save_stream(src: BinaryIO, dest: Path, budget: list[int]) -> None:
    """เขียนทีละก้อน ตัดทิ้งทันทีเมื่อรวมทุกไฟล์เกิน MAX_UPLOAD_BYTES"""
    with dest.open("wb") as out:
        while chunk := src.read(CHUNK):
            budget[0] -= len(chunk)
            if budget[0] < 0:
                raise HTTPException(413, f"ไฟล์รวมกันใหญ่เกิน {MAX_UPLOAD_BYTES // 2**20} MB")
            out.write(chunk)


def zip_dest(member: str) -> PurePosixPath | None:
    """ตำแหน่งใน areas/ ของไฟล์ใน zip — .gdb เก็บทั้งโฟลเดอร์, ไฟล์ขอบเขตวางชั้นบนสุด, อื่น ๆ ข้าม"""
    norm = member.replace("\\", "/")
    parts = PurePosixPath(norm).parts
    unsafe = (norm.startswith("/") or any(p in ("..", ".") for p in parts)
              or any(c in '<>:"|?*' or ord(c) < 32 for c in norm))
    if unsafe:
        raise HTTPException(400, f"zip มี path ที่ไม่ปลอดภัย: {member!r}")
    if not parts or parts[0] == "__MACOSX" or norm.endswith("/"):
        return None
    for i, part in enumerate(parts):
        if part.lower().endswith(".gdb"):
            return PurePosixPath(*parts[i:]) if i + 1 < len(parts) else None
    name = parts[-1]
    if name.startswith(".") or _suffix(name) not in AREA_FILE_SUFFIXES:
        return None
    return PurePosixPath(name)


def _extract_zip(zpath: Path, staging: Path) -> None:
    with zipfile.ZipFile(zpath) as z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        if len(infos) > MAX_ZIP_MEMBERS:
            raise HTTPException(413, f"zip มีไฟล์มากเกิน {MAX_ZIP_MEMBERS} ไฟล์")
        if sum(i.file_size for i in infos) > MAX_UNZIPPED_BYTES:
            raise HTTPException(413, "zip แตกออกมาแล้วใหญ่เกิน 2 GB")
        for info in infos:
            rel = zip_dest(info.filename)
            if rel is None:
                continue
            dest = (staging / rel).resolve()
            if not dest.is_relative_to(staging.resolve()):
                raise HTTPException(400, f"zip มี path ที่ไม่ปลอดภัย: {info.filename!r}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, dest.open("wb") as out:
                shutil.copyfileobj(src, out, CHUNK)


def _check_shapefiles(entries: list[Path]) -> None:
    names = {p.name.lower() for p in entries}
    for p in entries:
        suf = _suffix(p.name)
        stem = p.name[: -len(suf)].lower() if suf else p.name.lower()
        if suf == ".shp":
            missing = [s for s in SHP_REQUIRED if stem + s not in names]
            if missing:
                raise HTTPException(400, f"{p.name}: ต้องอัปโหลด {' '.join(missing)} มาพร้อมกัน")
        elif suf in SHP_PARTS and stem + ".shp" not in names:
            raise HTTPException(400, f"{p.name}: ไม่มีไฟล์ {stem}.shp มาด้วย")


def _move_aside(p: Path) -> str:
    """ไฟล์เดิมที่ถูกแทนที่ -> areas/.replaced/<เวลา>_<ชื่อ> (กู้คืนได้ ไม่ลบทิ้ง)"""
    trash = AREAS_DIR / REPLACED_DIR
    trash.mkdir(exist_ok=True)
    dest = trash / f"{time.strftime('%Y%m%d_%H%M%S')}_{p.name}"
    os.replace(p, dest)
    return dest.relative_to(AREAS_DIR).as_posix()


def _check_area(p: Path) -> dict[str, Any]:
    """ลองอ่านด้วยตัวอ่านเดียวกับ fetch_parcels.py — อ่านไม่ได้ก็ยังเก็บไฟล์ไว้ แต่เตือน"""
    kind = "gdb" if p.is_dir() else _suffix(p.name).lstrip(".")
    try:
        read_polygons(p)
    except Exception as e:  # noqa: BLE001 - ข้อความจาก GDAL/ValueError แสดงให้ผู้ใช้ดูตรง ๆ
        return {"name": p.name, "kind": kind, "ok": False, "message": str(e)[:300]}
    return {"name": p.name, "kind": kind, "ok": True, "message": "อ่านขอบเขตได้"}


@router.post("/areas/upload")
def upload_areas(files: list[UploadFile] = File(...), overwrite: bool = Form(False)) -> dict[str, Any]:
    AREAS_DIR.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".upload_", dir=AREAS_DIR))
    try:
        budget = [MAX_UPLOAD_BYTES]
        zips = staging / ".zips"
        for f in files:
            name = clean_name(f.filename)
            if _suffix(name) not in UPLOAD_SUFFIXES:
                raise HTTPException(400, f"{name}: ไม่รองรับไฟล์ชนิดนี้ "
                                         f"(รองรับ {' '.join(sorted(UPLOAD_SUFFIXES))})")
            if _suffix(name) == ".zip":
                zips.mkdir(exist_ok=True)
                _save_stream(f.file, zips / name, budget)
                try:
                    _extract_zip(zips / name, staging)
                except zipfile.BadZipFile:
                    raise HTTPException(400, f"{name}: ไฟล์ zip เสีย") from None
            else:
                _save_stream(f.file, staging / name, budget)

        entries = sorted(p for p in staging.iterdir() if not p.name.startswith("."))
        if not entries:
            raise HTTPException(400, "ไม่พบไฟล์ขอบเขตที่ใช้ได้ (zip ต้องมี .gdb / .kmz / .shp ฯลฯ อยู่ข้างใน)")
        _check_shapefiles(entries)

        conflicts = [p.name for p in entries if (AREAS_DIR / p.name).exists()]
        if conflicts and not overwrite:
            raise HTTPException(409, {"message": "มีไฟล์ชื่อนี้อยู่แล้วใน areas/", "conflicts": conflicts})

        replaced = [_move_aside(AREAS_DIR / n) for n in conflicts]
        moved = []
        for p in entries:
            dest = AREAS_DIR / p.name
            os.replace(p, dest)
            moved.append(dest)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    saved = [_check_area(p) for p in moved if is_area_file(p)]
    return {"saved": saved, "replaced": replaced}


# ─────────────────────────── ลบ (ย้ายไป .deleted/) ───────────────────────────

def area_path(name: str) -> Path:
    """ชื่อ area ชั้นบนสุดของ areas/ เท่านั้น — ห้ามมี path ปน, ต้องเป็นไฟล์ขอบเขตจริง"""
    if clean_name(name) != name:
        raise HTTPException(400, f"ชื่อไฟล์ใช้ไม่ได้: {name!r}")
    p = AREAS_DIR / name
    if not p.exists():
        raise HTTPException(404, f"ไม่พบ {name} ใน areas/")
    if not is_area_file(p):
        raise HTTPException(400, f"{name} ไม่ใช่ไฟล์ขอบเขต")
    return p


def area_parts(p: Path) -> list[Path]:
    """ทุกไฟล์ที่ประกอบเป็น area เดียว: shapefile = ทั้งชุด (.shx .dbf ...), .gdb = ทั้งโฟลเดอร์"""
    return _shapefile_set(p) if _suffix(p.name) == ".shp" else [p]


def _new_trash_dir() -> Path:
    base = AREAS_DIR / DELETED_DIR
    stamp = time.strftime("%Y%m%d_%H%M%S")
    trash, n = base / stamp, 1
    while trash.exists():
        n += 1
        trash = base / f"{stamp}_{n}"
    trash.mkdir(parents=True)
    return trash


def trash_areas(names: list[str]) -> str:
    """ย้าย areas ที่เลือกไป areas/.deleted/<เวลา>/ ทั้งชุด — ย้ายไม่ได้แม้ไฟล์เดียว (เช่นเปิดค้างใน
    ArcGIS/QGIS) จะย้ายที่ย้ายไปแล้วกลับคืนทั้งหมด ไม่ปล่อย shapefile ครึ่งชุด"""
    parts = [part for p in (area_path(n) for n in dict.fromkeys(names)) for part in area_parts(p)]
    trash = _new_trash_dir()
    moved: list[tuple[Path, Path]] = []
    for part in parts:
        dest = trash / part.name
        try:
            os.replace(part, dest)
        except OSError as e:
            for src, back in reversed(moved):
                os.replace(back, src)
            trash.rmdir()  # ว่างแล้วหลังย้ายกลับ — rmdir ลบได้เฉพาะโฟลเดอร์ว่าง กันลบข้อมูลพลาด
            raise HTTPException(409, f"ย้าย {part.name} ไม่ได้ — อาจเปิดค้างอยู่ใน ArcGIS/QGIS "
                                     f"ปิดโปรแกรมก่อนแล้วลองใหม่ ({e.strerror or e})") from None
        moved.append((part, dest))
    return trash.relative_to(AREAS_DIR).as_posix()


# ─────────────────────────── download ───────────────────────────

def _shapefile_set(shp: Path) -> list[Path]:
    """.shp + ไฟล์คู่ทั้งหมด (.shx .dbf .prj .cpg .shp.xml ...) ยกเว้น lock file
    (ไม่รวมชุดอื่นที่ชื่อขึ้นต้นเหมือนกัน เช่น a.shp ไม่เอา a.b.shp)"""
    prefix = shp.stem.lower() + "."

    def belongs(name: str) -> bool:
        low = name.lower()
        return (low.startswith(prefix) and not low.endswith(SKIP_SUFFIX)
                and low[len(prefix):].split(".")[0] in SHP_SIDECARS)

    return sorted(f for f in shp.parent.iterdir() if f.is_file() and belongs(f.name))


def _zip_response(files: list[Path], base: Path, filename: str) -> FileResponse:
    fd, tmp = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f.relative_to(base).as_posix())
    return FileResponse(tmp, media_type="application/zip", filename=filename,
                        background=BackgroundTask(os.unlink, tmp))


@router.get("/output/download")
def download_output(path: str = "") -> FileResponse:
    """ไฟล์ .shp -> zip ทั้งชุด · โฟลเดอร์ -> zip ทั้งโฟลเดอร์ · .gpkg/.geojson -> ส่งไฟล์ตรง ๆ"""
    p = safe_child(OUTPUT_DIR, path)
    if p.is_dir():
        files = sorted(f for f in p.rglob("*") if f.is_file() and not f.name.lower().endswith(SKIP_SUFFIX))
        if not files:
            raise HTTPException(404, "โฟลเดอร์นี้ไม่มีไฟล์")
        return _zip_response(files, p.parent, f"{p.name}.zip")
    if p.suffix.lower() == ".shp":
        return _zip_response(_shapefile_set(p), p.parent, f"{p.stem}.zip")
    return FileResponse(p, filename=p.name)


# ─────────────────────────── เปิดโฟลเดอร์ใน Explorer ───────────────────────────

class RevealIn(BaseModel):
    root: Literal["areas", "output"] = "output"
    path: str = ""


@router.post("/reveal")
def reveal(body: RevealIn) -> dict[str, Any]:
    if os.name != "nt":
        raise HTTPException(501, "เปิด Explorer ได้เฉพาะ Windows")
    base = AREAS_DIR if body.root == "areas" else OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    p = safe_child(base, body.path)
    explorer = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "explorer.exe"
    args = [str(explorer), f"/select,{p}"] if p.is_file() else [str(explorer), str(p)]
    subprocess.Popen(args)  # noqa: S603 - path ถูกจำกัดให้อยู่ใต้ areas/ หรือ output/ แล้ว
    return {"ok": True, "path": str(p)}
