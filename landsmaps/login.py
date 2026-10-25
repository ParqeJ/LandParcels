"""ขอ access token ของบัญชี LandsMaps อัตโนมัติผ่าน DGA (บัญชีทางรัฐ) แทนการคัดลอกจาก browser ทุก 24 ชม.

ล็อกอินใหม่ทุกครั้งที่รัน ไม่เช็กว่าของเดิมหมดอายุหรือยัง
บัญชีอ่านได้ 3 ที่ เรียงตามลำดับความสำคัญ: environment variable -> .env -> Access_Key.txt
"""

import os
import re
from pathlib import Path

import requests

from . import keystore, openid
from .api import read_token, token_expiry
from .config import ENV_FILE, TOKEN_FILE

ID_KEY = "LANDSMAPS_DGA_ID"                 # บัญชีทางรัฐ (ปุ่ม "เข้าสู่ระบบด้วย DGA")
PASSWORD_KEY = "LANDSMAPS_PASSWORD"
KIND = "openid"                             # ค่า "kind" ใน Access_Key.txt (รองรับแค่บัญชี DGA)
DOUBLE_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')
INLINE_COMMENT = re.compile(r"\s+#")        # # ที่มีช่องว่างนำหน้า = คอมเมนต์ท้ายบรรทัด
NEEDS_QUOTE = re.compile(r"[\s#'\"]")


class LoginError(RuntimeError):
    """ล็อกอินไม่สำเร็จ (บัญชีผิด บัญชีเปิด OTP เน็ตล่ม หรือ DGA/LandsMaps ตอบ error)"""


def parse_value(raw: str) -> str:
    """ค่าหลัง = ใน .env: อยู่ในเครื่องหมายคำพูด -> เอาตามนั้นทั้งหมด (# ข้างในเป็นส่วนของค่า)
    ไม่มีเครื่องหมายคำพูด -> ตัดคอมเมนต์ที่ขึ้นต้นด้วย " #" (รหัสผ่าน abc#123 จึงไม่ถูกตัด)"""
    raw = raw.strip()
    if raw[:1] == "'" and "'" in raw[1:]:
        return raw[1:raw.index("'", 1)]
    m = DOUBLE_QUOTED.match(raw)
    if m:
        return re.sub(r'\\(["\\])', r"\1", m.group(1))
    return INLINE_COMMENT.split(raw, maxsplit=1)[0]


def quote_value(value: str) -> str:
    """ค่าที่มี # ช่องว่าง หรือเครื่องหมายคำพูด -> ครอบด้วยเครื่องหมายคำพูด ให้ parse_value อ่านกลับได้ตรงเดิม"""
    if not NEEDS_QUOTE.search(value):
        return value
    if "'" not in value:
        return f"'{value}'"
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def read_env(path: Path = ENV_FILE) -> dict[str, str]:
    """อ่าน .env แบบง่าย (KEY=value บรรทัดละตัว, # = คอมเมนต์) ไม่มีไฟล์ -> {}"""
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = parse_value(value)
    return out


def credentials(env: dict[str, str] | None = None) -> tuple[str, str]:
    """(ชื่อผู้ใช้ DGA, รหัสผ่าน) — env var -> .env -> Access_Key.txt"""
    if env is None:
        env = {**read_env(), **os.environ}
        if not (env.get(ID_KEY) or "").strip():
            env = {**saved_credentials(), **env}    # ไม่มีบัญชีใน .env -> ใช้ Access_Key.txt
    user = (env.get(ID_KEY) or "").strip()
    if not user:
        raise LoginError(f"ไม่พบบัญชีใน {ENV_FILE.name} หรือ {TOKEN_FILE.name} "
                         f"-> ตั้ง {ID_KEY} และ {PASSWORD_KEY}")
    password = (env.get(PASSWORD_KEY) or "").strip()
    if not password:
        raise LoginError(f"ไม่พบรหัสผ่าน -> ตั้ง {PASSWORD_KEY} ใน {ENV_FILE.name} "
                         f"หรือ \"pass\" ใน {TOKEN_FILE.name}")
    return user, password


def saved_credentials() -> dict[str, str]:
    """บัญชีใน Access_Key.txt ในรูปแบบเดียวกับ .env ไม่มี -> {}"""
    saved = keystore.load()
    if not (saved.get("user") and saved.get("pass")):
        return {}
    kind = saved.get("kind") or KIND
    if kind != KIND:
        raise LoginError(f"kind '{kind}' ใน {TOKEN_FILE.name} ใช้ไม่ได้แล้ว "
                         f"-> รองรับเฉพาะบัญชี DGA (แก้เป็น \"kind\": \"{KIND}\")")
    return {ID_KEY: saved["user"], PASSWORD_KEY: saved["pass"]}


def has_credentials() -> bool:
    try:
        credentials()
    except LoginError:
        return False
    return True


def write_env(updates: dict[str, str], path: Path = ENV_FILE) -> Path:
    """เขียนบัญชีลง .env ด้วย (เก็บไว้ 2 ที่) บรรทัดเดิมที่มี key นี้ถูกแทนที่ ที่ไม่มีถูกต่อท้าย"""
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    left = {k: quote_value(v) for k, v in updates.items()}
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else ""
        if key in left:
            lines[i] = f"{key}={left.pop(key)}"
    if not lines:
        lines = ["# บัญชี LandsMaps สำหรับล็อกอินอัตโนมัติ — ห้าม commit (อยู่ใน .gitignore แล้ว)"]
    lines += [f"{k}={v}" for k, v in left.items()]
    keystore.write_secret(path, "\n".join(lines) + "\n")
    return path


def save_credentials(user: str, password: str, token: str) -> None:
    """บันทึกบัญชีและ token ไว้ทั้ง Access_Key.txt และ .env"""
    keystore.save(kind=KIND, user=user, key=token, **{"pass": password})
    write_env({ID_KEY: user, PASSWORD_KEY: password})


def network_error(e: requests.RequestException) -> str:
    """สาเหตุแบบย่อ ไม่ใส่ URL เต็ม เพราะ URL ระหว่างล็อกอินมี token อยู่ข้างใน"""
    if e.response is not None:
        return f"{openid.host_of(e.response.url)} ตอบ HTTP {e.response.status_code}"
    return type(e).__name__                     # ConnectionError, ReadTimeout, ...


def login(user: str, password: str) -> str:
    """ล็อกอิน LandsMaps ผ่าน DGA คืน access token ของบัญชี (อายุ 24 ชม.)"""
    try:
        return openid.login_openid(user, password)
    except openid.OpenIDError as e:
        raise LoginError(str(e)) from e
    except requests.RequestException as e:     # เน็ตล่ม หรือเซิร์ฟเวอร์ตอบ 5xx
        raise LoginError(f"ติดต่อเซิร์ฟเวอร์ไม่ได้ ({network_error(e)})") from e


def save_token(token: str, path: Path = TOKEN_FILE) -> Path:
    return keystore.save(path, key=token)


def describe(token: str) -> str:
    exp = token_expiry(token)
    return f"หมดอายุ {exp:%d/%m/%Y %H:%M}" if exp else "อ่านวันหมดอายุไม่ได้"


def ensure_token() -> str:
    """ล็อกอินใหม่เสมอแล้วบันทึกทับ ไม่มีบัญชีให้ล็อกอิน -> คืน token เดิมที่มีอยู่"""
    if not has_credentials():
        return read_token()                     # ให้ check_token ว่ากันต่อว่าของเดิมยังใช้ได้ไหม
    user, password = credentials()
    token = login(user, password)
    save_credentials(user, password, token)
    print(f"  ล็อกอิน LandsMaps สำเร็จ ({ID_KEY}={user}) -> เขียน {TOKEN_FILE.name} แล้ว "
          f"({describe(token)})")
    return token
