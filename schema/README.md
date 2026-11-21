# Schema Editor — คู่มือสั้น

Local HTML editor สำหรับ **เลือกฟิลด์เสริม + ตั้งชื่อ custom** ของผลลัพธ์ parcel และ cityplanning

---

## วิธีเปิด

### วิธีที่ 1 (แนะนำ) — ดับเบิลคลิก `open_editor.bat`

เปิด HTTP server ชั่วคราวที่ port 8765 + เปิด browser ให้อัตโนมัติ
ปิด server ด้วย Ctrl+C ในหน้าต่าง cmd

### วิธีที่ 2 — รัน command เอง

```powershell
cd D:\ANISPOWER\LandParcels\schema
python -m http.server 8765
```

แล้วเปิด <http://localhost:8765/schema_editor.html>

### วิธีที่ 3 — เปิดไฟล์ตรงๆ (file://)

ดับเบิลคลิก `schema_editor.html` → หน้าจะให้เลือก `catalog_parcel.json` + `catalog_cityplanning.json` เอง ก่อนใช้งาน

---

## ขั้นตอนใช้งาน

1. **เลือกฟิลด์** — ติ๊ก checkbox ฟิลด์ที่ต้องการเพิ่มเข้า output (นอกเหนือ fixed 14/12 ฟิลด์ที่ถูกล็อกไว้)
2. **ตั้งชื่อฟิลด์** — ชื่อ output ของ shapefile ยาวสูงสุด 10 ตัวอักษร (ข้อจำกัดของ DBF)
3. **กด 💾 Save user_schema.json** — browser จะดาวน์โหลดไฟล์ให้
4. **ย้ายไฟล์** — วาง `user_schema.json` ที่ดาวน์โหลดเข้า `LandParcels/schema/user_schema.json`
5. **Python จะอ่านอัตโนมัติ** — ถ้าไฟล์ `user_schema.json` มีอยู่ ครั้งถัดไปที่รัน `fetch_parcels.py` / `fetch_cityplanning.py` จะเพิ่มฟิลด์ตามที่ตั้งไว้ (ยังไม่ hook; อยู่ในขั้นถัดไป)

---

## โครงสร้างไฟล์

| ไฟล์ | หน้าที่ |
|---|---|
| `catalog_parcel.json` | รายการฟิลด์ดิบทั้งหมดของ parcel API + กลุ่ม + fixed_fields |
| `catalog_cityplanning.json` | รายการฟิลด์ดิบของ cityplanning ArcGIS service |
| `schema_editor.html` | หน้า editor (single-file) |
| `open_editor.bat` | launcher สำหรับ Windows |
| `user_schema.json` | **ผลลัพธ์จาก editor** — Python อ่านไฟล์นี้เพื่อตัดสินใจเพิ่มฟิลด์ (**ยังไม่มี** — ต้อง generate จาก editor) |

---

## รูปแบบ `user_schema.json`

```json
{
  "_generated_by": "schema_editor.html",
  "_generated_at": "2026-11-22T00:50:12.345Z",
  "parcel": {
    "extra_fields": [
      { "source": "info.parcel_seq", "name": "ParcelSeq" },
      { "source": "info.parcellat",  "name": "Lat" }
    ]
  },
  "cityplanning": {
    "extra_fields": [
      { "source": "virtual.area_m2", "name": "AreaM2" }
    ]
  }
}
```

- `source` อ้างฟิลด์ใน `catalog_*.json`
  - `info.*` / `props.*` = ดึงตรงจาก API
  - `virtual.*` = คำนวณในฝั่ง Python
- `name` = ชื่อฟิลด์ใน shapefile (≤10 chars, DBF limit)
- ฟิลด์ใน `fixed_fields` ของ catalog **ไม่ต้องใส่** (Python จะใช้ค่าดีฟอลต์ 14/12 ฟิลด์เสมอ)

---

## กฎทอง

- ❌ **ห้ามแก้ `fixed_fields`** ใน catalog — pipeline merge ใช้ชื่อเหล่านี้
- ❌ **ห้ามตั้งชื่อ custom ทับชื่อ fixed** — editor จะล็อกให้แล้ว แต่ถ้า edit JSON เองระวังด้วย
- ❌ **ห้ามเกิน 10 ตัวอักษร** — ESRI Shapefile DBF ตัดฟิลด์ยาวเกินเงียบๆ
