#!/usr/bin/env python3
"""
ดึงแปลงที่ดิน (โฉนด + น.ส.3ก) จาก LandsMaps ตามไฟล์ขอบเขตพื้นที่ -> Shapefile

    python fetch_parcels.py                    # ทุกไฟล์ในโฟลเดอร์ areas/
    python fetch_parcels.py areas/my_site.kmz  # เฉพาะไฟล์ที่ระบุ
    python fetch_parcels.py --no-detail        # เอาแค่รูปแปลง ไม่ใช้โควตา API

ผลลัพธ์: output/<ชื่อไฟล์>/<ชื่อไฟล์>_parcel_epsg240xx.shp และ _ns3k_epsg240xx.shp
"""

import argparse
import sys
from pathlib import Path

from landsmaps import run_area
from landsmaps.api import QuotaExceeded, check_token, read_token
from landsmaps.area import find_area_files
from landsmaps.config import AREA_SUFFIXES, AREAS_DIR, TOKEN_FILE
from landsmaps.login import LoginError, ensure_token


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ดึงแปลงที่ดินจาก LandsMaps ตามไฟล์ขอบเขตพื้นที่")
    p.add_argument("areas", nargs="*", type=Path,
                   help=f"ไฟล์ขอบเขต ({', '.join(AREA_SUFFIXES)}, .gdb) ไม่ใส่ = ทุกไฟล์ใน {AREAS_DIR.name}/")
    p.add_argument("--no-detail", action="store_true",
                   help="ข้ามการดึงรายละเอียดรายแปลง (ไร่-งาน-วา ฯลฯ) เอาแค่รูปแปลง + เลขที่ดิน")
    p.add_argument("--layer", help="ชื่อ layer ที่ใช้ (ถ้าไฟล์มีหลาย layer ไม่ใส่ = รวม polygon ทุก layer)")
    p.add_argument("--name", help="ชื่อพื้นที่สำหรับตั้งชื่อไฟล์ผลลัพธ์ (ใช้ได้เมื่อระบุไฟล์เดียว)")
    args = p.parse_args(argv)
    if args.name and len(args.areas) != 1:
        p.error("--name ใช้ได้เมื่อระบุไฟล์ขอบเขตไฟล์เดียว")
    return args


def login_or_saved_token() -> str:
    """ล็อกอินใหม่ ถ้าล็อกอินไม่ผ่านแต่ยังมี token เดิมอยู่ ให้เตือนแล้วใช้ของเดิมต่อ"""
    try:
        return ensure_token()
    except LoginError as e:
        saved = read_token()
        if not saved:
            raise
        print(f"ล็อกอินอัตโนมัติไม่สำเร็จ: {e}")
        print(f"  -> ใช้ token เดิมใน {TOKEN_FILE.name} ต่อ")
        return saved


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")        # แสดงภาษาไทยใน console ของ Windows
    args = parse_args(argv)
    files = args.areas or find_area_files(AREAS_DIR)
    if not files:
        print(f"ไม่พบไฟล์ขอบเขต -> วางไฟล์ {', '.join(AREA_SUFFIXES)} หรือโฟลเดอร์ .gdb ไว้ใน {AREAS_DIR}")
        return 1

    fetch_detail = not args.no_detail
    if fetch_detail:
        try:
            print(check_token(login_or_saved_token()))
        except (LoginError, QuotaExceeded) as e:    # แจ้งก่อนเริ่ม ไม่ต้องรอให้พังทุกพื้นที่
            print(f"{e}\nหรือใช้ --no-detail เพื่อดึงแค่รูปแปลง")
            return 1

    failed = []
    for path in files:
        try:
            result = run_area(path, layer=args.layer, name=args.name, fetch_detail=fetch_detail)
        except Exception as e:                      # พื้นที่หนึ่งพัง ไม่ให้พื้นที่อื่นหยุดตาม
            print(f"[{path.name}] ผิดพลาด: {e}")
            failed.append(path.name)
            continue
        if result.quota_hit:                        # โควตานับรวมทุกพื้นที่ -> ไม่ต้องลองต่อ
            fetch_detail = False
        print()

    if failed:
        print(f"ไม่สำเร็จ {len(failed)} พื้นที่: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
