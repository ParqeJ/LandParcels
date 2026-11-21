# LandParcels Dashboard

Local web UI รวมทุกอย่างที่ใช้ทำงานกับ LandsMaps ในหน้าเดียว:
input (areas) · schema editor · run parcel · run cityplanning · monitor + live log · map · output browser

---

## วิธีเปิด

### ดับเบิลคลิก launcher
```
D:\ANISPOWER\LandParcels\open_dashboard.bat
```

Launcher จะ:
1. เช็ค `fastapi`, `uvicorn` — ติดตั้งให้ถ้ายังไม่มี (`pip install fastapi uvicorn`)
2. เปิด `http://localhost:8765` ใน browser
3. รัน uvicorn server (ปิดด้วย Ctrl+C)

### หรือรันเองจาก terminal
```powershell
cd D:\ANISPOWER\LandParcels
pip install fastapi uvicorn
python -m uvicorn dashboard.server:app --host 127.0.0.1 --port 8765
```

---

## โครงสร้าง

```
dashboard/
├── server.py        FastAPI backend (ไม่แตะ Python fetch_* เดิม, spawn subprocess เท่านั้น)
├── index.html       Single-page UI (Leaflet, SSE)
└── README.md        (ไฟล์นี้)
```

---

## API endpoints

| Method | Path | ใช้ทำ |
|---|---|---|
| GET | `/` | serve `index.html` |
| GET | `/api/catalog/{parcel\|cityplanning}` | `schema/catalog_*.json` |
| GET | `/api/user-schema` | อ่าน `schema/user_schema.json` (`_missing:true` ถ้ายังไม่มี) |
| POST | `/api/user-schema` | เขียน `schema/user_schema.json` (ตรวจ ≤10 ตัวอักษร) |
| GET | `/api/areas` | list `areas/` (KMZ/KML/GeoJSON/SHP/GDB) |
| GET | `/api/areas/{name}/geojson` | convert → GeoJSON (EPSG:4326) สำหรับ Leaflet |
| GET | `/api/provinces` | 77 จังหวัด จาก `landsmaps/cityplanning/provinces.py` |
| GET | `/api/output` | list shapefile/gpkg ใน `output/` |
| POST | `/api/run` | spawn `fetch_parcels.py` หรือ `fetch_cityplanning.py` |
| GET | `/api/jobs` | list job ทั้งหมด (in-memory) |
| GET | `/api/jobs/{id}` | รายละเอียด job + log 200 บรรทัดล่าสุด |
| GET | `/api/jobs/{id}/stream` | **SSE** live log + progress |
| POST | `/api/jobs/{id}/cancel` | ส่ง `terminate()` ให้ subprocess |

---

## โฟลว์ใช้งาน

### 1) Schema setup (ครั้งแรก)
- เมนู **🗂 Schema** → ติ๊กฟิลด์ที่อยากเพิ่ม, ตั้งชื่อ custom (≤10 ตัวอักษร)
- กด **💾 Save user_schema.json** → เขียน `schema/user_schema.json`
- Fixed fields (14 ของ parcel, 12 ของ city) ถูกล็อก เปลี่ยนไม่ได้

### 2) ตรวจ input area
- เมนู **📥 Input** → คลิกไฟล์ใน `areas/` → ดูบน map

### 3) Run parcel
- เมนู **🏞 Run · Parcel** → ติ๊ก area ที่ต้องการ (ไม่ติ๊ก = ทุกไฟล์)
- ตั้ง `--name`, `--layer`, `--refetch`, `--no-detail` ตามสะดวก
- กด **▶ Start** → เด้งไปหน้า **Monitor** อัตโนมัติ

### 4) Run cityplanning
- เมนู **🏙 Run · Cityplanning** → ค้นจังหวัด, กด **+ เพิ่ม** (เพิ่มได้หลายจังหวัด)
- ถ้าต้องการตัดเฉพาะกรอบ: เลือก `--area` จาก dropdown
- กด **▶ Start**

### 5) Monitor
- live log พร้อม progress bar (parse `[N/M]` หรือ `%` จาก stdout)
- map แสดง area ที่กำลังทำ (ถ้า job ผูกกับ area)
- ปุ่ม **⏹ Cancel** ส่ง SIGTERM ให้ subprocess

---

## รูปแบบ `user_schema.json` ที่ dashboard เขียน

```json
{
  "_generated_by": "dashboard",
  "_generated_at": "2026-11-22T00:50:12Z",
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

- date format: ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`)
- `source` = path ใน catalog (`info.*`, `props.*`, `virtual.*`)
- `name` = ชื่อ column ใน shapefile (DBF จำกัด 10 ตัวอักษร — backend reject ถ้ายาวเกิน)
- **fixed_fields ไม่ใส่** — pipeline ใช้ชื่อเดิมเสมอ

---

## ข้อควรรู้

- ✅ **ไม่แก้ `fetch_parcels.py` / `fetch_cityplanning.py` เดิม** — dashboard spawn subprocess เท่านั้น
- ✅ **CLAUDE.md compliant** — Claude ไม่กด Start ให้เอง, user กดเท่านั้น
- ⚠️ Job registry เก็บใน memory — ปิด server แล้วประวัติหาย (log/output ยังอยู่ใน `output/`)
- ⚠️ Progress parsing ใช้ regex (`[N/M]`, `N/M parcels`, `X%`) — ถ้า fetch script ไม่ print รูปแบบนี้ จะแสดง progress bar แบบ indeterminate
- ⚠️ Map ใช้ OSM tiles + Leaflet CDN — ต้องมี internet (ครั้งแรก); สามารถเปลี่ยนไปใช้ tile ภายในได้ในอนาคต

---

## Troubleshooting

| อาการ | สาเหตุ / แก้ |
|---|---|
| `ModuleNotFoundError: fastapi` | รัน `pip install fastapi uvicorn` |
| `ไม่พบ catalog_parcel.json` | ต้องมี `schema/catalog_parcel.json` + `schema/catalog_cityplanning.json` |
| Map ไม่ขึ้น | ตรวจ internet (CDN Leaflet + OSM tiles) |
| SSE ไม่อัปเดต | ตรวจว่า browser ไม่บล็อก `text/event-stream` (บาง corp proxy block) |
| อ่าน `.gdb` ไม่ได้ | ต้องมี `pyogrio` หรือ `fiona` driver ของ OpenFileGDB — ปกติ geopandas ล่าสุดมีให้แล้ว |
