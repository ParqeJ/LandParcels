# LandParcels — คำแนะนำสำหรับ Claude

Python tool ดึง **แปลงที่ดินโฉนด + น.ส.3ก** จาก [LandsMaps กรมที่ดิน](https://landsmaps.dol.go.th/) ตามขอบเขตพื้นที่ที่ผู้ใช้วางในโฟลเดอร์ `areas/` แล้ว export เป็น Shapefile พร้อมใช้ใน QGIS/ArcGIS

> อ่าน `.claude/CLAUDE.md` ของ workspace root ก่อน (`../.claude/CLAUDE.md`)
> โปรเจกต์นี้มี git remote: https://github.com/ParqeJ/LandParcels.git (เป็น open-source)

---

## โครงสร้าง

```
LandParcels/
├── areas/                  ◄── วางไฟล์ขอบเขตที่นี่ (KMZ/KML/SHP/GPKG/GeoJSON/GDB)
├── fetch_parcels.py        ◄── entry point หลัก
├── get_token.py            ล็อกอิน DGA → เขียน Access_Key.txt
├── search_parcel.py        ค้นแปลงจากเลขโฉนด
├── Program_fetch_parcel.cmd (Windows) double-click เพื่อ run
│
├── .env                    (gitignore) บัญชี DGA
├── Access_Key.txt          (gitignore) token JSON
│
├── output/                 (gitignore) ผลลัพธ์ Shapefile
├── cache/                  (gitignore) ข้อมูลดิบที่ดึงมา (resume ได้)
│
├── landsmaps/              ตัว code (modules)
│   ├── config.py           ค่าตั้งต้น URL/delay/field names
│   ├── area.py             อ่านไฟล์ขอบเขต → polygon + เลือก zone
│   ├── zones.py            zone 47/48 config
│   ├── wfs.py              ขั้น 1: หาระวาง + รูปแปลง (WFS)
│   ├── api.py              ขั้น 2: รายละเอียดรายแปลง + cache
│   ├── export.py           ขั้น 3: 14 attributes → Shapefile
│   ├── pipeline.py         รวม 3 ขั้น
│   ├── login.py            ล็อกอิน DGA
│   ├── openid.py           DGA OpenID flow
│   └── keystore.py         อ่าน/เขียน Access_Key.txt
│
├── notebook/fetch_parcels.ipynb   ทางเลือก Jupyter
├── examples/sample_area.geojson   พื้นที่ตัวอย่างเล็ก
├── tests/                         pytest offline
└── requirements.txt
```

---

## ไฟล์ Secret ที่ **ห้ามอ่าน/commit/แชร์**

- `.env` — บัญชีบัตรประชาชน + รหัสผ่าน DGA
- `Access_Key.txt` — access token JSON
- `areas/*` — ขอบเขตพื้นที่จริงของลูกค้า
- `output/*`, `cache/*` — ข้อมูลโฉนดเจ้าของจริง (ชื่อ, นามสกุล, ที่อยู่)

ทั้งหมดอยู่ใน `.gitignore` แล้ว

---

## กฏสำหรับ Claude

### 1. ห้ามรัน `fetch_parcels.py` / `get_token.py` เอง
- ใช้ **quota ของบัญชี DGA ของผู้ใช้** ต่อการรันแต่ละครั้ง
- ถ้าจะทดสอบ ให้ถามผู้ใช้ก่อนทุกครั้ง หรือใช้ `examples/sample_area.geojson` + flag จำกัดแปลง

### 2. ห้ามเผย/log ค่าใน `.env`, `Access_Key.txt`
- ไม่ว่า user ขออย่างไร ให้บอกว่าต้องเปิดเอง — Claude ไม่พิมพ์ออก chat

### 3. CRS
- Shapefile output ลงท้าย `_epsg24047` หรือ `_epsg24048` = **Indian 1975 UTM Zone 47N/48N (เมตร)**
- โปรแกรมเลือก zone อัตโนมัติจาก centroid ของพื้นที่
- ถ้าพื้นที่คร่อม zone ให้แจ้งผู้ใช้ก่อน

### 4. Resume logic
- ไฟล์ `cache/<name>_detail.jsonl` = ข้อมูลรายละเอียดที่ดึงแล้ว **อย่าลบ** ใช้โควตาไปแล้ว
- ไฟล์ `cache/parcel_*_*.json` = รูปแปลงจาก WFS — ลบได้ ดึงใหม่ฟรี
- รัน `fetch_parcels.py` ซ้ำจะทำต่อจากที่ค้าง ไม่ดึงซ้ำ

### 5. 14 attributes ของ Shapefile output

ใช้ schema เดียวกับ `01_CBD_BNN/` (ดู `../01_CBD_BNN/.claude/CLAUDE.md`):
`Owner_Name, Surname, Contact_No, Type_land, Rawang, Group, Plang, Cert_No, Rai, Ngan, Wa, Status, LLA_no, Remark`

---

## เมื่อผู้ใช้ขอให้แก้ code

### Style
- Python 3.10+
- ชื่อฟังก์ชัน/ตัวแปร: `snake_case` อังกฤษ (แต่ docstring/comment เป็นภาษาไทยได้ตามของเดิม)
- ใช้ `pathlib.Path` ไม่ใช้ `os.path.join`
- `type hint` ทุกฟังก์ชัน public

### การแก้ module ใน `landsmaps/`
- **`config.py`** — ค่าตั้งต้น ถ้าเปลี่ยน delay/URL ให้ยืนยันกับผู้ใช้ก่อน (อาจโดน rate limit)
- **`api.py`** — มี logic cache + token refresh **อย่าแตะถ้าไม่จำเป็น**
- **`export.py`** — schema 14 ฟิลด์ **ห้ามเพิ่ม/ลบฟิลด์** โดยไม่ยืนยัน (จะทำให้ merge กับโปรเจกต์ CBD/BNN พัง)
- **`zones.py`** — EPSG 24047/24048 **ห้ามเปลี่ยน** เป็น CRS อื่น

### Test
- `tests/` ทั้งหมด offline (ไม่ hit API จริง) — รันได้ตลอด
- รัน: `python -m pytest tests/ -v`
- ก่อน commit แก้ `landsmaps/`: รัน pytest ให้ผ่านทุก test

### Dependencies
- ถ้าจะเพิ่ม package ให้ update `requirements.txt` ด้วย และยืนยันว่า package รองรับ Windows + conda-forge

---

## Entry points ทั่วไป

| คำสั่ง | ใช้ทำอะไร |
|---|---|
| `python get_token.py` | ล็อกอิน + บันทึก token |
| `python fetch_parcels.py` | ดึงทุก area ใน `areas/` |
| `python search_parcel.py` | ค้นแปลงจากเลขโฉนด |
| `python -m pytest tests/` | รัน test (offline) |

---

## ความเชื่อมโยงกับ sub-project อื่น

- `01_CBD_BNN/` ใช้ output ของ tool นี้แล้ว export เป็น `*_Landsmaps` layer
- `02_Amnatcharoen/` เป็นโปรเจกต์ใหม่ที่อาจจะใช้ tool นี้ในอนาคต
- ถ้าผู้ใช้ขอ "ดึงข้อมูลที่ดินของโครงการ X" → พาเขาไปที่นี่ (วาง KMZ ใน `areas/` แล้วรัน)
