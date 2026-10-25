#!/usr/bin/env python3
"""ล็อกอิน LandsMaps ผ่าน DGA (บัญชีทางรัฐ) แล้วเขียน access token ลง Access_Key.txt (แทนการคัดลอกจาก browser)

    python get_token.py                 # ล็อกอินใหม่ด้วยบัญชีที่บันทึกไว้
    python get_token.py --where         # ดูว่าเก็บบัญชี/token ไว้ที่ไหน มีอะไรบ้าง

บัญชีอ่านได้ 3 ที่ เรียงตามลำดับ: environment variable -> .env -> Access_Key.txt
"""

import argparse
import sys

from landsmaps import keystore
from landsmaps.config import ENV_FILE, TOKEN_FILE
from landsmaps.login import (ID_KEY, PASSWORD_KEY, LoginError, credentials, describe, login,
                             save_credentials)


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ขอ access token ของบัญชี LandsMaps (ล็อกอินผ่าน DGA)")
    p.add_argument("--where", action="store_true",
                   help="แสดงว่าเก็บบัญชีและ token ไว้ที่ไหน มีอะไรบ้าง (ไม่โชว์รหัสผ่าน)")
    return p.parse_args(argv)


def show_where() -> int:
    print(keystore.describe())
    print(f"\n.env:     {ENV_FILE}" + ("" if ENV_FILE.exists() else "  (ยังไม่มีไฟล์นี้)"))
    print(f"          ตัวแปรที่อ่าน: {ID_KEY}, {PASSWORD_KEY}")
    return 0


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    try:
        if args.where:
            return show_where()
        user, password = credentials()
        token = login(user, password)
        save_credentials(user, password, token)
    except keystore.KeyFileError as e:          # Access_Key.txt เสีย -> บอกวิธีแก้ ไม่โชว์ traceback
        print(e)
        return 1
    except LoginError as e:
        print(f"ล็อกอินไม่สำเร็จ: {e}")
        return 1

    print(f"ล็อกอินสำเร็จ ({ID_KEY}={user}) -> เขียน {TOKEN_FILE.name} แล้ว ({describe(token)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
