import os

import pytest
import requests

from landsmaps import login as lg


def test_read_env_skips_comments_and_strips_quotes(tmp_path):
    f = tmp_path / ".env"
    f.write_text('# comment\nLANDSMAPS_DGA_ID="123"\n\nLANDSMAPS_PASSWORD = \'pw\'\nbroken\n',
                 encoding="utf-8")
    assert lg.read_env(f) == {"LANDSMAPS_DGA_ID": "123", "LANDSMAPS_PASSWORD": "pw"}


def test_read_env_missing_file(tmp_path):
    assert lg.read_env(tmp_path / "nope") == {}


def test_read_env_strips_trailing_comment(tmp_path):
    f = tmp_path / ".env"
    f.write_text("LANDSMAPS_DGA_ID=123          # บัญชีทางรัฐ", encoding="utf-8")
    assert lg.read_env(f) == {"LANDSMAPS_DGA_ID": "123"}


@pytest.mark.parametrize("raw, value", [
    ("abc#123", "abc#123"),                     # # ติดกับค่า ไม่ใช่คอมเมนต์
    ("#abc", "#abc"),
    ("'abc #123'  # comment", "abc #123"),
    ('"abc#123"', "abc#123"),
    (r'"say \"hi\" \\ ok"', 'say "hi" \\ ok'),
    ("plain   # comment", "plain"),
    ("", ""),
])
def test_parse_value(raw, value):
    assert lg.parse_value(raw) == value


@pytest.mark.parametrize("password", [
    "abc#123", "a b", "#start", "it's", 'say "hi"', "it's \"x\" \\", "plain",
])
def test_write_env_then_read_env_keeps_password(tmp_path, password):
    """รหัสผ่านที่เขียนลง .env ต้องอ่านกลับได้ตรงเดิม (เดิม abc#123 ถูกอ่านกลับเป็น abc)"""
    f = lg.write_env({"LANDSMAPS_PASSWORD": password}, tmp_path / ".env")
    assert lg.read_env(f)["LANDSMAPS_PASSWORD"] == password


def test_credentials_reads_dga_account():
    env = {"LANDSMAPS_DGA_ID": "123", "LANDSMAPS_PASSWORD": "pw"}
    assert lg.credentials(env) == ("123", "pw")


def test_credentials_without_account():
    with pytest.raises(lg.LoginError, match="ไม่พบบัญชี"):
        lg.credentials({"LANDSMAPS_PASSWORD": "pw"})


def test_credentials_ignores_removed_account_kinds():
    """เหลือแค่บัญชี DGA — ตัวแปรของบัญชีชนิดอื่นที่ค้างใน .env ไม่ถูกใช้"""
    with pytest.raises(lg.LoginError, match="ไม่พบบัญชี"):
        lg.credentials({"LANDSMAPS_MAIL": "a@b.c", "LANDSMAPS_PASSWORD": "pw"})


def test_credentials_without_password():
    with pytest.raises(lg.LoginError, match="ไม่พบรหัสผ่าน"):
        lg.credentials({"LANDSMAPS_DGA_ID": "123"})


# ─────────────────────────── ล็อกอิน ───────────────────────────

def test_login_uses_dga(monkeypatch):
    monkeypatch.setattr(lg.openid, "login_openid", lambda u, p: f"dga-{u}-{p}")
    assert lg.login("123", "pw") == "dga-123-pw"


def test_login_wraps_openid_error(monkeypatch):
    def boom(u, p):
        raise lg.openid.OpenIDError("ยังไม่ได้พิสูจน์ตัวตน")
    monkeypatch.setattr(lg.openid, "login_openid", boom)
    with pytest.raises(lg.LoginError, match="ยังไม่ได้พิสูจน์ตัวตน"):
        lg.login("123", "pw")


def http_error(status: int, url: str) -> requests.HTTPError:
    r = requests.Response()
    r.status_code, r.url = status, url
    return requests.HTTPError(f"{status} Server Error for url: {url}", response=r)


@pytest.mark.parametrize("error, reason", [
    (http_error(503, "https://landsmaps.dol.go.th/Account/Login?access_token=SECRET"),
     "landsmaps.dol.go.th ตอบ HTTP 503"),
    (requests.ConnectionError("Max retries exceeded with url: /Account/Login?access_token=SECRET"),
     "ConnectionError"),
])
def test_login_turns_network_error_into_login_error_without_url(monkeypatch, error, reason):
    """เน็ตล่ม/เซิร์ฟเวอร์ตอบ 5xx -> LoginError (ให้ fetch_parcels ถอยไปใช้ token เดิมได้) และไม่โชว์ URL ที่มี token"""
    def boom(u, p):
        raise error
    monkeypatch.setattr(lg.openid, "login_openid", boom)
    with pytest.raises(lg.LoginError) as exc:
        lg.login("123", "pw")
    assert reason in str(exc.value)
    assert "SECRET" not in str(exc.value)


def test_save_token_writes_file(tmp_path):
    p = lg.save_token("abc", tmp_path / "Access_Key.txt")
    assert lg.keystore.load(p)["key"] == "abc"


def test_ensure_token_always_logs_in_again(monkeypatch):
    """ล็อกอินใหม่เสมอ แม้ token เดิมยังไม่หมดอายุ"""
    saved = {}
    monkeypatch.setattr(lg, "read_token", lambda: "old")
    monkeypatch.setattr(lg, "credentials", lambda: ("123", "pw"))
    monkeypatch.setattr(lg, "has_credentials", lambda: True)
    monkeypatch.setattr(lg, "login", lambda *a: "fresh")
    monkeypatch.setattr(lg, "save_credentials", lambda *a: saved.setdefault("args", a))
    assert lg.ensure_token() == "fresh"
    assert saved["args"] == ("123", "pw", "fresh")


def test_ensure_token_without_credentials_returns_existing(monkeypatch):
    monkeypatch.setattr(lg, "read_token", lambda: "old")
    monkeypatch.setattr(lg, "has_credentials", lambda: False)
    monkeypatch.setattr(lg, "login", lambda *a: pytest.fail("ไม่มีบัญชี ไม่ควรล็อกอิน"))
    assert lg.ensure_token() == "old"


# ─────────────────────────── บัญชีจาก Access_Key.txt ───────────────────────────

def test_credentials_falls_back_to_keystore(monkeypatch):
    monkeypatch.setattr(lg, "read_env", lambda: {})
    monkeypatch.setattr(os, "environ", {})
    monkeypatch.setattr(lg.keystore, "load",
                        lambda: {"kind": "openid", "user": "123", "pass": "pw"})
    assert lg.credentials() == ("123", "pw")


def test_credentials_keystore_without_kind_is_dga(monkeypatch):
    monkeypatch.setattr(lg, "read_env", lambda: {})
    monkeypatch.setattr(os, "environ", {})
    monkeypatch.setattr(lg.keystore, "load", lambda: {"user": "123", "pass": "pw"})
    assert lg.credentials() == ("123", "pw")


def test_credentials_prefers_env_over_keystore(monkeypatch):
    monkeypatch.setattr(lg, "read_env", lambda: {"LANDSMAPS_DGA_ID": "999",
                                                 "LANDSMAPS_PASSWORD": "env-pw"})
    monkeypatch.setattr(os, "environ", {})
    monkeypatch.setattr(lg.keystore, "load",
                        lambda: {"kind": "openid", "user": "123", "pass": "file-pw"})
    assert lg.credentials() == ("999", "env-pw")


def test_credentials_rejects_removed_kind_in_keystore(monkeypatch):
    monkeypatch.setattr(lg, "read_env", lambda: {})
    monkeypatch.setattr(os, "environ", {})
    monkeypatch.setattr(lg.keystore, "load",
                        lambda: {"kind": "mail", "user": "a@b.c", "pass": "pw"})
    with pytest.raises(lg.LoginError, match="รองรับเฉพาะบัญชี DGA"):
        lg.credentials()


# ─────────────────────────── เขียนบัญชีลง .env ───────────────────────────

def test_write_env_creates_file_with_comment(tmp_path):
    p = lg.write_env({"LANDSMAPS_DGA_ID": "123"}, tmp_path / ".env")
    text = p.read_text(encoding="utf-8")
    assert text.startswith("#")
    assert "LANDSMAPS_DGA_ID=123" in text


def test_write_env_replaces_existing_key_only(tmp_path):
    f = tmp_path / ".env"
    f.write_text("""
# keep me
LANDSMAPS_DGA_ID=old
OTHER=stay
""", encoding="utf-8")
    lg.write_env({"LANDSMAPS_DGA_ID": "new", "LANDSMAPS_PASSWORD": "pw"}, f)
    lines = f.read_text(encoding="utf-8").splitlines()
    assert lines == ["", "# keep me", "LANDSMAPS_DGA_ID=new", "OTHER=stay",
                     "LANDSMAPS_PASSWORD=pw"]


def test_write_env_ignores_commented_key(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# LANDSMAPS_DGA_ID=example", encoding="utf-8")
    lg.write_env({"LANDSMAPS_DGA_ID": "123"}, f)
    text = f.read_text(encoding="utf-8")
    assert "# LANDSMAPS_DGA_ID=example" in text and "LANDSMAPS_DGA_ID=123" in text
