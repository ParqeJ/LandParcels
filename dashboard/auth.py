"""บัญชี LandsMaps ของ dashboard — ใช้ landsmaps.login ตัวเดียวกับ get_token.py

dashboard ไม่มีระบบสมาชิกของตัวเอง: รหัสผ่านถูกส่งต่อไปที่ DGA (connect.egov.go.th)
และ LandsMaps (landsmaps.dol.go.th) เท่านั้น ไม่ถูกส่งกลับหน้าเว็บและไม่เขียนลง log
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from landsmaps import config, keystore
from landsmaps import login as lg
from landsmaps.api import token_expiry

logger = logging.getLogger("dashboard.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])

TOKEN_FILE = config.TOKEN_FILE
ENV_FILE = config.ENV_FILE
PROVIDER = "LandsMaps กรมที่ดิน · เข้าสู่ระบบด้วย DGA (บัญชีทางรัฐ)"


class LoginIn(BaseModel):
    user: str = ""
    password: str = ""
    remember: bool = True


class LogoutIn(BaseModel):
    forget: bool = False


def mask_user(user: str) -> str:
    """เลขประจำตัวประชาชน/อีเมลไม่ควรโชว์เต็มบนจอ (เผื่อแชร์หน้าจอ)"""
    if len(user) <= 6:
        return user[:1] + "*" * (len(user) - 1)
    return f"{user[:3]}{'*' * (len(user) - 5)}{user[-2:]}"


def _token() -> tuple[str, str | None]:
    """(token, ที่มา) — env LANDSMAPS_TOKEN มาก่อนไฟล์ เหมือน landsmaps.api.read_token"""
    env_tok = os.environ.get(config.TOKEN_ENV, "").strip()
    if env_tok:
        return env_tok.removeprefix("Bearer ").strip(), "env"
    tok = keystore.load(TOKEN_FILE).get("key", "").strip().removeprefix("Bearer ").strip()
    return tok, ("file" if tok else None)


def _remembered() -> tuple[str, str] | None:
    """บัญชีที่จำไว้ ลำดับเดียวกับ login.credentials(): env var -> .env -> Access_Key.txt"""
    env = {**lg.read_env(ENV_FILE), **os.environ}
    if not (env.get(lg.ID_KEY) or "").strip():
        saved = keystore.load(TOKEN_FILE)
        if saved.get("user") and saved.get("pass"):
            env = {lg.ID_KEY: saved["user"], lg.PASSWORD_KEY: saved["pass"], **env}
    try:
        return lg.credentials(env)
    except lg.LoginError:
        return None


def _status() -> dict[str, Any]:
    tok, source = _token()
    exp = token_expiry(tok) if tok else None
    now = datetime.now()
    expired = bool(exp and exp <= now)
    creds = _remembered()
    user = keystore.load(TOKEN_FILE).get("user") or (creds[0] if creds else "")
    logged_in = bool(tok) and not expired
    return {
        "provider": PROVIDER,
        "logged_in": logged_in,
        "source": source,
        "user": mask_user(user) if user else None,
        "expires_at": exp.isoformat(timespec="minutes") if exp else None,
        "remaining_sec": max(0, int((exp - now).total_seconds())) if exp else None,
        "expired": expired,
        "remembered": creds is not None,
        "quota": config.LOGIN_QUOTA if logged_in else config.FREE_QUOTA,
    }


@router.get("/status")
def status() -> dict[str, Any]:
    try:
        return _status()
    except keystore.KeyFileError as e:
        return {"provider": PROVIDER, "logged_in": False, "error": str(e),
                "remembered": False, "quota": config.FREE_QUOTA}


@router.post("/login")
def do_login(body: LoginIn) -> dict[str, Any]:
    """กรอกบัญชี -> ล็อกอินด้วยบัญชีนั้น · เว้นว่างทั้งคู่ -> ต่ออายุด้วยบัญชีที่จำไว้"""
    user, password = body.user.strip(), body.password.strip()
    if bool(user) != bool(password):
        raise HTTPException(400, "กรอกทั้งบัญชีผู้ใช้และรหัสผ่าน (หรือเว้นว่างทั้งคู่เพื่อใช้บัญชีที่จำไว้)")
    remember = body.remember
    try:
        if not user:
            creds = _remembered()
            if creds is None:
                raise HTTPException(400, "ยังไม่มีบัญชีที่จำไว้ -> กรอกบัญชี DGA และรหัสผ่าน")
            (user, password), remember = creds, True
        token = lg.login(user, password)
    except lg.LoginError as e:
        logger.info("LandsMaps login failed for %s", mask_user(user))
        raise HTTPException(401, f"ล็อกอินไม่สำเร็จ: {e}") from None
    except keystore.KeyFileError as e:
        raise HTTPException(500, str(e)) from None

    if remember:
        keystore.save(TOKEN_FILE, kind=lg.KIND, user=user, key=token, password=password)
        lg.write_env({lg.ID_KEY: user, lg.PASSWORD_KEY: password}, ENV_FILE)
    else:
        keystore.save(TOKEN_FILE, kind=lg.KIND, user=user, key=token)
        lg.forget_credentials(TOKEN_FILE, ENV_FILE)
    logger.info("LandsMaps login ok for %s (remember=%s)", mask_user(user), remember)
    return status()


@router.post("/logout")
def do_logout(body: LogoutIn) -> dict[str, Any]:
    """ลบ token ออกจาก Access_Key.txt · forget=True -> ลืมบัญชีที่จำไว้ด้วย"""
    try:
        keystore.remove("key", path=TOKEN_FILE)
        if body.forget:
            lg.forget_credentials(TOKEN_FILE, ENV_FILE)
            keystore.remove("user", path=TOKEN_FILE)
    except keystore.KeyFileError as e:
        raise HTTPException(500, str(e)) from None
    return status()
