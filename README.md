# LandsMaps — แปลงที่ดิน + ผังเมือง จากกรมที่ดิน

Python tool ดึง **แปลงที่ดินโฉนด/น.ส.3ก** และ **ผังเมืองรายจังหวัด** จาก [LandsMaps กรมที่ดิน](https://landsmaps.dol.go.th/) ออกมาเป็น Shapefile/GPKG พร้อม overlay ใน QGIS/ArcGIS Pro ได้ทันที

---

## 📑 สารบัญ

| คู่มือ | ใช้เมื่อ |
|---|---|
| **[docs/setup.md](docs/setup.md)** | ติดตั้งครั้งแรก, เตรียมบัญชี, โครงสร้างไฟล์, ไฟล์ secret, กฎทั่วไป |
| **[docs/parcel.md](docs/parcel.md)** | ดึง **แปลงที่ดิน** โฉนด/น.ส.3ก ตามขอบเขตพื้นที่ (`fetch_parcels.py`) |
| **[docs/cityplanning.md](docs/cityplanning.md)** | ดึง **ผังเมืองรวม** รายจังหวัด (`fetch_cityplanning.py`) |

ไฟล์ใน `docs/` แต่ละไฟล์มีลิงก์ breadcrumb กลับมาที่สารบัญ (README.md) และลิงก์ข้ามไฟล์กัน — เปลี่ยนไปอ่านอีกไฟล์ได้ด้วยคลิกเดียว

---

## 2 Features ย่อ ๆ

| Feature | Entry point | ผลลัพธ์ | Token |
|---|---|---|---|
| **แปลงที่ดิน** | `python fetch_parcels.py` | `output/<area>/*_parcel_epsg240xx.shp` (14 ฟิลด์) | DGA (บัญชีทางรัฐ) |
| **ผังเมือง** | `python fetch_cityplanning.py <รหัสจังหวัด>` | `output/cityplanning/<prov>/*_cityplanning_epsg240xx.shp` (12 ฟิลด์) | ArcGIS token ของ LandsMaps |

CRS อัตโนมัติ: **EPSG:24047** (ตะวันตก 102°E) หรือ **24048** (ตะวันออก 102°E) — Indian 1975 UTM หน่วยเมตร

---

## Quick Start

```bash
# 1) clone + ติดตั้ง
git clone https://github.com/ParqeJ/LandParcels.git
cd LandParcels
pip install -r requirements.txt

# 2) ลองทดสอบด้วยพื้นที่ตัวอย่าง (ไม่ต้องล็อกอิน ไม่ใช้โควตา)
python fetch_parcels.py examples/sample_area.geojson --no-detail

# 3) ลองดึงผังเมืองจังหวัดที่เปิดสาธารณะ (60 = นครสวรรค์)
python fetch_cityplanning.py 60
```

รายละเอียดการกรอกบัญชี, token, โควตา, troubleshooting → ดู [docs/parcel.md](docs/parcel.md) และ [docs/cityplanning.md](docs/cityplanning.md)

---

## ข้อควรทราบเรื่องการใช้ข้อมูล

- ข้อมูลทั้งหมดเป็นของ **กรมที่ดิน** ดึงจากบริการสาธารณะของ LandsMaps ตามสิทธิ์ของผู้ใช้แต่ละคน
- เครื่องมือนี้ไม่ได้หลบเลี่ยงโควตาหรือการยืนยันตัวตน (ล็อกอินด้วยบัญชีของผู้ใช้เองตามขั้นตอนเดียวกับปุ่มในเว็บ) และหน่วงเวลาระหว่างคำขอเพื่อไม่ให้รบกวนระบบ
- ผลลัพธ์ใช้ประกอบการวางแผน/สำรวจเบื้องต้นเท่านั้น **ไม่ใช่เอกสารทางกฎหมาย** ตรวจสอบกับสำนักงานที่ดินก่อนใช้อ้างอิงเสมอ
- โปรดใช้ข้อมูลตามกฎหมายคุ้มครองข้อมูลส่วนบุคคล (PDPA) และเงื่อนไขการใช้งานของกรมที่ดิน
