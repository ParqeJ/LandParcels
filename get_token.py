#!/usr/bin/env python3
"""ล็อกอิน LandsMaps แล้วเขียน access token ลง Access_Key.txt (แทนการคัดลอกจาก browser)

    python get_token.py                 # ล็อกอินใหม่ด้วยบัญชีที่บันทึกไว้
    python get_token.py --where         # ดูว่าเก็บบัญชี/token ไว้ที่ไหน มีอะไรบ้าง
    python get_token.py --kind openid   # บังคับชนิดบัญชี (openid = เข้าสู่ระบบด้วย DGA)

บัญชีอ่านได้ 3 ที่ เรียงตามลำดับ: environment variable -> .env -> Access_Key.txt
"""

import argparse
import sys

import requests

from landsmaps import keystore
from landsmaps.config import ENV_FILE, TOKEN_FILE
from landsmaps.login import (ID_KEYS, KINDS, LoginError, credentials, describe,
                             login_any, save_credentials)


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ขอ access token ของบัญชี LandsMaps")
    p.add_argument("--where", action="store_true",
                   help=f"แสดงว่าเก็บบัญชีและ token ไว้ที่ไหน มีอะไรบ้าง (ไม่โชว์รหัสผ่าน)")
    p.add_argument("--kind", choices=KINDS,
                   help="ชนิดบัญชีที่ใช้ล็อกอิน ไม่ใส่ = ตามที่บันทึกไว้")
    return p.parse_args(argv)


def show_where() -> int:
    print(keystore.describe())
    print(f"\n.env:     {ENV_FILE}" + ("" if ENV_FILE.exists() else "  (ยังไม่มีไฟล์นี้)"))
    print(f"          ตัวแปรที่อ่าน: {', '.join(ID_KEYS.values())}, LANDSMAPS_PASSWORD")
    return 0


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    if args.where:
        return show_where()

    try:
        kind, user, password = credentials()
        kind = args.kind or kind
        token = login_any(kind, user, password)
    except LoginError as e:
        print(f"ล็อกอินไม่สำเร็จ: {e}")
        return 1
    except requests.RequestException as e:
        print(f"ติดต่อ LandsMaps ไม่ได้: {e}")
        return 1

    save_credentials(kind, user, password, token)
    print(f"ล็อกอินสำเร็จ ({ID_KEYS[kind]}={user}) -> เขียน {TOKEN_FILE.name} แล้ว ({describe(token)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
