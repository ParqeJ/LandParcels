# CityPlanning — ดึงผังเมืองรวมรายจังหวัด

> Feature คู่กับ parcel: `fetch_cityplanning.py` → Shapefile/GPKG ผังเมือง
> กลับไปที่สารบัญ: [CLAUDE.md](../CLAUDE.md) · โฟลเดอร์คู่: [setup.md](setup.md) · [parcel.md](parcel.md)
> README ผู้ใช้: [CITYPLANNING_README.md](../../CITYPLANNING_README.md)

เดิมชื่อ feature "landuse" — rename เป็น "cityplanning" ทั้งโมดูล/ไฟล์/path แล้ว (`landsmaps/cityplanning/`, `output/cityplanning/`)

---

## Entry points

| คำสั่ง | ใช้ทำอะไร |
|---|---|
| `python fetch_cityplanning.py 60` | ดึงทั้งจังหวัด (60=นครสวรรค์ เปิดสาธารณะ ทดสอบได้) → `output/cityplanning/60_นครสวรรค์/...shp` |
| `python fetch_cityplanning.py อำนาจเจริญ` | ระบุด้วยชื่อไทย |
| `python fetch_cityplanning.py 37 50 60` | หลายจังหวัดในครั้งเดียว |
| `python fetch_cityplanning.py 37 --area areas/my_site.kmz` | ตัดเฉพาะกรอบพื้นที่โครงการ |
| `python fetch_cityplanning.py 60 --list-layers` | ดูชั้นข้อมูลของจังหวัดนั้น |
| `python fetch_cityplanning.py --list-provinces` | ดูรหัส/ชื่อจังหวัดทั้ง 77 |
| `python fetch_cityplanning.py 36 --method identify` | บังคับ identify ซอยกรอบ (ปกติ auto) |
| `python -m pytest tests/test_cityplanning.py tests/test_cityplanning_identify.py -v` | รัน test (offline) |

---

## Token (สำคัญ)

service ผังเมืองรายจังหวัดของกรมที่ดิน **ส่วนใหญ่ต้องใช้ ArcGIS token ของผู้ใช้** (ยกเว้นบางจังหวัดที่เปิดสาธารณะ เช่น **นครสวรรค์/60** ใช้ได้โดยไม่ต้อง token)

- env `LANDSMAPS_ARCGIS_TOKEN` (ถาวรกว่า) หรือ `--token <value>`
- โปรแกรม **ไม่ไปหยิบ token ของ DGA/กรมที่ดินมาใช้แทน** — ผู้ใช้ต้องจัดหา token เอง (ล็อกอินเว็บ LandsMaps แล้วคัดลอก ArcGIS token)
- ถ้าจังหวัดต้อง token แต่ไม่ได้ใส่ โปรแกรมจะแจ้ง `service ต้องใช้ ArcGIS token` และข้ามจังหวัดนั้น

---

## วิธีดึง: `/query` vs `/identify` (`--method`)

| capability ของ service | ตัวอย่าง | วิธีที่ใช้ |
|---|---|---|
| `Map,Query,Data` | 60 นครสวรรค์ | **query**: ขอ objectId ทั้งหมดแล้วดึงเป็นชุด (เร็ว) |
| `Map,Query` (ไม่มี `Data`) | 36 ชัยภูมิ | **identify** ซอยกรอบ quadtree (ช้ากว่า แต่ครบ) |

`--method auto` (ค่าเริ่มต้น) เลือกให้เองจาก capability และสลับไป identify ถ้า `/query` ถูกปฏิเสธ

**identify ซอยกรอบ** (`landsmaps/cityplanning/identify.py`):

1. เรียก `/identify` ด้วยกรอบทั้งจังหวัด (หรือกรอบ `--area`)
2. ถ้าคืนมาเต็ม `maxRecordCount` (เช่น 500) → ผ่ากรอบเป็น 4 แล้วถามใหม่ ไล่ลงไปเรื่อย ๆ
3. กรอบที่คืนน้อยกว่าเพดาน = ได้ครบแล้ว
4. รวมทุกกรอบ ตัดตัวซ้ำด้วย `FID` → polygon เต็มรูป + attribute ครบ
5. ถ้ามีกรอบที่ผ่าจนสุด (`MAX_DEPTH`) แล้วยังเต็มเพดาน จะขึ้น `[เตือน] … อาจตกหล่น`

ตรวจความถูกต้องกับ PLLU60: identify ได้ **399/399 รูป FID ตรงกันทุกตัว** attribute หลัง export ตรงกัน 100% และ geometry ต่างกัน 0 ตร.ม.

---

## Schema: 12 ฟิลด์ของ `output/cityplanning/<prov>/<prov>_cityplanning_epsg240xx.shp`

**แยกจาก schema 14 ฟิลด์ของแปลงที่ดิน — ห้ามปน** (field ≤ 10 ตัวอักษร)

| Field | ความหมาย | ที่มา |
|---|---|---|
| `PL_USE` | รหัสประเภทการใช้ที่ดิน (เช่น 1110, 3100, 8600) | field `PL_USE` |
| `PL_USE_TH` | ชื่อประเภทภาษาไทย (เช่น "ชนบทและเกษตรกรรม") | ตาราง legend |
| `ZONE_HEX` | สีผังทางการ (#rrggbb) ตาม renderer ของกรมที่ดิน | ตาราง legend |
| `FAR_MAX` | อัตราส่วนพื้นที่อาคารต่อที่ดินสูงสุด | `PL_FAR_MAX` |
| `BCR_MAX` | อัตราส่วนพื้นที่อาคารคลุมดินสูงสุด | `PL_BCR_MAX` |
| `DENS_H` / `DENS_L` | ความหนาแน่น สูง/ต่ำ | `PL_DENS_H/L` |
| `PLAN_NAME` | ชื่อผัง | `NAME` |
| `YEAR` | ปีผัง (พ.ศ.) | `YEAR` |
| `PROVINCE` | ชื่อจังหวัด | ตารางจังหวัด |
| `AREA_RAI` | พื้นที่ (ไร่) คำนวณจาก geometry เมตร | 1 ไร่ = 1600 ตร.ม. |
| `SRC_LAYER` | ชื่อชั้นต้นทางใน service | metadata |

**CRS:** EPSG 24047/24048 เลือกอัตโนมัติจาก CRS ที่ service ประกาศ (32647/32648)

---

## สถาปัตยกรรม (`landsmaps/cityplanning/`)

| ไฟล์ | หน้าที่ |
|---|---|
| `provinces.py` | รหัสจังหวัด ↔ ชื่อ (77 จังหวัด) = pvcode ของ service PLLU |
| `service.py` | ArcGIS REST client (metadata/objectId/feature), token, retry, เลี่ยง WAF |
| `identify.py` | สำรองเมื่อ `/query` ใช้ไม่ได้: `/identify` ซอยกรอบ quadtree + ตัดซ้ำ + Esri→GeoJSON |
| `legend.py` | `PL_USE` → ชื่อไทย + สี (จาก `data/pl_use_legend.json` merge กับ renderer ตอนรัน) |
| `export.py` | GeoJSON (4326) → reproject เป็นเมตร → SHP/GPKG |
| `pipeline.py` | รวมทุกขั้นของ 1 จังหวัด |

> **หมายเหตุ:** ชื่อ URL `LandusePlan` และ service code `PLLU` เป็นชื่อจริงของเซิร์ฟเวอร์กรมที่ดิน — **ห้ามเปลี่ยน** (external dependency)

---

## หมายเหตุทางเทคนิค

- **WAF** บล็อก query ที่หน้าตาเหมือน SQL injection → ใช้ `where=PL_USE>=0` แทน `1=1`
- service **ไม่รองรับ pagination** → ขอ `objectId` ทั้งหมดก่อน (`returnIdsOnly`) แล้วดึงเป็นชุดละ `OID_CHUNK` รูป
- เซิร์ฟเวอร์ **บล็อก POST** ไปที่ `/query` (รหัส 555) → ใช้ GET เท่านั้น
- **retry** อัตโนมัติเมื่อเจอ 5xx/429 ชั่วคราว
- `f=geojson` ตอบ `content-type: text/plain` ไม่บอก charset → บังคับถอดรหัส UTF-8 (ไม่งั้นชื่อผังภาษาไทยเพี้ยน)

---

## Template สำหรับ ArcGIS Pro

`templates/cityplanning_PL_USE.lyrx` — Layer file ตั้ง symbology ตาม `PL_USE` + `ZONE_HEX` ใช้ drag เข้า ArcGIS Pro แล้ว Set Data Source ไปยัง shapefile ที่ดึงออกมา
