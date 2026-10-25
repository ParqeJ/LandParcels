"""API รายละเอียดแปลงของ LandsMaps + access token + cache รายแปลง"""

import base64
import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests

from . import keystore
from .config import (API, FREE_QUOTA, HEADERS, JWT_URL, LOGIN_QUOTA, RETRY_WAITS, TIMEOUT,
                     TOKEN_ENV, TOKEN_FILE)


class QuotaExceeded(RuntimeError):
    """LandsMaps ตอบ error (เกินโควตาค้นหาต่อวัน หรือ token ถูกปฏิเสธ)"""


# ─────────────────────────── token ───────────────────────────

def read_token(token_file: Path = TOKEN_FILE) -> str:
    """env LANDSMAPS_TOKEN ก่อน แล้วค่อย key ในไฟล์ Access_Key.txt ไม่มีทั้งคู่ -> "" (ไม่ล็อกอิน)"""
    tok = os.environ.get(TOKEN_ENV, "").strip()
    if not tok:
        tok = keystore.load(token_file).get("key", "").strip()
    return tok.removeprefix("Bearer ").strip()


def token_expiry(tok: str) -> datetime | None:
    """เวลาหมดอายุ (exp) ของ JWT หรือ None ถ้าอ่านไม่ได้"""
    try:
        p = tok.split(".")[1]
        exp = json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))["exp"]
        return datetime.fromtimestamp(int(exp))
    except (IndexError, KeyError, ValueError, TypeError):
        return None


def check_token(tok: str) -> str:
    """คืนข้อความสถานะ หรือ raise ถ้า token หมดอายุแล้ว"""
    if not tok:
        return f"LandsMaps: ไม่ล็อกอิน (ค้นรายละเอียดได้{FREE_QUOTA} แปลง/วัน)"
    exp = token_expiry(tok)
    if exp is None:
        return f"LandsMaps: ใช้ access token ของบัญชี (ค้นรายละเอียดได้{LOGIN_QUOTA} แปลง/วัน)"
    if exp < datetime.now():
        raise QuotaExceeded(f"access token หมดอายุแล้วเมื่อ {exp:%d/%m/%Y %H:%M} "
                            f"-> รัน python get_token.py เพื่อล็อกอินใหม่")
    return (f"LandsMaps: ใช้ access token ของบัญชี (หมดอายุ {exp:%d/%m/%Y %H:%M}, "
            f"ค้นรายละเอียดได้{LOGIN_QUOTA} แปลง/วัน)")


# ─────────────────────────── API ───────────────────────────

class LandsMapsAPI:
    def __init__(self, token: str = ""):
        self.token = token
        self.s = requests.Session()
        self.s.headers.update(HEADERS)
        self._authorize()

    def _authorize(self):
        if self.token:
            self.s.headers["Authorization"] = "Bearer " + self.token
            return
        r = self.s.get(JWT_URL, timeout=TIMEOUT)
        r.raise_for_status()
        self.s.headers["Authorization"] = "Bearer " + r.json()["result"][0]["access_token"]

    def _get_first(self, url: str) -> dict | None:
        for wait in (*RETRY_WAITS, None):
            try:
                r = self.s.get(url, timeout=TIMEOUT)
                if r.status_code == 401:
                    if self.token:
                        raise QuotaExceeded("access token ถูกปฏิเสธ (401) "
                                            "-> รัน python get_token.py เพื่อล็อกอินใหม่")
                    self._authorize()       # token สาธารณะหมดอายุ -> ขอใหม่แล้วลองอีกรอบ
                    raise requests.HTTPError("401 token expired")
                r.raise_for_status()
                body = r.json()
                if body.get("error"):
                    raise QuotaExceeded(" ".join((body.get("message") or "").split()))
                res = body.get("result") or []
                return res[0] if res and res[0] else None
            except (requests.RequestException, ValueError) as e:
                if wait is None:
                    raise
                print(f"    retry in {wait}s ({e})")
                time.sleep(wait)
        return None

    def parcel_at(self, lat: float, lon: float) -> dict | None:
        """รายละเอียดแปลงที่ตำแหน่ง (เลขโฉนดถูกซ่อนเป็น xxxx19)"""
        return self._get_first(f"{API}/LandsMaps/GetParcelByDouleClick/{lat:.8f}/{lon:.8f}")

    def parcel_by_no(self, prov: str, amphur: str, parcel_no) -> dict | None:
        """รายละเอียดแปลงจากเลขโฉนด (รหัสจังหวัด 2 หลัก, อำเภอ 2 หลัก)"""
        return self._get_first(f"{API}/LandsMaps/GetParcelByParcelNo/{prov}/{amphur}/{parcel_no}")


# ─────────────────────────── cache รายแปลง ───────────────────────────

def load_detail_cache(path: Path) -> dict:
    """{parcel_seq: info} จากไฟล์ .jsonl (info = None คือค้นแล้วไม่พบ)"""
    if not path.exists():
        return {}
    out = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            out[rec["seq"]] = rec["info"]
        except (ValueError, KeyError):              # บรรทัดเขียนไม่จบ (โปรแกรมถูกหยุดกลางทาง) -> ข้าม
            print(f"  ข้ามบรรทัด {n} ที่เสียใน {path.name} (แปลงนั้นจะถูกดึงใหม่)")
    return out


def open_detail_cache(path: Path):
    """เปิดไฟล์ cache แบบต่อท้าย ถ้าบรรทัดสุดท้ายเขียนไม่จบ ขึ้นบรรทัดใหม่ก่อน"""
    needs_newline = path.exists() and path.stat().st_size > 0 and not path.read_bytes().endswith(b"\n")
    fh = path.open("a", encoding="utf-8")
    if needs_newline:
        fh.write("\n")
    return fh
