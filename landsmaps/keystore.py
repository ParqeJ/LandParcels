"""เก็บบัญชีและ access token ไว้ไฟล์เดียวที่ Access_Key.txt — เปิดด้วย Notepad อ่านได้

รูปแบบไฟล์ (JSON):
    {"kind": "openid", "user": "...", "pass": "...", "key": "eyJ...", "saved_at": "..."}

ไฟล์แบบเก่า (access token เปล่าบรรทัดเดียว) ยังอ่านได้
ถ้าแก้ไฟล์แล้ว JSON เสีย โปรแกรมจะแจ้งให้แก้ ไม่เดาว่าทั้งไฟล์คือ token
(ไม่งั้นรหัสผ่านในไฟล์จะถูกส่งออกไปเป็น Bearer token)

ดูว่าเก็บอะไรไว้ที่ไหน: python get_token.py --where
"""

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from .config import TOKEN_FILE

FIELDS = ("kind", "user", "pass", "key", "saved_at")    # ลำดับที่เขียนลงไฟล์
JWT_SHAPE = re.compile(r"(?:Bearer\s+)?[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
ICACLS = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "icacls.exe"


class KeyFileError(RuntimeError):
    """ไฟล์ Access_Key.txt อ่านไม่ได้หรือรูปแบบไม่ถูกต้อง"""


def load(path: Path = TOKEN_FILE) -> dict[str, str]:
    """อ่านไฟล์เป็น dict ไม่มีไฟล์ -> {} รูปแบบเสีย -> KeyFileError"""
    try:
        text = path.read_text(encoding="utf-8-sig").strip() if path.exists() else ""
    except (OSError, UnicodeDecodeError) as e:
        raise KeyFileError(f"อ่าน {path.name} ไม่ได้: {e}") from e
    if not text:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if isinstance(data, dict):
        return {str(k): v for k, v in data.items() if isinstance(v, str)}
    if JWT_SHAPE.fullmatch(text):
        return {"key": text}                            # ไฟล์แบบเก่า ใช้ต่อได้ไม่ต้องแปลงมือ
    raise KeyFileError(f"{path.name} ไม่ใช่ JSON ที่ถูกต้อง -> แก้ไฟล์ให้ถูก "
                       f"หรือลบไฟล์แล้วรัน python get_token.py ใหม่")


def save(path: Path = TOKEN_FILE, *, password: str | None = None, **fields: str) -> Path:
    """เขียนทับเฉพาะ field ที่ส่งมา (ของเดิมที่ไม่ได้ส่งยังอยู่) ไฟล์มีรหัสผ่าน -> จำกัดสิทธิ์ให้เจ้าของ"""
    data = {**load(path), **{k: v for k, v in fields.items() if v is not None}}
    if password is not None:
        data["pass"] = password
    data["saved_at"] = datetime.now().isoformat(timespec="seconds")
    ordered = {k: data[k] for k in FIELDS if k in data}
    ordered.update({k: v for k, v in data.items() if k not in FIELDS})

    tmp = path.with_suffix(path.suffix + ".tmp")        # เขียนไฟล์ชั่วคราวก่อน กันไฟล์พังถ้าถูกขัดจังหวะ
    try:
        write_secret(tmp, json.dumps(ordered, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)                     # ถ้าพังกลางทาง อย่าทิ้งไฟล์รหัสผ่านไว้
    restrict(path)
    return path


def write_secret(path: Path, text: str) -> None:
    """สร้างไฟล์ด้วยสิทธิ์จำกัดก่อนเขียน ไม่ให้ความลับอยู่ในไฟล์ที่คนอื่นอ่านได้แม้ชั่วขณะ"""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        restrict(path)                                  # Windows ไม่สนใจ mode ของ os.open -> ต้องสั่งเอง
        fh.write(text)


def restrict(path: Path) -> None:
    """จำกัดสิทธิ์ไฟล์ให้เฉพาะเจ้าของ ทำไม่ได้ก็ข้ามไป (ไม่ถือเป็น error แต่เตือนให้รู้)"""
    if os.name != "nt":
        try:
            path.chmod(0o600)
        except OSError as e:
            print(f"  เตือน: จำกัดสิทธิ์ {path.name} ไม่ได้ ({e})")
        return
    user = os.environ.get("USERNAME")
    if not user:
        return
    try:                                                # เรียกด้วย path เต็ม ไม่ให้ไปเจอ icacls.exe ปลอมใน cwd
        r = subprocess.run([str(ICACLS), str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
                           capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"  เตือน: จำกัดสิทธิ์ {path.name} ไม่ได้ ({e})")
        return
    if r.returncode != 0:
        print(f"  เตือน: จำกัดสิทธิ์ {path.name} ไม่สำเร็จ (icacls คืนค่า {r.returncode}) "
              f"-> ไฟล์นี้มีรหัสผ่าน ตรวจสิทธิ์ด้วยตัวเองด้วย")


def mask(value: str) -> str:
    """ซ่อนค่าลับไว้ตอนแสดงผล บอกแค่ความยาว"""
    return f"{'*' * min(len(value), 9)} ({len(value)} ตัวอักษร)" if value else "-"


def preview(key: str) -> str:
    """แสดง token แบบพอให้รู้ว่าเป็นตัวไหน โดยไม่เผยทั้งก้อน"""
    if len(key) <= 20:
        return mask(key)
    return f"{key[:12]}...{key[-4:]}  ({len(key)} ตัวอักษร)"


def describe(path: Path = TOKEN_FILE) -> str:
    """รายงานว่าเก็บอะไรไว้ที่ไหน (ไม่โชว์รหัสผ่าน / token เต็ม)"""
    data = load(path)
    head = f"ไฟล์:     {path}" + ("" if path.exists() else "  (ยังไม่มีไฟล์นี้)")
    if not data:
        return head + "\n          ยังไม่มีข้อมูล -> รัน python get_token.py เพื่อล็อกอินและสร้างไฟล์"
    rows = [
        f"kind:     {data.get('kind', '-')}",
        f"user:     {data.get('user', '-')}",
        f"pass:     {mask(data.get('pass', ''))}",
        f"key:      {preview(data.get('key', ''))}",
        f"saved_at: {data.get('saved_at', '-')}",
    ]
    return "\n".join([head, *rows])
