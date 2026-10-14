#!/usr/bin/env python3
"""
ค้นโฉนดตามเลขโฉนดจาก LandsMaps แล้วบันทึกเป็น Shapefile

    python search_parcel.py --prov 36 --amphur 07 30219 30220

รหัสจังหวัด/อำเภอ: ดูได้จากเว็บ landsmaps.dol.go.th (ค้นหาแปลง > เลือกจังหวัด/อำเภอ)
ผลลัพธ์: output/search/parcel_search_epsg240xx.shp (แยกไฟล์ตาม zone ถ้าปนกัน)
"""

import argparse
import sys
import time

import requests
from pyproj import CRS
from shapely.geometry import shape

from landsmaps.api import LandsMapsAPI, QuotaExceeded, check_token, read_token
from landsmaps.config import OUTPUT_DIR, SLEEP_SEC, TIMEOUT, WFS
from landsmaps.export import detail_row, to_shp
from landsmaps.zones import Zone

SEARCH_RADII_M = (50, 500)      # bbox รอบจุด e/n ที่ใช้หารูปแปลง


def get_geometry(info: dict, zone: Zone):
    """หา polygon จาก WFS ด้วย bbox รอบจุด e/n แล้วจับคู่ parcel_seq"""
    e, n = float(info["e"]), float(info["n"])
    seq = int(info["parcel_seq"])
    for radius in SEARCH_RADII_M:
        params = {
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": f"LANDSMAPS:{zone.parcel_layer}",
            "viewparams": f"utmmap:{info['utm1']}{info['utm2']}",
            "bbox": f"{e - radius},{n - radius},{e + radius},{n + radius},EPSG:{zone.epsg}",
            "outputFormat": "application/json",
        }
        r = requests.get(WFS, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        for f in r.json()["features"]:
            if int(f["properties"]["parcel_seq"]) == seq:
                g = shape(f["geometry"])
                return (g if g.is_valid else g.buffer(0)), f["properties"].get("land_no")
        time.sleep(SLEEP_SEC)
    return None, None


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ค้นโฉนดตามเลขโฉนดจาก LandsMaps -> Shapefile")
    p.add_argument("--prov", required=True, help="รหัสจังหวัด 2 หลัก เช่น 36 = ชัยภูมิ")
    p.add_argument("--amphur", required=True, help="รหัสอำเภอ 2 หลัก เช่น 07")
    p.add_argument("parcel_nos", nargs="+", help="เลขโฉนด (ใส่ได้หลายเลข)")
    args = p.parse_args(argv)
    for code, label in ((args.prov, "--prov"), (args.amphur, "--amphur")):
        if not (is_ascii_number(code) and len(code) == 2):
            p.error(f"{label} ต้องเป็นตัวเลข 2 หลัก (ได้ '{code}')")
    if not all(is_ascii_number(no) for no in args.parcel_nos):
        p.error("เลขโฉนดต้องเป็นตัวเลขอารบิก 0-9 เท่านั้น")
    return args


def is_ascii_number(text: str) -> bool:
    return text.isascii() and text.isdecimal()      # isdigit() ยอมรับเลขไทย ๑๒๓ ซึ่ง API ไม่รู้จัก


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    token = read_token()
    print(check_token(token))
    api = LandsMapsAPI(token)

    by_zone: dict[int, list] = {}
    for i, no in enumerate(args.parcel_nos, 1):
        print(f"[{i}/{len(args.parcel_nos)}] โฉนด {no} ... ", end="", flush=True)
        try:
            info = api.parcel_by_no(args.prov, args.amphur, no)
            if info is None:
                print("ไม่พบ")
                continue
            zone = Zone(int(info.get("zone") or 47))
            geom, land_no = get_geometry(info, zone)
        except QuotaExceeded as e:
            print(f"หยุด: LandsMaps แจ้ง [{e}]")
            break
        except requests.RequestException as e:      # แปลงนี้พลาด ไม่ทิ้งแปลงที่ได้มาแล้ว
            print(f"ติดต่อ LandsMaps ไม่ได้ ({e}) -> ข้าม")
            continue
        if geom is None:
            print("พบข้อมูลแต่ไม่พบรูปแปลงใน WFS -> ข้าม")
            continue
        by_zone.setdefault(zone.number, []).append((detail_row(land_no, info, no), geom))
        print(f"ระวาง {info['utm']}  เลขที่ดิน {land_no}  "
              f"{info['rai']}-{info['ngan']}-{info['wa']} ไร่  ต.{info['tumbolname']}")
        time.sleep(SLEEP_SEC)

    if not by_zone:
        print("ไม่มีข้อมูลให้บันทึก")
        return 1
    for number, items in by_zone.items():
        zone = Zone(number)
        path = OUTPUT_DIR / "search" / f"parcel_search_epsg{zone.epsg}.shp"
        rows, geoms = zip(*items)
        to_shp(list(rows), geoms, CRS.from_epsg(zone.epsg), path)
        print(f"\nบันทึก {len(rows)} แปลง -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
