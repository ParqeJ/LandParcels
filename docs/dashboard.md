# LandParcels Dashboard

Local web UI รวมทุกอย่างที่ใช้ทำงานกับ LandsMaps ในหน้าเดียว — **ไม่ต้องพิมพ์คำสั่ง ไม่ต้องคัดลอกไฟล์เอง**

🔐 บัญชี LandsMaps · 📥 ลากวาง/ลบไฟล์ขอบเขต · 🗂 schema (เลือกฟิลด์ + ตั้งชื่อ) · ▶ run parcel / cityplanning · 📊 live log + map · 📤 ดาวน์โหลดผล · ☀️/🌙 ธีมสว่าง-มืด

> 📑 สารบัญ: [← README](../README.md) · [setup](setup.md) · [parcel](parcel.md) · [cityplanning](cityplanning.md) · [schema](schema.md) · 🖥 อ่านใน dashboard: `http://localhost:8765/#docs/dashboard`

---

## วิธีเปิด

### ดับเบิลคลิก launcher (Windows)
```
D:\ANISPOWER\LandParcels\open_dashboard.bat
```

Launcher จะ:
1. เช็ค `fastapi`, `uvicorn`, `python-multipart` — ติดตั้งให้ถ้ายังไม่มี
2. เปิด `http://localhost:8765` ใน browser
3. รัน uvicorn server (ปิดด้วย Ctrl+C)

### หรือรันเองจาก terminal
```powershell
cd D:\ANISPOWER\LandParcels
pip install fastapi uvicorn python-multipart
python -m uvicorn dashboard.server:app --host 127.0.0.1 --port 8765
```

> ⚠️ ใช้ `--host 127.0.0.1` เท่านั้น **อย่าใช้ `0.0.0.0`** — dashboard รับรหัสผ่านและเขียนไฟล์ได้ ถ้าเปิดออกเครือข่ายคนอื่นจะสั่งงานแทนคุณได้

ลิงก์ตรงเข้าแต่ละหน้าได้ด้วย `#ชื่อหน้า` เช่น `http://localhost:8765/#account`, `#input`, `#output` (กด refresh แล้วอยู่หน้าเดิม)

---

## โฟลว์ใช้งาน

### 0) 🔐 บัญชี LandsMaps (ครั้งแรก / ทุก 24 ชม.)

ป้าย **LandsMaps** มุมขวาบนบอกสถานะตลอด: 🟢 เข้าสู่ระบบแล้ว (เหลือกี่ชั่วโมง) · 🟠 token หมดอายุ · ⚪ ยังไม่เข้าสู่ระบบ — คลิกป้ายเพื่อไปหน้าบัญชี

- ใช้ **บัญชีของ LandsMaps กรมที่ดิน** (ปุ่ม "เข้าสู่ระบบด้วย DGA" บนเว็บ = บัญชีทางรัฐ) — dashboard **ไม่มีระบบสมาชิกของตัวเอง**
- รหัสผ่านถูกส่งต่อไปที่ `connect.egov.go.th` / `landsmaps.dol.go.th` เท่านั้น ผ่าน `landsmaps/login.py` ตัวเดียวกับ `python get_token.py`
- ☑ **จำบัญชีไว้ในเครื่อง** (ค่าเริ่มต้น) → เขียนลง `Access_Key.txt` + `.env` แล้ว `fetch_parcels.py` จะล็อกอินใหม่ให้เองทุกครั้งที่รัน
- ☐ ไม่ติ๊ก → เก็บแค่ token (ใช้ได้ 24 ชม.) และ**ลบรหัสผ่านที่เคยจำไว้ออก**
- ปุ่ม **↻ ต่ออายุ** = ล็อกอินใหม่ด้วยบัญชีที่จำไว้ · **ออกจากระบบ** = ลบ token · **ออกจากระบบ + ลืมบัญชี** = ลบ token + รหัสผ่านใน `Access_Key.txt` และ `.env`
- บัญชีที่เปิด OTP (ยืนยันสองชั้น) ล็อกอินอัตโนมัติไม่ได้
- ถ้าตั้ง env `LANDSMAPS_TOKEN` ไว้ ค่านั้นถูกใช้ก่อนไฟล์เสมอ (dashboard ลบให้ไม่ได้ — หน้าบัญชีจะเตือน)

### 1) 📥 ข้อมูลขอบเขตนำเข้า — ลากไฟล์มาวาง + ดูสถานะการดึง

- ลากไฟล์ลงกรอบ (หรือคลิกเลือกไฟล์) → server เก็บลง `areas/` แล้ว**ลองอ่านขอบเขตด้วยตัวอ่านเดียวกับ `fetch_parcels.py`** ทันที (✓ อ่านได้ / ⚠ อ่านไม่ได้ + สาเหตุ) แล้วโชว์บนแผนที่

| ไฟล์ | วิธีส่ง |
|---|---|
| `.kmz` `.kml` `.geojson` `.json` `.gpkg` | ลากมาได้เลย หลายไฟล์พร้อมกันได้ |
| shapefile | เลือก `.shp` `.shx` `.dbf` (`.prj` `.cpg`) **พร้อมกัน** — ขาด `.shx`/`.dbf` จะถูกปฏิเสธ |
| File Geodatabase `.gdb` | browser ส่งโฟลเดอร์ไม่ได้ → คลิกขวาโฟลเดอร์ > *Send to > Compressed (zip)* แล้วลาก `.zip` มา |
| `.zip` | แตกให้อัตโนมัติ — เก็บเฉพาะ `.gdb` และไฟล์ขอบเขต (ไฟล์อื่นข้าม) |

- ชื่อซ้ำกับของเดิม → ถามก่อน ถ้าแทนที่ ไฟล์เดิมถูกย้ายไป `areas/.replaced/<วันเวลา>_<ชื่อ>` (ไม่ลบทิ้ง กู้คืนได้)
- **ลบ input**: กด 🗑 ท้ายแถว หรือติ๊กหลายไฟล์แล้วกด **🗑 ลบที่เลือก** → ย้ายไป `areas/.deleted/<วันเวลา>/` (กู้คืนได้ด้วยการย้ายกลับ)
  - shapefile ย้ายทั้งชุด (.shx .dbf .prj ...), `.gdb` ย้ายทั้งโฟลเดอร์
  - ถ้ามี job ที่ยังรันอยู่ใช้ไฟล์นั้น (หรือ parcel ที่ไม่ได้เลือก area = ใช้ทุกไฟล์) จะไม่ยอมลบ
  - ถ้าไฟล์ถูกเปิดค้างใน ArcGIS/QGIS ย้ายไม่ได้ → ยกเลิกทั้งชุด ไม่มีการย้ายครึ่ง ๆ กลาง ๆ
- จำกัด 500 MB ต่อครั้ง (zip แตกแล้วไม่เกิน 2 GB)
- ปุ่ม 📂 เปิดโฟลเดอร์ `areas/` ใน Explorer

#### สถานะการดึงของแต่ละ input (คอลัมน์ **สถานะการดึง** + **ล่าสุด**)

เห็นทุกครั้งที่เปิดหน้านี้ — **ไม่ว่าจะรันจาก dashboard, ดับเบิลคลิก `.cmd` หรือ Windows Task Scheduler** เพราะ `fetch_parcels.py` เขียนสถานะลง `cache/status/<ชื่อพื้นที่>.json` เอง (หน้าเว็บ refresh ให้ทุก 15 วินาทีขณะเปิดหน้านี้อยู่)

| ป้าย | ความหมาย | ทำอะไรต่อ |
|---|---|---|
| ยังไม่เคยดึง | ไม่มีไฟล์สถานะและไม่มีผลใน `output/` | รัน |
| 🔄 กำลังดึง | process ยังรันอยู่ · แถบ = `รอบนี้ n/ทั้งหมดที่ต้องดึงรอบนี้` | รอ |
| ✅ ครบ | ทุกแปลงมีรายละเอียดแล้ว | — |
| ⛔ โควตาเต็ม | LandsMaps แจ้งเกินโควตา · แถบ = ได้แล้ว/ทั้งหมด + ค้างกี่แปลง | รันใหม่หลังโควตารีเซ็ต — ทำต่อจาก cache |
| ⏸ ยังค้าง | จบรอบแต่ยังมีแปลงไม่มีรายละเอียด (เช่น `--no-detail` หรือโควตาหมดตั้งแต่พื้นที่ก่อนหน้า) | รันใหม่ |
| ⚠ หยุดกลางทาง | ไฟล์สถานะบอกว่ารันอยู่ แต่ process ไม่อยู่แล้ว (ปิดหน้าต่าง / ไฟดับ / กด Cancel) | รันใหม่ — ทำต่อจาก cache |
| ✗ ผิดพลาด | พื้นที่นั้นพัง (ชี้เมาส์ดูสาเหตุ) | แก้ตามสาเหตุแล้วรันใหม่ |

- พื้นที่ที่ดึงไว้**ก่อน**มีระบบนี้ (ไม่มีไฟล์สถานะ) → นับจาก `output/<ชื่อ>/<ชื่อ>_parcel_*.shp` แทน (ฟิลด์ `Remark = ยังไม่ได้ดึงรายละเอียด`) — ชี้เมาส์จะบอกว่านับจาก shapefile
- รันด้วย `--name` → จับคู่ตามชื่อไฟล์ input ที่บันทึกไว้ในสถานะ (ใช้รอบล่าสุด)
- ไฟล์สถานะเป็น JSON เล็ก ๆ ลบทิ้งได้ไม่เสียอะไร (ไม่ใช่ cache รายละเอียด ไม่เสียโควตา)

#### รันอัตโนมัติด้วย Windows Task Scheduler

ใช้ `Schedule_fetch_parcel.cmd` (ไม่มี `pause` — task จบเองได้ ต่างจาก `Program_fetch_parcel.cmd`) · log ต่อท้ายที่ `cache/autorun.log`

| ช่องใน Task Scheduler (Action: Start a program) | ค่า |
|---|---|
| Program/script | `D:\ANISPOWER\LandParcels\Schedule_fetch_parcel.cmd` |
| Add arguments | เว้นว่าง = ทุกไฟล์ใน `areas/` · หรือเลือกเฉพาะ เช่น `areas\bnn.gdb areas\cbd.kmz` · ใส่ตัวเลือกอื่นได้ เช่น `--refetch notfound` |
| Start in | `D:\ANISPOWER\LandParcels` |

- ต้อง **จำบัญชี** ไว้ในหน้า 🔐 บัญชี ก่อน (ตอนรันอัตโนมัติไม่มีคนกรอกรหัส)
- แนะนำติ๊ก *Run task as soon as possible after a scheduled start is missed* และ *If the task is already running: Do not start a new instance*
- ไม่รู้เวลารีเซ็ตโควตาแน่ชัด → ตั้งได้หลายเวลา (เช่น 00:15 และ 06:00) รอบที่โควตายังไม่รีเซ็ตจะหยุดเองโดยไม่เสียหาย

### 2) 🗂 ตั้งค่าผลลัพธ์ — เลือกฟิลด์เสริม + ตั้งชื่อ (ครั้งแรก)
- แท็บย่อย **parcel** / **cityplanning** · ฟิลด์แบ่งเป็นกลุ่ม หัวกลุ่มบอกจำนวนที่เลือก (`2/9`)
- ติ๊กฟิลด์ที่อยากเพิ่ม → แก้ชื่อในช่องขวา (≤10 ตัวอักษร) → **💾 Save user_schema.json** = เขียนลง `schema/user_schema.json` ให้เลย (ไม่ต้องดาวน์โหลด/ย้ายไฟล์)
- **↻ Reload** = โหลดค่าจากไฟล์กลับมา ทิ้งที่แก้แต่ยังไม่ save
- Fixed fields (14 ของ parcel, 12 ของ city) ถูกล็อก เปลี่ยนไม่ได้
- **ตรวจชื่อให้ทันทีระหว่างพิมพ์** — ชื่อที่ใช้ไม่ได้ขึ้นกรอบแดง + รายการ ⚠ ใต้ปุ่ม (ชี้เมาส์ที่ช่องเพื่อดูสาเหตุ) และ **กด Save ไม่ได้จนกว่าจะแก้ครบ**:

  | ปัญหา | ตัวอย่าง |
  |---|---|
  | ชื่อซ้ำกันเอง (ไม่สนตัวพิมพ์เล็ก/ใหญ่ เพราะ DBF ถือว่าเป็นชื่อเดียวกัน) | `Lat` กับ `lat` |
  | ชนฟิลด์มาตรฐาน | ตั้งชื่อฟิลด์เสริมว่า `Rai` / `rawang` |
  | ติ๊กแล้วแต่ช่องชื่อว่าง | — |
  | เกิน 10 ตัวอักษร | `ParcelNumber` |

  ถ้าอีกแท็บย่อยมีปัญหา กด Save จะพาไปแท็บนั้นและโฟกัสช่องแรกที่ผิดให้ · server ตรวจซ้ำอีกชั้นก่อนเขียนไฟล์
- ✅ `fetch_*.py` **อ่าน** `user_schema.json` แล้ว — Save แล้วดึงใหม่ output จะเป็นฟิลด์ตามที่ตั้ง · ไม่เคย Save = คง 14/12 ฟิลด์เดิม
- รายละเอียดฟิลด์ + รูปแบบไฟล์ → [schema.md](schema.md)

### 3) 🏞 ดึงรูปแปลงดิน
- ติ๊ก area (ไม่ติ๊ก = ทุกไฟล์) · ตั้ง `--name`, `--layer`, `--refetch`, `--no-detail`
- ถ้ายังไม่ล็อกอิน จะมีแถบเตือนเรื่องโควตาพร้อมลิงก์ไปหน้าบัญชี
- **▶ Start** → เด้งไปหน้า Monitor

### 4) 🏙 ดึงผังเมือง
- ค้นจังหวัด → **+ เพิ่ม** (หลายจังหวัดได้) · `--area` ตัดเฉพาะกรอบ
- `--token` คือ **ArcGIS token ของ LandsMaps** (คนละตัวกับบัญชี DGA) — ช่องนี้ซ่อนค่าไว้ และ cmd ที่โชว์บนหน้าเว็บจะเป็น `--token ***`

### 5) 📊 Monitor
- live log + progress bar (parse `[N/M]` หรือ `%`) + แผนที่ area ของ job
- **⏹ Cancel** ส่ง terminate ให้ subprocess · เสร็จแล้วกด **📤 ดูผลลัพธ์**

### 6) 📤 ผลลัพธ์ — ดาวน์โหลด/เปิดผล

- จัดกลุ่มตามโฟลเดอร์ใน `output/`
- **⬇ zip** ที่ไฟล์ `.shp` = รวม `.shp .shx .dbf .prj .cpg .shp.xml` เป็น zip เดียว (ไม่รวม lock file ของ ArcGIS/QGIS)
- `.gpkg` / `.geojson` ดาวน์โหลดตรง ๆ · **⬇ zip ทั้งโฟลเดอร์** ได้ทั้งชุด
- **📂** เปิดไฟล์/โฟลเดอร์ใน Explorer (เลือกไฟล์ไว้ให้) → ลากเข้า QGIS / ArcGIS Pro ได้เลย

### 7) 📖 คู่มือ — อ่าน docs ในหน้าเว็บ

- สารบัญด้านซ้าย = `README.md` + ทุกไฟล์ใน `docs/` (วางไฟล์ `.md` ใหม่ใน `docs/` แล้วกด refresh ก็โผล่เอง)
- ลิงก์ในคู่มือกดข้ามไปอีกหน้า/หัวข้อได้เลย · ลิงก์ภายนอกเปิดแท็บใหม่ · ลิงก์ไปไฟล์ในเครื่อง (เช่น `.env.example`) แสดงเป็นเส้นประ ชี้เมาส์ดู path
- ลิงก์ตรง: `#docs/<ชื่อไฟล์>` หรือ `#docs/<ชื่อไฟล์>/<หัวข้อ>` เช่น `http://localhost:8765/#docs/parcel` — refresh แล้วอยู่หน้าเดิม
- ตัวแสดง markdown (marked + DOMPurify) โหลดจาก CDN ตอนเปิดครั้งแรก — ไม่มี internet จะแสดงเป็นข้อความดิบแทน

### ธีม ☀️ / 🖥️ / 🌙
ปุ่มขวาบน: สว่าง · ตามระบบ (ค่าเริ่มต้น) · มืด — จำค่าไว้ใน browser (`localStorage` key `lp-theme`) แผนที่ก็ปรับเป็นโทนมืดตาม

---

## โครงสร้าง

```
dashboard/
├── server.py        FastAPI: schema, areas list/preview/delete, run, jobs, SSE + middleware กันเว็บอื่น
├── auth.py          /api/auth/*  บัญชี LandsMaps (เรียก landsmaps.login / keystore)
├── files.py         /api/areas/upload, ลบ areas (ย้ายไป .deleted/), /api/output/download, /api/reveal
├── docs.py          /api/docs  ส่ง README.md + docs/*.md ให้หน้า 📖 คู่มือ (อ่านอย่างเดียว)
├── status.py      /api/status/areas  สถานะการดึงของแต่ละ input (อ่านอย่างเดียว)
├── index.html       markup อย่างเดียว
├── static/
│   ├── app.css      design tokens + theme สว่าง/มืด
│   ├── app.js       input/schema/run/monitor/output
│   ├── account.js   theme switch + หน้าบัญชี + ป้ายสถานะ
│   └── docs.js      หน้า 📖 คู่มือ (render markdown + แปลงลิงก์ข้ามหน้า)

docs/dashboard.md    (ไฟล์นี้ — คู่มือรวมอยู่ใน docs/)
```

`fetch_parcels.py` / `fetch_cityplanning.py` ไม่ถูกแก้ — dashboard spawn เป็น subprocess เท่านั้น

---

## API endpoints

| Method | Path | ใช้ทำ |
|---|---|---|
| GET | `/` | serve `index.html` |
| GET | `/api/auth/status` | สถานะบัญชี: `logged_in`, `user` (mask), `expires_at`, `remaining_sec`, `remembered`, `quota` |
| POST | `/api/auth/login` | `{user, password, remember}` → ล็อกอิน DGA · body ว่าง = ต่ออายุด้วยบัญชีที่จำไว้ |
| POST | `/api/auth/logout` | `{forget}` → ลบ token (+ ลืมบัญชีถ้า `forget: true`) |
| GET | `/api/areas` | list `areas/` |
| POST | `/api/areas/delete` | `{names: [...]}` → ย้ายไป `areas/.deleted/<เวลา>/` (409 ถ้า job ยังใช้อยู่ / ไฟล์ถูกล็อก) |
| POST | `/api/areas/upload` | multipart `files[]`, `overwrite` → เก็บลง `areas/` + ตรวจอ่านได้ (409 ถ้าชื่อซ้ำ) |
| GET | `/api/areas/{name}/geojson` | ขอบเขต (EPSG:4326) สำหรับ Leaflet — อ่านด้วย `landsmaps.area.read_polygons` |
| GET | `/api/status/areas` | สถานะการดึงรายไฟล์ใน `areas/` — อ่าน `cache/status/*.json` (ไม่มี → นับจาก shp ใน `output/`) อ่านอย่างเดียว |
| GET | `/api/catalog/{parcel\|cityplanning}` | `schema/catalog_*.json` |
| GET/POST | `/api/user-schema` | อ่าน/เขียน `schema/user_schema.json` — 400 `{message, problems[]}` ถ้าชื่อว่าง/เกิน 10/ซ้ำ/ชนฟิลด์มาตรฐาน |
| GET | `/api/docs` | รายการคู่มือ `[{name, title}]` (`index` = README.md) |
| GET | `/api/docs/{name}` | markdown ดิบของคู่มือ (เฉพาะ README.md + `docs/*.md`) |
| GET | `/api/provinces` | 77 จังหวัด |
| GET | `/api/output` | list shp/gpkg/geojson ใน `output/` (มี `dir` สำหรับจัดกลุ่ม) |
| GET | `/api/output/download?path=` | `.shp` → zip ทั้งชุด · โฟลเดอร์ → zip · อื่น ๆ → ไฟล์ตรง |
| POST | `/api/reveal` | `{root: areas\|output, path}` → เปิด Explorer (Windows) |
| POST | `/api/run` | spawn `fetch_parcels.py` / `fetch_cityplanning.py` |
| GET | `/api/jobs`, `/api/jobs/{id}` | job list / รายละเอียด + log 200 บรรทัดล่าสุด |
| GET | `/api/jobs/{id}/stream` | **SSE** live log + progress |
| POST | `/api/jobs/{id}/cancel` | terminate subprocess |

---

## ความปลอดภัย

- **Host check** — ตอบเฉพาะ `Host` เป็น `127.0.0.1` / `localhost` / `[::1]` (กัน DNS rebinding)
- **Origin check** — POST ที่ `Origin` ไม่ตรงกับ host ของ dashboard ถูกปฏิเสธ 403 (กันเว็บอื่นที่เปิดใน browser เดียวกันสั่งล็อกอิน/อัปโหลด/รันแทน)
- รหัสผ่านและ token **ไม่ถูกส่งกลับหน้าเว็บและไม่ลง log** — หน้าเว็บเห็นแค่ชื่อบัญชีแบบ mask (`123********45`) กับวันหมดอายุ
- `Access_Key.txt` / `.env` ถูกจำกัดสิทธิ์ให้เจ้าของอ่านได้คนเดียว (ผ่าน `landsmaps.keystore` เหมือนเดิม)
- Upload: ตัด path ออกจากชื่อไฟล์, ปฏิเสธชื่อต้องห้ามของ Windows, กัน zip-slip (`../`), จำกัดขนาด
- Download / reveal: จำกัด path ให้อยู่ใต้ `output/` หรือ `areas/` เท่านั้น
- Delete: รับเฉพาะชื่อไฟล์ขอบเขตชั้นบนสุดของ `areas/` (ไม่มี `../` / path ซ้อน) · ไม่ลบจริง ย้ายไป `areas/.deleted/` · ทุกไฟล์ต้องผ่านก่อนถึงเริ่มย้าย (ชื่อผิดตัวเดียว = ไม่ลบเลย)

---

## ข้อควรรู้

- ✅ **CLAUDE.md compliant** — Claude ไม่กด Start / เข้าสู่ระบบ / อัปโหลดลง `areas/` จริงแทนผู้ใช้
- ⚠️ `areas/.replaced/` และ `areas/.deleted/` **ไม่ถูกล้างอัตโนมัติ** — ถ้ารกหรือกินพื้นที่ ลบเองใน Explorer (โฟลเดอร์ขึ้นต้นด้วยจุด อาจต้องเปิด *Hidden items*)
- ⚠️ Schema Editor แบบแยก (`schema/open_editor.bat`) ใช้ port 8765 เหมือน dashboard — เปิดพร้อมกันไม่ได้ (ใช้หน้า 🗂 ตั้งค่าผลลัพธ์ ใน dashboard แทนได้)
- ⚠️ Job registry เก็บใน memory — ปิด server แล้วประวัติ job หาย (log/output ยังอยู่ใน `output/`)
- ⚠️ Progress parsing ใช้ regex (`[N/M]`, `N/M parcels`, `X%`) — ถ้า script ไม่ print รูปแบบนี้จะเป็น progress bar แบบวิ่งไม่รู้จบ
- ⚠️ Map ใช้ OSM tiles + Leaflet CDN — ต้องมี internet

---

## Test

```powershell
pip install httpx          # TestClient ของ FastAPI ต้องใช้
python -m pytest tests/test_dashboard.py -v
```

offline ทั้งหมด — login ถูก mock ไม่ยิง LandsMaps จริง, ไฟล์อยู่ใน `tmp_path`

---

## Troubleshooting

| อาการ | สาเหตุ / แก้ |
|---|---|
| `ModuleNotFoundError: fastapi` | `pip install fastapi uvicorn python-multipart` |
| อัปโหลดแล้ว error `Form data requires "python-multipart"` | `pip install python-multipart` |
| `403 dashboard เปิดได้จาก localhost เท่านั้น` | เปิดผ่าน `http://localhost:8765` หรือ `http://127.0.0.1:8765` (ไม่ใช่ชื่อเครื่อง/IP) |
| `ล็อกอินไม่สำเร็จ: ...` | ข้อความมาจาก DGA ตรง ๆ — เช็ครหัสผ่าน / บัญชีเปิด OTP อยู่หรือไม่ / ลองล็อกอินบนเว็บ LandsMaps ก่อน |
| ลากโฟลเดอร์ `.gdb` แล้วขึ้นเตือน | zip โฟลเดอร์ก่อนแล้วลาก `.zip` |
| อัปโหลดแล้ว ⚠ อ่านขอบเขตไม่ได้ | ไฟล์ยังถูกเก็บไว้ — ดูข้อความ (เช่น ไม่มี polygon, ไม่มี .prj) แก้ไฟล์แล้วอัปโหลดทับ |
| กด 🗑 แล้วขึ้น `มี job ที่ยังรันอยู่ใช้ไฟล์นี้` | รอ job จบ หรือกด ⏹ Cancel ที่หน้า Monitor ก่อน (parcel ที่ไม่ได้เลือก area ใช้ทุกไฟล์) |
| กด 🗑 แล้วขึ้น `ย้าย ... ไม่ได้ — อาจเปิดค้างอยู่ใน ArcGIS/QGIS` | ปิด layer/โปรเจกต์ที่เปิดไฟล์นั้นอยู่แล้วลองใหม่ — ไม่มีไฟล์ไหนถูกย้ายไปครึ่งชุด |
| Save schema ไม่ได้ ขึ้นกรอบแดง | ชื่อซ้ำ / ชนฟิลด์มาตรฐาน / ว่าง / เกิน 10 — ชี้เมาส์ที่ช่องดูสาเหตุ หรืออ่านรายการ ⚠ ใต้ปุ่ม |
| 📖 คู่มือ ขึ้นข้อความดิบ | ไม่มี internet (โหลด CDN ไม่ได้) — เนื้อหาครบ แค่ไม่จัดรูปแบบ |
| ลบผิดไฟล์ | เปิด `areas/.deleted/<วันเวลา>/` แล้วย้ายไฟล์กลับมาไว้ใน `areas/` → กด ↻ |
| 📂 ไม่เปิด Explorer | ใช้ได้เฉพาะ Windows |
| `ไม่พบ catalog_parcel.json` | ต้องมี `schema/catalog_parcel.json` + `schema/catalog_cityplanning.json` |
| Map ไม่ขึ้น | ตรวจ internet (CDN Leaflet + OSM tiles) |
| SSE ไม่อัปเดต | บาง corp proxy บล็อก `text/event-stream` |
