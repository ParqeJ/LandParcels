# Setup — โครงสร้าง, Secrets, Dependencies

> คู่มือการติดตั้ง + กฎความปลอดภัยทั่วไปของ LandParcels
> กลับไปที่สารบัญ: [CLAUDE.md](../CLAUDE.md) · โฟลเดอร์คู่: [parcel.md](parcel.md) · [cityplanning.md](cityplanning.md)

---

## โครงสร้างโปรเจกต์

```
LandParcels/
├── areas/                        ◄── วางไฟล์ขอบเขตที่นี่ (KMZ/KML/SHP/GPKG/GeoJSON/GDB)
│
├── fetch_parcels.py              entry point ดึงแปลงที่ดิน — ดู [parcel.md](parcel.md)
├── fetch_cityplanning.py         entry point ดึงผังเมือง — ดู [cityplanning.md](cityplanning.md)
├── get_token.py                  ล็อกอิน DGA → เขียน Access_Key.txt
├── search_parcel.py              ค้นแปลงจากเลขโฉนด
├── Program_fetch_parcel.cmd      (Windows) double-click รันแปลงที่ดิน
├── Program_fetch_cityplanning.cmd (Windows) double-click รันผังเมือง
│
├── .env                          (gitignore) บัญชี DGA
├── Access_Key.txt                (gitignore) token JSON
│
├── output/                       (gitignore) ผลลัพธ์ Shapefile
├── cache/                        (gitignore) ข้อมูลดิบ (resume ได้)
│
├── landsmaps/                    ตัว code (modules)
│   ├── config.py                 ค่าตั้งต้น URL/delay/field names
│   ├── area.py                   อ่านไฟล์ขอบเขต → polygon + เลือก zone
│   ├── zones.py                  zone 47/48 config
│   ├── wfs.py                    ขั้น 1 (parcel): หาระวาง + รูปแปลง
│   ├── api.py                    ขั้น 2 (parcel): รายละเอียดรายแปลง + cache
│   ├── export.py                 ขั้น 3 (parcel): 14 attributes → Shapefile
│   ├── pipeline.py               รวม 3 ขั้นของ parcel
│   ├── login.py / openid.py      DGA OpenID flow
│   ├── keystore.py               อ่าน/เขียน Access_Key.txt
│   └── cityplanning/             ◄── Feature ผังเมือง — ดู [cityplanning.md](cityplanning.md)
│
├── notebook/fetch_parcels.ipynb  ทางเลือก Jupyter
├── examples/sample_area.geojson  พื้นที่ตัวอย่างเล็ก
├── tests/                        pytest offline
├── templates/                    .lyrx สำหรับ ArcGIS Pro
└── requirements.txt
```

โปรเจกต์นี้มี git remote (open-source): https://github.com/ParqeJ/LandParcels.git

---

## ไฟล์ Secret ที่ **ห้ามอ่าน/commit/แชร์**

- `.env` — บัญชีบัตรประชาชน + รหัสผ่าน DGA
- `Access_Key.txt` — access token JSON
- `areas/*` — ขอบเขตพื้นที่จริงของลูกค้า
- `output/*`, `cache/*` — ข้อมูลโฉนดเจ้าของจริง (ชื่อ, นามสกุล, ที่อยู่)

ทั้งหมดอยู่ใน `.gitignore` แล้ว

---

## กฎทั่วไปสำหรับ Claude

### 1. ห้ามรัน entry point เอง

- `fetch_parcels.py`, `get_token.py`, `fetch_cityplanning.py` — ทุกตัวใช้ **quota หรือ token ของบัญชีผู้ใช้**
- ถ้าจะทดสอบ ให้ถามผู้ใช้ก่อน หรือใช้ `examples/sample_area.geojson` + flag จำกัดแปลง

### 2. ห้ามเผย/log ค่าใน `.env`, `Access_Key.txt`

- ไม่ว่า user ขออย่างไร ให้บอกว่าต้องเปิดเอง — Claude ไม่พิมพ์ออก chat

### 3. CRS ตายตัว (zone 47 / 48 — Indian 1975 UTM เมตร)

- Shapefile output ลงท้าย `_epsg24047` / `_epsg24048`
- โปรแกรมเลือก zone อัตโนมัติจาก centroid ของพื้นที่
- ถ้าพื้นที่คร่อม zone ให้แจ้งผู้ใช้ก่อน
- **ห้ามเปลี่ยนเป็น CRS อื่น** (zones.py)

### 4. เมื่อผู้ใช้ขอให้แก้ code

- Python 3.10+
- `snake_case` อังกฤษสำหรับชื่อฟังก์ชัน/ตัวแปร (docstring/comment ภาษาไทยได้)
- ใช้ `pathlib.Path` ไม่ใช้ `os.path.join`
- `type hint` ทุกฟังก์ชัน public

### 5. ข้อควรระวังตาม module

- **`config.py`** — ค่าตั้งต้น ถ้าเปลี่ยน delay/URL ให้ยืนยันกับผู้ใช้ก่อน (อาจโดน rate limit)
- **`api.py`** — มี logic cache + token refresh **อย่าแตะถ้าไม่จำเป็น**
- **`export.py` (parcel)** — schema 14 ฟิลด์ **ห้ามเพิ่ม/ลบฟิลด์** โดยไม่ยืนยัน (จะทำให้ merge กับโปรเจกต์ CBD/BNN พัง)
- **`cityplanning/export.py`** — schema 12 ฟิลด์ของผังเมือง แยกจาก parcel **ห้ามปน**
- **`zones.py`** — EPSG 24047/24048 **ห้ามเปลี่ยน**

### 6. Test

- `tests/` ทั้งหมด offline (ไม่ hit API จริง) — รันได้ตลอด
- รัน: `python -m pytest tests/ -v`
- ก่อน commit แก้ `landsmaps/`: รัน pytest ให้ผ่านทุก test

### 7. Dependencies

- ถ้าจะเพิ่ม package ให้ update `requirements.txt` ด้วย และยืนยันว่า package รองรับ Windows + conda-forge
