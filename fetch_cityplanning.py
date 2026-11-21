#!/usr/bin/env python3
"""
ดึงผังเมืองรวม (การใช้ประโยชน์ที่ดิน) รายจังหวัดจาก LandsMaps กรมที่ดิน -> Shapefile/GPKG

    python fetch_cityplanning.py 60                 # ทั้งจังหวัด (รหัส 60 = นครสวรรค์ เปิดสาธารณะ)
    python fetch_cityplanning.py อำนาจเจริญ          # ระบุด้วยชื่อไทยก็ได้
    python fetch_cityplanning.py 37 50 60           # หลายจังหวัดในครั้งเดียว
    python fetch_cityplanning.py 37 --area areas/my_site.kmz   # เฉพาะกรอบพื้นที่โครงการ
    python fetch_cityplanning.py 60 --list-layers   # ดูชั้นข้อมูลในจังหวัดนั้น
    python fetch_cityplanning.py --list-provinces   # ดูรหัส/ชื่อจังหวัดทั้งหมด

ผลลัพธ์: output/cityplanning/<รหัส_จังหวัด>/<รหัส_จังหวัด>_cityplanning_epsg240xx.shp (+ .gpkg)
         CRS = Indian 1975 UTM 47N/48N (เมตร) overlay กับแปลง/buffer ของโปรเจกต์ได้ตรง

Token: จังหวัดส่วนใหญ่ service ต้องใช้ ArcGIS token ของกรมที่ดิน
       ใส่ของตัวเองผ่าน  --token <ค่า>  หรือ env  LANDSMAPS_ARCGIS_TOKEN
       (นครสวรรค์/60 ทดสอบได้โดยไม่ต้อง token)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from landsmaps.cityplanning import (ServiceError, TokenRequired, all_provinces,
                                    describe_service, resolve_token, run_province)
from landsmaps.cityplanning.service import TOKEN_ENV
from landsmaps.login import read_env

FORMATS = {"shp": ("shp",), "gpkg": ("gpkg",), "both": ("shp", "gpkg")}


def pick_token(cli_token: str | None) -> str | None:
    """ลำดับ: env ของระบบ > --token > ค่าในไฟล์ .env (คีย์ LANDSMAPS_ARCGIS_TOKEN)"""
    return resolve_token(cli_token) or (read_env().get(TOKEN_ENV) or None)


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="ดึงผังเมืองรายจังหวัดจาก LandsMaps -> Shapefile/GPKG",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("provinces", nargs="*", help="รหัสจังหวัด (เช่น 37) หรือชื่อไทย (เช่น อำนาจเจริญ)")
    p.add_argument("--area", type=Path, help="ไฟล์ขอบเขต (KMZ/SHP/…) สำหรับตัดเฉพาะกรอบพื้นที่โครงการ")
    p.add_argument("--layer", help="เลือกชั้นข้อมูลเอง (id หรือชื่อ) ไม่ใส่ = ชั้นผังรวมทั้งจังหวัด")
    p.add_argument("--token", help="ArcGIS token ของคุณ (หรือใช้ env LANDSMAPS_ARCGIS_TOKEN)")
    p.add_argument("--format", choices=FORMATS, default="both", help="ชนิดไฟล์ผลลัพธ์ (ค่าเริ่มต้น both)")
    p.add_argument("--out", type=Path, help="โฟลเดอร์ผลลัพธ์ (ค่าเริ่มต้น output/cityplanning)")
    p.add_argument("--method", choices=("auto", "query", "identify"), default="auto",
                   help="วิธีดึง: auto (ค่าเริ่มต้น) เลือกเอง | query เร็ว | identify ซอยกรอบ "
                        "ใช้กับจังหวัดที่ service ไม่เปิด /query (เช่น 36)")
    p.add_argument("--list-provinces", action="store_true", help="แสดงรหัส/ชื่อจังหวัดทั้งหมดแล้วออก")
    p.add_argument("--hints", action="store_true",
                   help="แสดงคำแนะนำการใส่ค่าท้ายรายชื่อจังหวัด (ใช้กับ --list-provinces)")
    p.add_argument("--list-layers", action="store_true", help="แสดงชั้นข้อมูลของจังหวัดที่ระบุแล้วออก")
    return p.parse_args(argv)


def print_provinces(hints: bool = False) -> None:
    items = all_provinces()
    print(f"จังหวัดทั้งหมด {len(items)} (รหัส = pvcode ของ service PLLU):")
    for i, prov in enumerate(items, 1):
        end = "\n" if i % 3 == 0 else "   "
        print(f"  {prov.code} {prov.name:<16}", end=end)
    if len(items) % 3:
        print()
    if hints:
        print()
        print("-" * 58)
        print("  ใส่หลายจังหวัดได้ เว้นวรรค เช่น:  37 50 60")
        print("  ใส่ชื่อไทยก็ได้ เช่น:  อำนาจเจริญ")
        print("  60 = นครสวรรค์ (เปิดสาธารณะ ไม่ต้องใช้ token)")
        print("-" * 58)


def print_layers(value: str, token: str | None) -> int:
    try:
        info = describe_service(value, token)
    except TokenRequired:
        print(f"จังหวัด {value}: service ต้องใช้ token -> ใส่ --token หรือ env LANDSMAPS_ARCGIS_TOKEN")
        return 1
    except (ServiceError, ValueError) as e:
        print(f"จังหวัด {value}: {e}")
        return 1
    print(f"ชั้นข้อมูลของ PLLU{info.province_code} (zone {info.zone}, wkid {info.wkid}):")
    master = info.master_layer()
    for lyr in info.layers:
        tag = "  <- ชั้นผังรวมทั้งจังหวัด (ค่าเริ่มต้น)" if lyr.id == master.id else ""
        print(f"  [{lyr.id:>2}] {lyr.name}{tag}")
    return 0


def token_help() -> None:
    print("  วิธีได้ token: ล็อกอินเว็บ landsmaps.dol.go.th แล้วคัดลอก ArcGIS token ของคุณ "
          "มาใส่ --token หรือตั้ง env LANDSMAPS_ARCGIS_TOKEN")
    print("  หรือทดสอบระบบก่อนด้วยจังหวัดที่เปิดสาธารณะ: python fetch_cityplanning.py 60")


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")        # แสดงภาษาไทยใน console ของ Windows
    args = parse_args(argv)
    token = pick_token(args.token)

    if args.list_provinces:
        print_provinces(hints=args.hints)
        return 0
    if not args.provinces:
        print("ระบุจังหวัดอย่างน้อย 1 จังหวัด (รหัสหรือชื่อ) หรือ --list-provinces")
        return 1
    if args.list_layers:
        return print_layers(args.provinces[0], token)

    formats = FORMATS[args.format]
    kwargs = {"layer": args.layer, "area_path": args.area, "formats": formats,
              "method": args.method}
    if args.out is not None:
        kwargs["out_dir"] = args.out

    failed: list[str] = []
    for value in args.provinces:
        try:
            run_province(value, token, **kwargs)
        except TokenRequired:
            print(f"[{value}] service ต้องใช้ ArcGIS token")
            token_help()
            failed.append(str(value))
        except (ServiceError, ValueError) as e:
            print(f"[{value}] {e}")
            failed.append(str(value))
        print()

    if failed:
        print(f"ไม่สำเร็จ {len(failed)} จังหวัด: {', '.join(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
