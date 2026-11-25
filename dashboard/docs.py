"""คู่มือ (README.md + docs/*.md) สำหรับหน้า 📖 คู่มือ ของ dashboard — ส่ง markdown ดิบ ให้ browser render เอง"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/api/docs", tags=["docs"])

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
INDEX = "index"                     # = README.md ที่ root (สารบัญหลัก)
ORDER = (INDEX, "setup", "dashboard", "parcel", "cityplanning", "schema")
NAME_RE = re.compile(r"^[a-z0-9_-]+$")


def doc_path(name: str) -> Path:
    """ชื่อ doc -> ไฟล์ .md (อ่านได้เฉพาะ README.md กับไฟล์ชั้นบนสุดของ docs/ เท่านั้น)"""
    if not NAME_RE.fullmatch(name):
        raise HTTPException(400, "ชื่อคู่มือไม่ถูกต้อง")
    p = ROOT / "README.md" if name == INDEX else DOCS_DIR / f"{name}.md"
    if not p.is_file():
        raise HTTPException(404, f"ไม่พบคู่มือ {name}")
    return p


def _title(p: Path) -> str:
    with p.open(encoding="utf-8") as f:
        for line in f:
            if line.startswith("# "):
                return line[2:].strip()
    return p.stem


def _names() -> list[str]:
    found = {p.stem for p in DOCS_DIR.glob("*.md") if NAME_RE.fullmatch(p.stem)} if DOCS_DIR.is_dir() else set()
    if (ROOT / "README.md").is_file():
        found.add(INDEX)
    return [n for n in ORDER if n in found] + sorted(found - set(ORDER))


@router.get("")
def list_docs() -> dict[str, Any]:
    return {"items": [{"name": n, "title": _title(doc_path(n))} for n in _names()]}


@router.get("/{name}", response_class=PlainTextResponse)
def get_doc(name: str) -> PlainTextResponse:
    return PlainTextResponse(doc_path(name).read_text(encoding="utf-8"), media_type="text/markdown; charset=utf-8")
