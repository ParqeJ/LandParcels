"""สถานะการดึงรายพื้นที่ -> cache/status/<name>.json ให้ dashboard อ่าน (ไม่มีผลกับ Shapefile ผลลัพธ์)

state: running · done (ครบ) · partial (ยังค้าง) · quota (โควตาเต็ม) · error · cancelled
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

STATUS_DIRNAME = "status"


def status_file(cache_dir: Path, name: str) -> Path:
    return cache_dir / STATUS_DIRNAME / f"{name}.json"


def read_status(path: Path) -> dict[str, Any] | None:
    """None ถ้าไม่มีไฟล์ / อ่านไม่ได้ / ไม่ใช่ JSON object"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_status(cache_dir: Path, name: str, **fields: Any) -> dict[str, Any]:
    """รวมกับค่าเดิมแล้วเขียนทับแบบ atomic (เขียนไฟล์ชั่วคราวก่อน) — dashboard จะไม่เจอไฟล์ครึ่ง ๆ"""
    path = status_file(cache_dir, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {**(read_status(path) or {}), **fields, "name": name, "updated_at": time.time()}
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return data


def pid_alive(pid: Any) -> bool:
    """process เลขนี้ยังรันอยู่ไหม (ไว้แยก "กำลังรัน" ออกจาก "รันค้าง/ถูกปิดกลางทาง")"""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if sys.platform == "win32":
        return _win_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:         # มีอยู่ แต่เป็นของ user อื่น
        return True
    except OverflowError:
        return False
    return True


def _win_pid_alive(pid: int) -> bool:
    # ห้ามใช้ os.kill(pid, 0) บน Windows: มันเรียก TerminateProcess = ฆ่า process ทิ้ง
    import ctypes
    from ctypes import wintypes

    query_limited, still_active, access_denied = 0x1000, 259, 5
    if pid > 0xFFFFFFFF:
        return False
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = k32.OpenProcess(query_limited, False, pid)
    if not handle:
        return ctypes.get_last_error() == access_denied
    try:
        code = wintypes.DWORD()
        return bool(k32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == still_active
    finally:
        k32.CloseHandle(handle)
