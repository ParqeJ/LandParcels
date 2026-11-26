# Schema — เลือกฟิลด์เสริม + ตั้งชื่อฟิลด์ output

ตั้งค่าว่าผลลัพธ์ shapefile ของ **parcel** และ **cityplanning** จะมีฟิลด์อะไรเพิ่มจากฟิลด์มาตรฐาน และตั้งชื่อฟิลด์ว่าอะไร — คลิกเลือกในหน้าเว็บ ผลถูกเก็บเป็น `schema/user_schema.json`

> 📑 สารบัญ: [← README](../README.md) · [setup](setup.md) · [dashboard](dashboard.md) · [parcel](parcel.md) · [cityplanning](cityplanning.md) · 🖥 อ่านใน dashboard: `http://localhost:8765/#docs/schema`

> ไฟล์ที่ไม่มี `base_fields` (รูปแบบเดิม) = preset ANIS POWER 14 ฟิลด์
>
> ✅ **สถานะ:** `fetch_parcels.py` / `fetch_cityplanning.py` **อ่าน** `user_schema.json` แล้ว — ตั้งค่า + Save แล้ว output จะเป็นฟิลด์ตามที่ตั้ง · ไม่มีไฟล์ หรือ parcel ไม่มี `base_fields` = คง 14/12 ฟิลด์เดิม (merge CBD/BNN ได้เหมือนเดิม)

---

## ฟิลด์ของ parcel — 3 ส่วน (หน้า 🗂 ตั้งค่าผลลัพธ์)

เปิดครั้งแรกจะติ๊กไว้ครบ **14 ฟิลด์เดิม = preset ANIS POWER** (ใช้ merge กับ CBD/BNN) — ไม่เอาตัวไหนก็ติ๊กออก / แก้ชื่อได้

| ส่วน | ฟิลด์ | มาจาก |
|---|---|---|
| **ฟิลด์หลักจาก LandsMaps** (8) | `Type_land` `Rawang` `Plang` `Cert_No` `Rai` `Ngan` `Wa` `Remark` | API / WFS — `Remark` ระบบใช้นับแปลงค้าง เอาออกไม่ได้ (เปลี่ยนชื่อได้) |
| **ฟิลด์ add-on** (กรอกเอง) | preset ANIS POWER: `Owner_Name` `Surname` `Contact_No` `Group` `LLA_no` `Status` + กด **+ เพิ่มฟิลด์ add-on** ตั้งเองได้ (str/int/float) | LandsMaps ไม่มีข้อมูล → ออกมาเป็นคอลัมน์ว่าง |
| **ฟิลด์เสริมจาก LandsMaps** | catalog 11 กลุ่ม (ด้านล่าง) | ข้อมูลดิบ API |

- ปุ่ม **LandParcels · 14 ฟิลด์เดิม** = กลับเป็นชุดเดิม · **เฉพาะที่ LandsMaps ให้** = ฟิลด์หลักอย่างเดียว ไม่มีคอลัมน์กรอกเอง
- **พรีวิว 1 แปลง** (ขวามือ): ใช้แปลงจริงจาก `cache/` (รูปแปลง WFS + รายละเอียด) → เห็นทันทีว่าติ๊ก/ตั้งชื่อแบบนี้ ผลลัพธ์ 1 แถวจะเป็นอย่างไร (ยังไม่เคยดึง = ใช้ค่าตัวอย่างจาก catalog)
- ⚠️ `Status` ในชุด preset เป็น **add-on ของโครงการ** (คอลัมน์ว่างไว้กรอกเอง) — เมื่อตั้งค่า `user_schema.json` แล้ว output จะเป็นคอลัมน์ว่าง ไม่ใช่ภาระผูกพัน LandsMaps อีก ถ้าต้องการภาระผูกพันให้เลือก `info.lands_status.*` ในฟิลด์เสริมแทน · (preset เดิมที่ยังไม่เคย Save: `Status` ยังเติม `lands_status` เหมือนเดิม)

## ฟิลด์หลักของ cityplanning (ติ๊กออก/เปลี่ยนชื่อได้)

| ส่วน | จำนวน | ฟิลด์ |
|---|---|---|
| cityplanning | 12 | `PL_USE` `PL_USE_TH` `ZONE_HEX` `FAR_MAX` `BCR_MAX` `DENS_H` `DENS_L` `PLAN_NAME` `YEAR` `PROVINCE` `AREA_RAI` `SRC_LAYER` |

- เดิมล็อกตายตัว ตอนนี้ **ติ๊กออก / เปลี่ยนชื่อได้** เหมือน parcel
- ปุ่ม **คืนค่าเริ่มต้น · 12 ฟิลด์ (merge ได้)** = กลับเป็นชุดเดิมครบ ชื่อเดิม (ค่าเริ่มต้น/ยังไม่เคย Save ก็เป็นชุดนี้ → merge ปลอดภัย)
- `cityplanning` ที่ไม่มี `base_fields` ใน `user_schema.json` (เช่นตัวอย่างด้านล่าง) = ใช้ 12 ฟิลด์เดิมครบ เหมือนกฎ `base_fields` ของ parcel

## ฟิลด์เสริมที่เลือกได้

**parcel** (`catalog_parcel.json`) — 11 กลุ่ม:
ID · เลขระวาง · เลขแปลง · ที่ตั้ง · พิกัด · ขนาด · ประเภท/ราคา · สำนักงานที่ดิน · ลิงก์ภายนอก · สถานะ · Virtual

**cityplanning** (`catalog_cityplanning.json`) — 5 กลุ่ม:
รหัสผังเมือง · ค่าควบคุม (FAR/BCR/ความหนาแน่น) · ข้อมูลผัง · ArcGIS metadata · Virtual

> ชื่อฟิลด์ดิบของผังเมืองอาจต่างกันในแต่ละจังหวัด (ขึ้นกับ ArcGIS service ของจังหวัดนั้น)

---

## วิธีตั้งค่า

### ✅ วิธีที่ 1 (แนะนำ) — หน้า 🗂 ตั้งค่าผลลัพธ์ ใน Dashboard

1. ดับเบิลคลิก `open_dashboard.bat` (ที่ root ของ LandParcels) → ไปหน้า **🗂 ตั้งค่าผลลัพธ์**
2. เลือกแท็บย่อย **parcel** / **cityplanning**
3. ติ๊กฟิลด์ที่ต้องการ → แก้ชื่อในช่องด้านขวา (≤10 ตัวอักษร) — หัวกลุ่มบอกว่าเลือกไปแล้วกี่ฟิลด์ (`2/9`)
   - ชื่อที่ใช้ไม่ได้ (ซ้ำ / ชนฟิลด์มาตรฐาน / ว่าง / เกิน 10) ขึ้น**กรอบแดง**ทันที + รายการ ⚠ ใต้ปุ่ม Save
4. กด **💾 Save user_schema.json** → เขียนลง `schema/user_schema.json` ให้เลย **ไม่ต้องย้ายไฟล์เอง**
5. **↻ Reload** = โหลดค่าที่บันทึกไว้ในไฟล์กลับมา (ทิ้งสิ่งที่แก้แต่ยังไม่ save)

### วิธีที่ 2 — Schema Editor แบบแยก (`schema_editor.html`)

ใช้เมื่อไม่อยากเปิด dashboard — **ข้อต่าง: กด Save แล้ว browser จะดาวน์โหลดไฟล์** ต้องย้าย `user_schema.json` ที่ได้มาวางใน `LandParcels/schema/` เอง (ทับของเดิม)

| วิธีเปิด | ทำยังไง |
|---|---|
| `open_editor.bat` | ดับเบิลคลิก → เปิด `http://localhost:8765/schema_editor.html` (ปิดด้วย Ctrl+C) |
| รันเอง | `cd D:\ANISPOWER\LandParcels\schema` → `python -m http.server 8765` |
| เปิดไฟล์ตรง (`file://`) | ดับเบิลคลิก `schema_editor.html` → หน้าจะให้เลือก `catalog_parcel.json` + `catalog_cityplanning.json` เอง |

- **📂 Load user_schema.json** = โหลดไฟล์ที่เคยตั้งไว้กลับมาแก้ต่อ
- ตรวจชื่อแบบเดียวกับ dashboard — มีช่องแดงอยู่ จะไม่ดาวน์โหลด/คัดลอก JSON ให้
- ⚠️ `open_editor.bat` ใช้ port **8765 เหมือน dashboard** — เปิดพร้อมกันไม่ได้ ปิดตัวหนึ่งก่อน (หรือรันเองด้วย port อื่น เช่น `python -m http.server 8766`)

---

## รูปแบบ `user_schema.json`

```json
{
  "_generated_by": "dashboard",
  "_generated_at": "2026-11-22T07:15:00Z",
  "parcel": {
    "base_fields":  [ { "field": "Rawang", "name": "Rawang" }, { "field": "Remark", "name": "Remark" } ],
    "addon_fields": [ { "name": "Owner_Name", "type": "str" }, { "name": "Plot_ID", "type": "int" } ],
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

| key | ความหมาย |
|---|---|
| `_generated_by` | `dashboard` หรือ `schema_editor.html` — ใครเป็นคนสร้าง |
| `_generated_at` | เวลาที่บันทึก (UTC, ISO 8601) |
| `extra_fields[].source` | ฟิลด์ใน `catalog_*.json` — `info.*` / `props.*` = ดึงตรงจาก API · `virtual.*` = คำนวณในฝั่ง Python |
| `extra_fields[].name` | ชื่อฟิลด์ใน shapefile (≤10 ตัวอักษร) |

ไม่มีไฟล์ = ไม่มีฟิลด์เสริม (dashboard จะแสดงว่าว่าง)

---

## โครงสร้างไฟล์ (`schema/`)

| ไฟล์ | หน้าที่ |
|---|---|
| `catalog_parcel.json` | ฟิลด์ดิบทั้งหมดของ parcel API แบ่งกลุ่ม + `fixed_fields` |
| `catalog_cityplanning.json` | ฟิลด์ดิบของ cityplanning ArcGIS service + `fixed_fields` |
| `user_schema.json` | **ค่าที่ผู้ใช้ตั้ง** — สร้างจาก dashboard/editor (ไม่มีจนกว่าจะกด Save ครั้งแรก) |
| `schema_editor.html` | editor แบบแยก (single-file) |
| `open_editor.bat` | launcher ของ editor แบบแยก |

ฟิลด์แต่ละตัวใน catalog มี `source` `label` `desc` `type` `example` — `label` คือชื่อตั้งต้นที่โผล่ในช่องชื่อ

---

## กฎทอง

- ❌ **ห้ามแก้ `fixed_fields`** ใน catalog — pipeline merge ใช้ชื่อเหล่านี้
- ❌ **ห้ามเกิน 10 ตัวอักษร** — DBF ของ shapefile ตัดชื่อยาวเกินเงียบ ๆ (ช่องในหน้าเว็บพิมพ์ได้แค่ 10 ตัว และ server ปฏิเสธถ้าเกิน)
- ❌ **ห้ามชื่อซ้ำ** — ทั้งซ้ำกันเองและซ้ำกับฟิลด์ fixed (เช่นตั้งชื่อ `Rai` ให้ฟิลด์เสริม) ไม่สนตัวพิมพ์เล็ก/ใหญ่ (`lat` = `Lat` ใน DBF) — **ระบบตรวจให้แล้ว** ทั้ง dashboard, editor แบบแยก และ server: ช่องที่ผิดขึ้นกรอบแดงและกด Save ไม่ได้จนกว่าจะแก้
- ✅ ใช้ตัวอักษรอังกฤษ/ตัวเลข/`_` — ชื่อภาษาไทยใน DBF เปิดใน ArcGIS/QGIS บางเวอร์ชันแล้วเพี้ยน

---

## Troubleshooting

| อาการ | สาเหตุ / แก้ |
|---|---|
| แท็บ Schema ขึ้น `ไม่พบ catalog_parcel.json` | ต้องมี `schema/catalog_parcel.json` + `schema/catalog_cityplanning.json` |
| กด Save แล้วขึ้น `✗ ยังไม่บันทึก — แก้ชื่อที่ขึ้นกรอบแดง` | ชี้เมาส์ที่ช่องแดงดูสาเหตุ: ซ้ำกับฟิลด์อื่น / ชนฟิลด์มาตรฐาน / ว่าง / เกิน 10 ตัว — แก้ให้ครบแล้ว Save ใหม่ |
| `open_editor.bat` เปิดไม่ขึ้น / port ถูกใช้ | dashboard เปิดอยู่ที่ 8765 — ใช้แท็บ Schema ใน dashboard แทน หรือปิด dashboard ก่อน |
| เปิด `schema_editor.html` ตรง ๆ แล้วไม่มีฟิลด์ | browser บล็อกการอ่านไฟล์จาก `file://` — กดเลือก catalog เองตามที่หน้าบอก หรือเปิดผ่าน `open_editor.bat` |
| ตั้งค่าแล้วแต่ output ไม่มีฟิลด์เสริม | เช็กว่ากด **Save** แล้ว (เขียน `schema/user_schema.json` จริง) + ดึงใหม่อีกครั้ง — ไฟล์ที่ไม่มี `base_fields` (parcel) จะถูกมองเป็น preset เดิม |
