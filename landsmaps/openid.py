"""เข้าสู่ระบบด้วย DGA (OpenID ของบัญชีทางรัฐ) แล้วคืน access token ของบัญชี LandsMaps

ทำตามลำดับเดียวกับปุ่ม "เข้าสู่ระบบด้วย DGA" ในเว็บ ดูรายละเอียดขั้นตอนที่ config.py

ความปลอดภัย: เดินตาม redirect เอง ยอมเฉพาะ https บนโฮสต์ใน ALLOWED_HOSTS
เพราะคำขอที่ส่งรหัสผ่านไปด้วยอาจถูก redirect ต่อ (307/308 ส่ง body ไปด้วย)
ข้อความ error บอกแค่ชื่อโฮสต์ ไม่ใส่ URL เต็ม เพราะ URL มี access_token อยู่ข้างใน
"""

import html
import re
from urllib.parse import urljoin, urlparse

import requests

from .config import (ACCOUNT_LOGIN_URL, ALLOWED_HOSTS, DGA_ERROR_CLASS, DGA_HIDDEN_FIELDS,
                     DGA_HOST, DGA_OTP_FIELD, DGA_PASSWORD_FIELD, DGA_SUBMIT, DGA_USER_FIELD, HEADERS,
                     JWT_URL, LANDSMAPS_HOST, LOGIN_OPENID_URL, MAX_REDIRECTS, TIMEOUT)

INPUT_TAG = re.compile(r"<input\b[^>]*>", re.I)
# (?<![\w-]) กัน data-name= / aria-id= ถูกอ่านเป็น name= / id=  (\x27 = quote เดี่ยว)
ATTR = re.compile(r"""(?<![\w-])(name|id|value)\s*=\s*("[^"]*"|\x27[^\x27]*\x27)""", re.I)
# หน้า /consent ของ DGA ไม่มีฟอร์ม แค่สั่งเบราว์เซอร์ไปต่อด้วย <meta http-equiv="refresh">
META_REFRESH = re.compile(r"""<meta\b[^>]*http-equiv\s*=\s*["']?refresh["']?[^>]*>""", re.I)
DATA_URL = re.compile(r"""data-url\s*=\s*("[^"]*"|\x27[^\x27]*\x27)""", re.I)
CONTENT_URL = re.compile(r"""content\s*=\s*["']?\s*\d*\s*;\s*url\s*=\s*([^"'>]+)""", re.I)
VERIFY_TOKEN = "__RequestVerificationToken"
UNKNOWN_HOST = "ไม่รู้จัก"


class OpenIDError(RuntimeError):
    """ล็อกอิน DGA ไม่สำเร็จ (บัญชีผิด บัญชีเปิด OTP หรือฟอร์มของ DGA เปลี่ยนไป)"""


def form_fields(page: str) -> dict[str, str]:
    """{ชื่อหรือ id ของ input: ค่า} ของทุก input ในหน้า (แปลง &amp; กลับเป็น & ให้แล้ว)"""
    out: dict[str, str] = {}
    for tag in INPUT_TAG.findall(page):
        attrs = {k.lower(): html.unescape(v[1:-1]) for k, v in ATTR.findall(tag)}
        key = attrs.get("name") or attrs.get("id")
        if key:
            out.setdefault(key, attrs.get("value", ""))
    return out


def error_message(page: str) -> str:
    """ข้อความ error ที่ DGA แสดงในหน้าล็อกอิน ไม่มี -> ค่าว่าง"""
    m = re.search(rf'class="[^"]*{re.escape(DGA_ERROR_CLASS)}[^"]*"[^>]*>(.*?)</div>',
                  page, re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", m.group(1)) if m else ""
    return " ".join(html.unescape(text).split())


def host_of(url: str) -> str:
    return urlparse(url).hostname or UNKNOWN_HOST


def on_host(url: str, host: str) -> bool:
    """URL นี้เป็น https และอยู่บนโฮสต์ที่ระบุจริงไหม (ไม่ใช่การเทียบแบบ substring)"""
    u = urlparse(url)
    return u.scheme == "https" and u.hostname == host


def meta_refresh(page: str) -> str | None:
    """ปลายทางของ <meta http-equiv="refresh"> ในหน้า (แปลง &amp; กลับแล้ว) ไม่มี -> None"""
    tag = META_REFRESH.search(page)
    if not tag:
        return None
    m = DATA_URL.search(tag.group(0))
    url = m.group(1)[1:-1] if m else (CONTENT_URL.search(tag.group(0)) or [None, None])[1]
    return html.unescape(url).strip() if url else None


def next_url(r: requests.Response) -> str | None:
    """ขั้นถัดไปของ flow: HTTP redirect หรือ meta refresh ไม่มี -> None (จบแล้ว)"""
    if r.is_redirect:
        return urljoin(r.url, r.headers.get("Location", ""))
    target = meta_refresh(r.text)
    return urljoin(r.url, target) if target else None


def follow(session: requests.Session, r: requests.Response) -> requests.Response:
    """เดินตาม redirect และ meta refresh เอง ยอมเฉพาะโฮสต์ที่อนุญาต ไม่งั้นรหัสผ่านอาจถูกส่งต่อไปที่อื่น"""
    for _ in range(MAX_REDIRECTS):
        target = next_url(r)
        if target is None:
            return r
        if not any(on_host(target, h) for h in ALLOWED_HOSTS):
            raise OpenIDError(f"ถูกส่งต่อไปโฮสต์ที่ไม่อนุญาต ({host_of(target)}) "
                              f"-> หยุดเพื่อไม่ให้บัญชีรั่ว")
        if r.is_redirect and r.status_code in (307, 308):   # ส่ง method และ body เดิมไปด้วย
            r = session.request(r.request.method, target, data=r.request.body,
                                timeout=TIMEOUT, allow_redirects=False)
        else:
            r = session.get(target, timeout=TIMEOUT, allow_redirects=False)
    raise OpenIDError("ถูกส่งต่อวนไม่จบ -> ขั้นตอนล็อกอินของ DGA เปลี่ยนไปแล้ว")


def json_body(r: requests.Response) -> dict:
    """แปลงคำตอบเป็น dict ไม่ใช่ JSON หรือรูปแบบผิด -> OpenIDError (ไม่เชื่อข้อมูลจากภายนอก)"""
    try:
        body = r.json()
    except ValueError as e:
        raise OpenIDError(f"{host_of(r.url)} ตอบกลับไม่ใช่ JSON (HTTP {r.status_code})") from e
    if not isinstance(body, dict):
        raise OpenIDError(f"{host_of(r.url)} ตอบกลับรูปแบบที่ไม่รู้จัก")
    return body


def first_result(body: dict, where: str) -> dict:
    """result[0] ที่เป็น dict ไม่ได้รูปนี้ -> OpenIDError"""
    result = body.get("result")
    if not isinstance(result, list) or not result or not isinstance(result[0], dict):
        raise OpenIDError(" ".join((body.get("message") or f"{where} ตอบกลับไม่มีข้อมูล").split()))
    return result[0]


def anon_token(session: requests.Session) -> str:
    """token สาธารณะของ LandsMaps ใช้เป็นใบเบิกทางและเป็นตัวผูกการล็อกอินครั้งนี้"""
    r = session.get(JWT_URL, timeout=TIMEOUT)
    r.raise_for_status()
    token = first_result(json_body(r), "LandsMaps").get("access_token")
    if not token:
        raise OpenIDError("LandsMaps ไม่ได้ส่ง token สาธารณะกลับมา")
    return token


def submit_dga_form(session: requests.Session, page_url: str, page: str,
                    user: str, password: str) -> requests.Response:
    """กรอกบัญชีลงฟอร์มของ DGA แล้วส่งกลับไปที่ URL เดิม (ฟอร์มใช้ action ว่าง)"""
    fields = form_fields(page)
    missing = [f for f in (DGA_USER_FIELD, DGA_PASSWORD_FIELD, VERIFY_TOKEN) if f not in fields]
    if missing:
        raise OpenIDError(f"หน้าล็อกอินของ DGA ไม่มีช่อง {', '.join(missing)} "
                          f"(ฟอร์มเปลี่ยนไปแล้ว -> แก้ DGA_* ใน config.py)")
    payload = {**{k: fields.get(k, "") for k in DGA_HIDDEN_FIELDS},
               DGA_USER_FIELD: user, DGA_PASSWORD_FIELD: password, **DGA_SUBMIT}
    return session.post(page_url, data=payload, timeout=TIMEOUT, allow_redirects=False)


def account_token(session: requests.Session, anon: str) -> str:
    """แลก token สาธารณะที่ผูกกับการล็อกอินแล้ว -> access token ของบัญชี"""
    r = session.post(LOGIN_OPENID_URL, data="", timeout=TIMEOUT,
                     headers={"Authorization": f"Bearer {anon}",
                              "Content-Type": "application/json; charset=utf-8"})
    r.raise_for_status()
    token = first_result(json_body(r), "LandsMaps").get("access_token")
    if not token:
        raise OpenIDError("ล็อกอิน DGA ผ่านแต่ LandsMaps ไม่ได้ส่ง access_token กลับมา")
    return token


def login_openid(user: str, password: str) -> str:
    """ล็อกอิน LandsMaps ผ่าน DGA คืน access token ของบัญชี (อายุ 24 ชม.)"""
    s = requests.Session()                      # ใช้ session เดียวตลอด cookie ต้องต่อเนื่องทุกขั้น
    s.headers.update(HEADERS)
    anon = anon_token(s)

    r = follow(s, s.get(ACCOUNT_LOGIN_URL, params={"access_token": anon},
                        timeout=TIMEOUT, allow_redirects=False))
    r.raise_for_status()
    if not on_host(r.url, DGA_HOST):
        raise OpenIDError(f"LandsMaps ไม่ได้ส่งต่อไปหน้าล็อกอินของ DGA (ไปที่ {host_of(r.url)})")

    r = follow(s, submit_dga_form(s, r.url, r.text, user, password))
    r.raise_for_status()
    if on_host(r.url, DGA_HOST):                # ยังอยู่ที่ DGA = ไม่ผ่าน
        if form_fields(r.text).get(DGA_OTP_FIELD):
            raise OpenIDError("บัญชี DGA นี้เปิดยืนยัน 2 ขั้น (OTP) -> ปิด OTP "
                              "หรือล็อกอินในเว็บแล้วคัดลอก token ใส่ Access_Key.txt เอง")
        raise OpenIDError(error_message(r.text) or "บัญชีหรือรหัสผ่าน DGA ไม่ถูกต้อง")
    if not on_host(r.url, LANDSMAPS_HOST):      # ไม่ใช่ปลายทางที่ควรเป็น -> ไม่เรียก API ต่อ
        raise OpenIDError(f"หลังล็อกอินไปจบที่โฮสต์ที่ไม่คาดคิด ({host_of(r.url)})")

    return account_token(s, anon)
