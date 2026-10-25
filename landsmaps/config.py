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
ENV_FILE = ROOT / ".env"        # บัญชีสำหรับล็อกอินอัตโนมัติ (ดู .env.example)

# ─────────────────────────── LandsMaps ───────────────────────────
API = "https://landsmaps.dol.go.th/apiService"
WFS = "https://landsmaps.dol.go.th/geoserver/LANDSMAPS/ows"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://landsmaps.dol.go.th/"}
JWT_URL = f"{API}/JWT/GetJWTAccessToken"    # token สาธารณะ ไม่ต้องล็อกอิน
# endpoint ล็อกอิน แยกตามชนิดบัญชี (key = ชื่อ field ที่ต้องส่งคู่กับ user_password)
LOGIN_URLS = {
    "mail": f"{API}/LandsMaps/Login",
    "personal_id": f"{API}/LandsMaps/LoginDepartment",
    "user_name": f"{API}/LandsMaps/LoginLandofficeAD",
}

# เข้าสู่ระบบด้วย DGA (OpenID ของบัญชีทางรัฐ) — ลำดับเดียวกับปุ่มในเว็บ (Script/master/master.js: btnopenid)
#   1. ขอ token สาธารณะ (JWT_URL)
#   2. GET ACCOUNT_LOGIN_URL?access_token=<token สาธารณะ> -> ถูก redirect ไปหน้าล็อกอินของ DGA
#   3. POST ฟอร์มหน้านั้นกลับไปที่ URL เดิม -> DGA ส่งกลับมาที่ callback ของ LandsMaps (แลก code ฝั่งเซิร์ฟเวอร์)
#   4. POST LOGIN_OPENID_URL ด้วย token สาธารณะเดิม -> ได้ access_token ของบัญชี
ACCOUNT_LOGIN_URL = "https://landsmaps.dol.go.th/Account/Login"
LOGIN_OPENID_URL = f"{API}/LandsMaps/LoginOpenID"
DGA_HOST = "connect.egov.go.th"             # ยังอยู่โฮสต์นี้หลัง POST = ล็อกอินไม่ผ่าน
LANDSMAPS_HOST = "landsmaps.dol.go.th"      # ปลายทางที่ถือว่าล็อกอินผ่าน
# เดินตาม redirect เฉพาะ https บน 2 โฮสต์นี้ กันรหัสผ่านถูกส่งต่อไปที่อื่น
ALLOWED_HOSTS = (DGA_HOST, LANDSMAPS_HOST)
MAX_REDIRECTS = 10
DGA_USER_FIELD = "UserName"                 # ช่อง "บัญชีผู้ใช้งาน / เลขประจำตัวประชาชน / อีเมล"
DGA_PASSWORD_FIELD = "MaskedInput"          # ช่องรหัสผ่าน (ส่งเป็น plaintext ตามที่เว็บทำ)
# hidden field ของฟอร์ม DGA ที่ต้องคัดลอกค่าเดิมส่งกลับไปด้วย
DGA_HIDDEN_FIELDS = ("ReturnUrl", "AppClientId", "AppName", "OrgName", "Ott",
                     "__RequestVerificationToken")
# ปุ่ม "เข้าสู่ระบบ" มี name="button" value="login" — ไม่ส่งไปด้วย DGA จะถือว่ากด "ยกเลิก"
DGA_SUBMIT = {"button": "login"}
DGA_OTP_FIELD = "hdfTwoFactorOtt"          # มีค่า = DGA ขอ OTP (บัญชีเปิด 2FA)
DGA_ERROR_CLASS = "login-message"           # div ที่ DGA ใส่ข้อความ error ของการล็อกอิน

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
