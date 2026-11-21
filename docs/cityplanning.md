# ผังเมือง — `fetch_cityplanning.py` คู่มือเต็ม

> 📑 สารบัญ: [← README](../README.md) · [setup](setup.md) · [parcel](parcel.md)

ดึง **ผังเมืองรวม / การใช้ประโยชน์ที่ดิน** รายจังหวัดจาก service `LandusePlan` ของ
[LandsMaps กรมที่ดิน](https://landsmaps.dol.go.th/) ออกมาเป็น **Shapefile + GeoPackage**
พิกัด **EPSG:24047/24048 (เมตร)** พร้อม overlay กับแปลงที่ดิน/buffer ของโปรเจกต์ได้ทันที

เป็น Feature คู่กับ `fetch_parcels.py` (ดึงแปลงที่ดิน) — ใช้ module ร่วมกันใน `landsmaps/`
แต่โค้ดผังเมืองอยู่แยกใน `landsmaps/cityplanning/`

---

## เริ่มใช้งาน

```powershell
python fetch_cityplanning.py 60                 # ทั้งจังหวัด (60 = นครสวรรค์ เปิดสาธารณะ ทดสอบได้เลย)
python fetch_cityplanning.py อำนาจเจริญ          # ระบุด้วยชื่อไทยก็ได้
python fetch_cityplanning.py 37 50 60           # หลายจังหวัดในครั้งเดียว
python fetch_cityplanning.py 37 --area areas/my_site.kmz   # เฉพาะกรอบพื้นที่โครงการ
python fetch_cityplanning.py 60 --list-layers   # ดูชั้นข้อมูลของจังหวัดนั้น
python fetch_cityplanning.py --list-provinces   # ดูรหัส/ชื่อจังหวัดทั้ง 77
python fetch_cityplanning.py 36 --method identify   # บังคับวิธี identify ซอยกรอบ (ปกติไม่ต้องใส่ auto เลือกให้)
```

**ผลลัพธ์:** `output/cityplanning/<รหัส_จังหวัด>/<รหัส_จังหวัด>_cityplanning_epsg240xx.shp` (+ `.gpkg`)

---

## Token (สำคัญ)

service ผังเมืองรายจังหวัดของกรมที่ดิน **ส่วนใหญ่ต้องใช้ ArcGIS token** (ยกเว้นบางจังหวัดที่เปิดสาธารณะ เช่น **นครสวรรค์/60** ใช้ได้โดยไม่ต้อง token)

ใส่ token ของคุณเองได้ 2 ทาง:

```powershell
# 1) ผ่าน env (ถาวรกว่า)
$env:LANDSMAPS_ARCGIS_TOKEN = "<token ของคุณ>"
python fetch_cityplanning.py 37

# 2) ผ่าน argument
python fetch_cityplanning.py 37 --token "<token ของคุณ>"
```

> โปรแกรม **ไม่ไปหยิบ token ของระบบกรมที่ดินมาใช้แทนคุณ** — คุณต้องเป็นผู้จัดหา token เอง
> (ล็อกอินเว็บ LandsMaps ด้วยบัญชีของคุณ แล้วนำ ArcGIS token มาใส่) ลำดับความสำคัญ: env → `--token`

ถ้าจังหวัดต้อง token แต่ไม่ได้ใส่ โปรแกรมจะแจ้ง `service ต้องใช้ ArcGIS token` และข้ามจังหวัดนั้น

---

## วิธีดึง: `/query` กับ `/identify` (`--method`)

แต่ละจังหวัดเปิด capability ของ service ไม่เท่ากัน (ดูได้จาก `capabilities` ใน metadata):

| capability ของ service | ตัวอย่าง | `/query` | วิธีที่ใช้ |
|---|---|---|---|
| `Map,Query,Data` | 60 นครสวรรค์ | ✅ | **query**: ขอ objectId ทั้งหมดแล้วดึงเป็นชุด (เร็ว) |
| `Map,Query` (ไม่มี `Data`) | 36 ชัยภูมิ | ❌ 400 *The requested capability is not supported.* | **identify** ซอยกรอบ (ช้ากว่ามาก แต่ครบ) |

`--method auto` (ค่าเริ่มต้น) เลือกให้เองจาก capability และสลับไป identify ถ้า `/query` ถูกปฏิเสธ

**identify ซอยกรอบทำงานอย่างไร** (`landsmaps/cityplanning/identify.py`)

1. เรียก `/identify` ด้วยกรอบทั้งจังหวัด (หรือกรอบ `--area`)
2. ถ้าคืนมาเต็มเพดาน `maxRecordCount` (เช่น 500) = อาจมีตกหล่น → ผ่ากรอบเป็น 4 แล้วถามใหม่ ไล่ลงไปเรื่อย ๆ
3. กรอบที่คืนน้อยกว่าเพดาน = ได้ครบทุกรูปที่แตะกรอบนั้นแล้ว
4. รวมทุกกรอบ ตัดตัวซ้ำด้วย `FID` → ได้ polygon เต็มรูป (ไม่ถูกตัดตามกรอบ) + attribute ครบ
5. ถ้ามีกรอบที่ผ่าจนสุด (`MAX_DEPTH`) แล้วยังเต็มเพดาน จะขึ้น `[เตือน] … อาจตกหล่น`

ตรวจความถูกต้องกับ PLLU60 (ใช้ได้ทั้งสองวิธี): identify ได้ **399/399 รูป FID ตรงกันทุกตัว**
attribute หลัง export ตรงกัน 100% และ geometry ต่างกัน 0 ตร.ม. (ทดสอบทั้งเพดานจริงและบังคับเพดานต่ำให้ผ่ากรอบ)

ข้อแตกต่างที่จัดการไว้แล้ว: identify คืนช่องตัวเลขที่ว่างเป็น `0` → `FAR_MAX`/`BCR_MAX` ที่เป็น 0 ถือเป็น "ไม่ระบุ" ให้ตรงกับ `/query`

---

## Schema ของ Shapefile/GPKG ผลลัพธ์

แยกจาก schema 14 ฟิลด์ของแปลงที่ดิน — ชุดนี้เป็นของผังเมืองโดยเฉพาะ (field ≤ 10 ตัวอักษร):

| Field | ความหมาย | ที่มา |
|---|---|---|
| `PL_USE` | รหัสประเภทการใช้ที่ดิน (เช่น 1110, 3100, 8600) | field `PL_USE` |
| `PL_USE_TH` | ชื่อประเภทภาษาไทย (เช่น "ชนบทและเกษตรกรรม") | ตาราง legend |
| `ZONE_HEX` | สีผังทางการ (#rrggbb) ตาม renderer ของกรมที่ดิน | ตาราง legend |
| `FAR_MAX` | อัตราส่วนพื้นที่อาคารต่อที่ดินสูงสุด (FAR) | `PL_FAR_MAX` |
| `BCR_MAX` | อัตราส่วนพื้นที่อาคารคลุมดินสูงสุด (BCR) | `PL_BCR_MAX` |
| `DENS_H` / `DENS_L` | ความหนาแน่น สูง/ต่ำ | `PL_DENS_H/L` |
| `PLAN_NAME` | ชื่อผัง | `NAME` |
| `YEAR` | ปีผัง (พ.ศ.) | `YEAR` |
| `PROVINCE` | ชื่อจังหวัด | ตารางจังหวัด |
| `AREA_RAI` | พื้นที่ (ไร่) คำนวณจาก geometry เมตร | คำนวณ (1 ไร่ = 1600 ตร.ม.) |
| `SRC_LAYER` | ชื่อชั้นต้นทางใน service | metadata |

**CRS:** Indian 1975 / UTM Zone 47N (`24047`) หรือ 48N (`24048`) เลือกอัตโนมัติจาก CRS ที่ service ประกาศ (32647/32648)

---

## สถาปัตยกรรม (`landsmaps/cityplanning/`)

| ไฟล์ | หน้าที่ |
|---|---|
| `provinces.py` | ตารางรหัสจังหวัด ↔ ชื่อ (77 จังหวัด) = pvcode ของ service PLLU |
| `service.py` | ArcGIS REST client (metadata / objectId / feature), token, retry, เลี่ยง WAF |
| `identify.py` | ทางสำรองเมื่อ `/query` ใช้ไม่ได้: `/identify` ซอยกรอบ quadtree + ตัดซ้ำ + Esri→GeoJSON |
| `legend.py` | `PL_USE` → ชื่อไทย + สี (จาก `data/pl_use_legend.json`, merge กับ renderer ตอนรัน) |
| `export.py` | GeoJSON (4326) → reproject เป็นเมตร → SHP/GPKG |
| `pipeline.py` | รวมทุกขั้นของ 1 จังหวัด |

### หมายเหตุทางเทคนิค (ข้อจำกัดของเซิร์ฟเวอร์กรมที่ดิน)

- **WAF** บล็อก query ที่หน้าตาเหมือน SQL injection → ใช้ `where=PL_USE>=0` แทน `1=1`
- service **ไม่รองรับ pagination** → ขอ `objectId` ทั้งหมดก่อน (`returnIdsOnly`) แล้วดึงเป็นชุดละ `OID_CHUNK` รูป
- เซิร์ฟเวอร์ **บล็อก POST** ไปที่ `/query` (รหัส 555) → ใช้ GET เท่านั้น
- มี **retry** อัตโนมัติเมื่อเจอ 5xx/429 ชั่วคราว (เช่น 502 Bad Gateway)
- `f=geojson` ตอบ `content-type: text/plain` ไม่บอก charset → บังคับถอดรหัส UTF-8 (ไม่งั้นชื่อผังภาษาไทยเพี้ยน)
- identify ใช้ retry ระดับกรอบอีกชั้น (หน่วง 5→120 วินาที) เผื่อ WAF/body ว่างระหว่างดึงนาน ๆ

---

## ทดสอบ (offline, ไม่ยิง API จริง)

```powershell
python -m pytest tests/test_cityplanning.py tests/test_cityplanning_identify.py -v
```
