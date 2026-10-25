"""ขอ access token ของบัญชี LandsMaps อัตโนมัติ แทนการคัดลอกจาก browser ทุก 24 ชม.

ล็อกอินใหม่ทุกครั้งที่รัน ไม่เช็กว่าของเดิมหมดอายุหรือยัง
บัญชีอ่านได้ 3 ที่ เรียงตามลำดับความสำคัญ: environment variable -> .env -> Access_Key.txt
"""

import os
from pathlib import Path

import requests

from . import keystore, openid
from .api import read_token, token_expiry
from .config import ENV_FILE, HEADERS, JWT_URL, LOGIN_URLS, TIMEOUT, TOKEN_FILE

PASSWORD_KEY = "LANDSMAPS_PASSWORD"
# ชนิดบัญชี (= ชื่อ field ที่ API ต้องการ) -> ชื่อตัวแปรใน .env  เรียงตามลำดับที่ลองหา
ID_KEYS = {
    "openid": "LANDSMAPS_DGA_ID",              # บัญชีทางรัฐ (ปุ่ม "เข้าสู่ระบบด้วย DGA")
    "mail": "LANDSMAPS_MAIL",                  # บัญชีอีเมล (ปุ่ม "เข้าสู่ระบบด้วยอีเมล")
    "personal_id": "LANDSMAPS_PERSONAL_ID",    # บัญชีเลขประจำตัวประชาชน
    "user_name": "LANDSMAPS_USERNAME",         # บัญชีเจ้าหน้าที่กรมที่ดิน (AD)
}
KINDS = tuple(ID_KEYS)


class LoginError(RuntimeError):
    """ล็อกอินไม่สำเร็จ (บัญชีผิด ยังไม่ยืนยันตัวตน หรือ LandsMaps ตอบ error)"""


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
        out[key.strip()] = value.split("#", 1)[0].strip().strip('"').strip("'")
    return out


def credentials(env: dict[str, str] | None = None) -> tuple[str, str, str]:
    """(ชนิดบัญชี, ชื่อผู้ใช้, รหัสผ่าน) — env var -> .env -> Access_Key.txt"""
    if env is None:
        env = {**read_env(), **os.environ}
        if not any((env.get(key) or "").strip() for key in ID_KEYS.values()):
            env = {**saved_credentials(), **env}    # ไม่มีบัญชีใน .env -> ใช้ Access_Key.txt
    for kind, key in ID_KEYS.items():
        user = (env.get(key) or "").strip()
        if user:
            break
    else:
        raise LoginError(f"ไม่พบบัญชีใน {ENV_FILE.name} หรือ {TOKEN_FILE.name} "
                         f"-> ตั้ง {' หรือ '.join(ID_KEYS.values())}")
    password = (env.get(PASSWORD_KEY) or "").strip()
    if not password:
        raise LoginError(f"ไม่พบรหัสผ่าน -> ตั้ง {PASSWORD_KEY} ใน {ENV_FILE.name} "
                         f"หรือ \"pass\" ใน {TOKEN_FILE.name}")
    return kind, user, password


def saved_credentials() -> dict[str, str]:
    """บัญชีใน Access_Key.txt ในรูปแบบเดียวกับ .env ไม่มี -> {}"""
    saved = keystore.load()
    if not (saved.get("user") and saved.get("pass")):
        return {}
    kind = saved.get("kind") or "openid"
    if kind not in ID_KEYS:
        raise LoginError(f"kind '{kind}' ใน {TOKEN_FILE.name} ไม่ถูกต้อง "
                         f"(ใช้ได้: {', '.join(KINDS)})")
    return {ID_KEYS[kind]: saved["user"], PASSWORD_KEY: saved["pass"]}


def has_credentials() -> bool:
    try:
        credentials()
    except LoginError:
        return False
    return True


def write_env(updates: dict[str, str], path: Path = ENV_FILE) -> Path:
    """เขียนบัญชีลง .env ด้วย (เก็บไว้ 2 ที่) บรรทัดเดิมที่มี key นี้ถูกแทนที่ ที่ไม่มีถูกต่อท้าย"""
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    left = dict(updates)
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else ""
        if key in left:
            lines[i] = f"{key}={left.pop(key)}"
    if not lines:
        lines = ["# บัญชี LandsMaps สำหรับล็อกอินอัตโนมัติ — ห้าม commit (อยู่ใน .gitignore แล้ว)"]
    lines += [f"{k}={v}" for k, v in left.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    keystore.restrict(path)
    return path


def save_credentials(kind: str, user: str, password: str, token: str) -> None:
    """บันทึกบัญชีและ token ไว้ทั้ง Access_Key.txt และ .env"""
    keystore.save(kind=kind, user=user, key=token, **{"pass": password})
    write_env({ID_KEYS[kind]: user, PASSWORD_KEY: password})


def login(kind: str, user: str, password: str) -> str:
    """ล็อกอิน LandsMaps ด้วยบัญชีของกรมที่ดินเอง คืน access token ของบัญชี (อายุ 24 ชม.)"""
    if kind not in LOGIN_URLS:
        raise LoginError(f"ไม่รู้จักชนิดบัญชี '{kind}' (ใช้ได้: {', '.join(LOGIN_URLS)})")
    s = requests.Session()
    s.headers.update(HEADERS)

    r = s.get(JWT_URL, timeout=TIMEOUT)             # token สาธารณะ ใช้เป็นใบเบิกทางของคำขอ login
    r.raise_for_status()
    s.headers["Authorization"] = "Bearer " + r.json()["result"][0]["access_token"]

    r = s.post(LOGIN_URLS[kind], json={kind: user, "user_password": password}, timeout=TIMEOUT)
    r.raise_for_status()
    body = r.json()
    if body.get("error") or not body.get("result"):
        raise LoginError(" ".join((body.get("message") or "ล็อกอินไม่สำเร็จ").split()))
    if body.get("actived") is False:
        raise LoginError("บัญชียังไม่ยืนยันตัวตน -> ล็อกอินในเว็บ LandsMaps กรอก OTP ให้ผ่านก่อน 1 ครั้ง")
    token = (body["result"][0] or {}).get("access_token")
    if not token:
        raise LoginError("ล็อกอินผ่านแต่ LandsMaps ไม่ได้ส่ง access_token กลับมา")
    return token


def login_any(kind: str, user: str, password: str) -> str:
    """ล็อกอินตามชนิดบัญชี — 'openid' ไปทาง DGA ที่เหลือใช้ endpoint ของกรมที่ดิน"""
    if kind == "openid":
        try:
            return openid.login_openid(user, password)
        except openid.OpenIDError as e:
            raise LoginError(str(e)) from e
    return login(kind, user, password)


def save_token(token: str, path: Path = TOKEN_FILE) -> Path:
    return keystore.save(path, key=token)


def describe(token: str) -> str:
    exp = token_expiry(token)
    return f"หมดอายุ {exp:%d/%m/%Y %H:%M}" if exp else "อ่านวันหมดอายุไม่ได้"


def ensure_token() -> str:
    """ล็อกอินใหม่เสมอแล้วบันทึกทับ ไม่มีบัญชีให้ล็อกอิน -> คืน token เดิมที่มีอยู่"""
    if not has_credentials():
        return read_token()                     # ให้ check_token ว่ากันต่อว่าของเดิมยังใช้ได้ไหม
    kind, user, password = credentials()
    token = login_any(kind, user, password)
    save_credentials(kind, user, password, token)
    print(f"  ล็อกอิน LandsMaps สำเร็จ ({ID_KEYS[kind]}={user}) -> เขียน {TOKEN_FILE.name} แล้ว "
          f"({describe(token)})")
    return token
