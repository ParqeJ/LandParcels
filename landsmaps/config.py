"""ค่าคงที่ของ LandsMaps และโฟลเดอร์ของโปรเจกต์"""

from pathlib import Path

# ─────────────────────────── โฟลเดอร์ ───────────────────────────
ROOT = Path(__file__).resolve().parent.parent
AREAS_DIR = ROOT / "areas"        # วางไฟล์ขอบเขตพื้นที่ที่นี่
OUTPUT_DIR = ROOT / "output"
CACHE_DIR = ROOT / "cache"

# access_token ของบัญชี LandsMaps (อายุ 24 ชม.) ไม่มี -> ใช้แบบไม่ล็อกอิน (โควตาน้อยกว่า)
TOKEN_FILE = ROOT / "Access_Key.txt"
TOKEN_ENV = "LANDSMAPS_TOKEN"

# ─────────────────────────── LandsMaps ───────────────────────────
API = "https://landsmaps.dol.go.th/apiService"
WFS = "https://landsmaps.dol.go.th/geoserver/LANDSMAPS/ows"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://landsmaps.dol.go.th/"}

SLEEP_SEC = 1.0             # หน่วงระหว่างเรียก API ไม่ให้โหลดเซิร์ฟเวอร์กรมที่ดิน
TIMEOUT = 120
MAX_COUNT = 60_000          # จำนวนแปลงสูงสุดต่อ 1 คำขอ WFS
RETRY_WAITS = (5, 15, 45)
LOG_EVERY = 100
# โควตาค้นรายละเอียด/วัน ไม่ใช่ตัวเลขตายตัว (เว็บแจ้ง 20 แต่ใช้จริงได้มากกว่า) ใช้แค่แสดงผล
FREE_QUOTA = "ประมาณ 20-40"       # ไม่ล็อกอิน
LOGIN_QUOTA = "ประมาณ 200-400"    # ใช้ access token ของบัญชี

# ไฟล์ขอบเขตที่อ่านได้ (และโฟลเดอร์ .gdb)
AREA_SUFFIXES = (".kmz", ".kml", ".shp", ".gpkg", ".geojson", ".json")

# ลำดับ attribute ของ Shapefile ผลลัพธ์ (ชื่อ field ยาวได้ไม่เกิน 10 ตัวอักษร)
FIELDS = [
    "Owner_Name", "Surname", "Contact_No", "Type_land", "Rawang", "Group",
    "Plang", "Cert_No", "Rai", "Ngan", "Wa", "Status", "LLA_no", "Remark",
]
