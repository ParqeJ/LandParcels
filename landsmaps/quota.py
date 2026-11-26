"""โควตาค้นรายละเอียดต่อวัน -> ต้องรันอีกกี่วัน

ตัวคุมว่างานจะเสร็จเมื่อไหร่คือ **โควตาต่อวัน** ไม่ใช่เวลารันในเครื่อง (1 วันรันจริงไม่กี่นาที
แล้วก็ติดโควตา) จึงประมาณเป็นจำนวนวัน ใช้ร่วมกันทั้ง pipeline (log) และ dashboard (หน้าเว็บ)
"""
from __future__ import annotations

import math

from .config import FREE_QUOTA_RANGE, LOGIN_QUOTA_RANGE

Quota = tuple[int, int]         # (ต่ำสุด, สูงสุด) แปลงต่อวัน


def quota_for(token: str) -> Quota:
    """โควตาค้นรายละเอียดต่อวัน ตามว่ามี access token ของบัญชีหรือไม่"""
    return LOGIN_QUOTA_RANGE if token else FREE_QUOTA_RANGE


def days_left(remaining: int, quota: Quota) -> str:
    """ต้องรันอีกกี่วันจึงจะครบ — เร็วสุด = หารด้วยโควตาสูงสุด, ช้าสุด = หารด้วยโควตาต่ำสุด"""
    if remaining <= 0:
        return "ครบแล้ว"
    lo, hi = quota
    fast, slow = math.ceil(remaining / hi), math.ceil(remaining / lo)
    return f"~{fast:,} วัน" if fast == slow else f"~{fast:,}-{slow:,} วัน"
