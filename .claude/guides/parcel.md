# Parcel — ดึงแปลงที่ดินโฉนด + น.ส.3ก

> Feature หลัก: `fetch_parcels.py` → Shapefile โฉนด/น.ส.3ก พร้อม 14 attributes
> กลับไปที่สารบัญ: [CLAUDE.md](../CLAUDE.md) · โฟลเดอร์คู่: [setup.md](setup.md) · [cityplanning.md](cityplanning.md)
> README ผู้ใช้: [README.md](../../README.md)

---

## Entry points

| คำสั่ง | ใช้ทำอะไร |
|---|---|
| `python get_token.py` | ล็อกอิน + บันทึก token (`Access_Key.txt` + `.env`) |
| `python fetch_parcels.py` | ดึงทุก area ใน `areas/` → `output/<area>/...shp` |
| `python fetch_parcels.py areas/x.kmz --no-detail` | แค่รูปแปลง ไม่ล็อกอิน ไม่ใช้โควตา |
| `python fetch_parcels.py --refetch mismatch` | ดึงซ้ำเฉพาะแปลงที่ผลเดิมชี้ไปแปลงอื่น |
| `python search_parcel.py --prov 36 --amphur 07 30219` | ค้นจากเลขโฉนด |
| `python -m pytest tests/` | รัน test parcel (offline) |

---

## Token / Quota

- access token DGA อายุ **24 ชม.** — `fetch_parcels.py` **ล็อกอินใหม่ทุกครั้งที่รัน** (ไม่เช็กว่าของเดิมหมดอายุหรือยัง)
- **โควตาการค้นรายละเอียด/วัน** (รูปแปลง WFS ไม่จำกัด):
  - ไม่ล็อกอิน: ~20–40 แปลง
  - ล็อกอินด้วย DGA: ~200–400 แปลง
- เมื่อโควตาเต็ม โปรแกรมจะหยุดเองแล้วบันทึก Shapefile (แปลงที่ยังไม่ได้ดึงมี Remark = `ยังไม่ได้ดึงรายละเอียด`) รันซ้ำวันถัดไปจะทำต่อจาก cache

---

## Resume logic

| ไฟล์ | เก็บอะไร | ลบได้ไหม |
|---|---|---|
| `cache/<name>_detail.jsonl` | รายละเอียดรายแปลงที่ดึงแล้ว (รวมแปลงที่ค้นแล้วไม่พบ) | **ไม่ควร** — ใช้โควตาไปแล้ว |
| `cache/parcel_<ระวาง>_<name>.json` | รูปแปลงจาก WFS | ได้ — ดึงใหม่ฟรี |
| `cache/ns3k_<ระวาง>_<name>.json` | รูปแปลง น.ส.3ก จาก WFS | ได้ — ดึงใหม่ฟรี |

- cache ผูกกับ **ชื่อพื้นที่** (ชื่อไฟล์ขอบเขต) — เปลี่ยนชื่อไฟล์จะเริ่มนับใหม่ (ใช้ `--name` เพื่อใช้ cache เดิม)
- รัน `fetch_parcels.py` ซ้ำจะทำต่อจากที่ค้าง ไม่ดึงซ้ำ

---

## Schema: 14 attributes ของ `output/<area>/*_parcel_epsg240xx.shp`

ใช้ schema เดียวกับ `01_CBD_BNN/` (ดู `../../../01_CBD_BNN/.claude/CLAUDE.md`):

| Field | ความหมาย | ที่มา |
|---|---|---|
| `Owner_Name` | ชื่อเจ้าของ | เว้นว่าง — LandsMaps ไม่เปิดเผย |
| `Surname` | นามสกุล | เว้นว่าง |
| `Contact_No` | เบอร์ติดต่อ | เว้นว่าง |
| `Type_land` | ประเภทเอกสารสิทธิ์ (โฉนด / น.ส.3ก) | API |
| `Rawang` | ระวาง เช่น `5339 IV 7808-00` | API |
| `Group` | กลุ่ม | เว้นว่างไว้กรอกเอง |
| `Plang` | เลขที่ดิน | WFS |
| `Cert_No` | เลขโฉนด (ตำแหน่ง = `xxxx19`; search = เต็ม) | API |
| `Rai` `Ngan` `Wa` | เนื้อที่ตามเอกสาร (Wa รวมเศษวาเป็นทศนิยม) | API |
| `Status` | ภาระผูกพัน เช่น `obligation:จำนอง` | API |
| `LLA_no` | | เว้นว่างไว้กรอกเอง |
| `Remark` | ว่าง = ครบ / `ยังไม่ได้ดึงรายละเอียด` / `ไม่พบรายละเอียดใน LandsMaps` / `ตำแหน่งชี้ไปแปลงอื่น` / `ถูกแปลงอื่นทับทั้งหมด` | |

ไฟล์ `*_ns3k_*` (น.ส.3ก) มีแค่รูปแปลง + เลขที่ดิน (LandsMaps ไม่มี API รายละเอียดจากตำแหน่ง)

**ห้ามเพิ่ม/ลบ/เปลี่ยนชื่อฟิลด์** โดยไม่ยืนยันกับผู้ใช้ — จะทำให้ merge กับ `01_CBD_BNN/` พัง

---

## Pipeline (`landsmaps/pipeline.py`)

```
areas/*.kmz → area.py (polygon + zone 47/48)
            → wfs.py ขั้น 1 (ดัชนีระวาง → รูปแปลงโฉนด + น.ส.3ก)
            → probe.py (ตัดส่วนที่แปลงอื่นทับ, เลือกจุดค้นลึกสุด)
            → api.py ขั้น 2 (รายละเอียดทีละแปลง, หน่วง 1s, cache jsonl, quota)
            → export.py ขั้น 3 (14 attributes → Shapefile)
```

---

## ความเชื่อมโยงกับ sub-project อื่น

- `01_CBD_BNN/` ใช้ output ของ tool นี้แล้ว export เป็น `*_Landsmaps` layer
- `02_Amnatcharoen/` เป็นโปรเจกต์ใหม่ที่อาจจะใช้ tool นี้ในอนาคต
- ถ้าผู้ใช้ขอ "ดึงข้อมูลที่ดินของโครงการ X" → พาเขาไปที่นี่ (วาง KMZ ใน `areas/` แล้วรัน)
