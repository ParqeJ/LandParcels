# LandParcels — คำแนะนำสำหรับ Claude

Python tool ดึง **แปลงที่ดินโฉนด + น.ส.3ก** และ **ผังเมืองรายจังหวัด** จาก [LandsMaps กรมที่ดิน](https://landsmaps.dol.go.th/) → Shapefile/GPKG พร้อม overlay ใน QGIS/ArcGIS

> อ่าน `.claude/CLAUDE.md` ของ workspace root ก่อน (`../../.claude/CLAUDE.md`)
> โปรเจกต์นี้มี git remote (open-source): https://github.com/ParqeJ/LandParcels.git

---

## 📑 สารบัญ

**หลัก (คู่มือฉบับเต็มของผู้ใช้):**

| ไฟล์ | เมื่อไหร่ควรอ่าน |
|---|---|
| **[../README.md](../README.md)** | สารบัญหลัก + hero + quick start |
| **[../docs/setup.md](../docs/setup.md)** | โครงสร้างโปรเจกต์, secrets, dependencies, กฎทั่วไป, CRS, test — **อ่านเสมอก่อนเริ่มงานใหม่** |
| **[../docs/parcel.md](../docs/parcel.md)** | ทำงานกับ `fetch_parcels.py`, `search_parcel.py`, 14-field schema โฉนด/น.ส.3ก, DGA token, quota |
| **[../docs/cityplanning.md](../docs/cityplanning.md)** | ทำงานกับ `fetch_cityplanning.py` (เดิมชื่อ landuse), 12-field schema ผังเมือง, ArcGIS token, identify/query |
| **[../docs/dashboard.md](../docs/dashboard.md)** | ทำงานกับ `dashboard/` (FastAPI + หน้าเว็บ): input อัปโหลด/ลบ, schema, run, monitor, output, หน้า 📖 คู่มือ |
| **[../docs/schema.md](../docs/schema.md)** | `schema/catalog_*.json`, `user_schema.json`, กฎตั้งชื่อฟิลด์เสริม (≤10, ห้ามซ้ำ/ชน fixed) |

**สำรอง (Claude-focused brief guides — มีทั้งคู่ไว้เผื่อค้นหาตรงนี้):**

- [guides/setup.md](guides/setup.md) · [guides/parcel.md](guides/parcel.md) · [guides/cityplanning.md](guides/cityplanning.md)

---

## กฎเร่งด่วน (Top 5)

1. **ห้ามรัน `fetch_parcels.py` / `get_token.py` / `fetch_cityplanning.py` เอง** — ใช้ quota/token ของบัญชีผู้ใช้
2. **ห้ามเผย/log ค่า** ใน `.env`, `Access_Key.txt` (secrets)
3. **ค่าเริ่มต้นต้องคง preset เดิมไว้เพื่อ merge** — parcel 14 ฟิลด์ (merge กับ CBD/BNN) · cityplanning 12 ฟิลด์ (ชื่อเดิม) เป็น **ค่าเริ่มต้น** ที่ merge ได้ · ผู้ใช้ติ๊กออก/เปลี่ยนชื่อได้เองทั้งสอง (parcel เพิ่ม add-on ได้ด้วย) ในหน้า ตั้งค่าผลลัพธ์ (`user_schema.json`) · ปุ่ม "คืนค่าเริ่มต้น" กลับชุดเดิมได้เสมอ — **อย่าตั้งชื่อ preset ของ cityplanning ว่า ANIS POWER**
4. **ห้ามเปลี่ยน CRS** `zones.py` (EPSG 24047/24048 เท่านั้น)
5. **`LandusePlan` / `PLLU`** ใน code คือชื่อ URL/service จริงของกรมที่ดิน — ห้ามเปลี่ยน

รายละเอียดเต็มอยู่ใน [guides/setup.md](guides/setup.md)

---

## ลำดับความสำคัญเมื่อเริ่มงาน

1. ผู้ใช้ถามเรื่อง "แปลงที่ดิน / โฉนด / น.ส.3ก / Owner / Rawang" → เปิด [guides/parcel.md](guides/parcel.md)
2. ผู้ใช้ถามเรื่อง "ผังเมือง / PL_USE / FAR / BCR / จังหวัด-รหัส 2 หลัก" → เปิด [guides/cityplanning.md](guides/cityplanning.md)
3. ผู้ใช้ถามเรื่องติดตั้ง / token / dependencies / test / CRS / โครงสร้างไฟล์ → เปิด [guides/setup.md](guides/setup.md)

---

## เชื่อมกับ sub-project อื่นใน workspace

- `01_CBD_BNN/` ใช้ output ของ parcel แล้ว export เป็น `*_Landsmaps` layer
- `02_Amnatcharoen/` อาจใช้ parcel ในอนาคต
- "ดึงข้อมูลที่ดินของโครงการ X" → พาเขามาที่นี่ (วาง KMZ ใน `areas/` → รัน `fetch_parcels.py`)
- "ขอผังเมืองจังหวัด X" → พาเขามาที่นี่ (`fetch_cityplanning.py <รหัสจังหวัด>`)
