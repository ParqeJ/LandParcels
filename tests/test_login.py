import os

import pytest
import requests

from landsmaps import login as lg


def test_read_env_skips_comments_and_strips_quotes(tmp_path):
    f = tmp_path / ".env"
    f.write_text('# comment\nLANDSMAPS_MAIL="a@b.c"\n\nLANDSMAPS_PASSWORD = \'pw\'\nbroken\n',
                 encoding="utf-8")
    assert lg.read_env(f) == {"LANDSMAPS_MAIL": "a@b.c", "LANDSMAPS_PASSWORD": "pw"}


def test_read_env_missing_file(tmp_path):
    assert lg.read_env(tmp_path / "nope") == {}


def test_credentials_picks_account_kind():
    env = {"LANDSMAPS_PERSONAL_ID": "123", "LANDSMAPS_PASSWORD": "pw"}
    assert lg.credentials(env) == ("personal_id", "123", "pw")


def test_credentials_without_account():
    with pytest.raises(lg.LoginError, match="ไม่พบบัญชี"):
        lg.credentials({"LANDSMAPS_PASSWORD": "pw"})


def test_credentials_without_password():
    with pytest.raises(lg.LoginError, match="ไม่พบรหัสผ่าน"):
        lg.credentials({"LANDSMAPS_MAIL": "a@b.c"})


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeSession:
    """จำลอง GetJWTAccessToken + POST login คืน payload ที่กำหนด"""

    def __init__(self, login_payload):
        self.login_payload = login_payload
        self.headers = {}
        self.posted = None

    def get(self, url, timeout=None):
        return FakeResponse({"result": [{"access_token": "anon"}]})

    def post(self, url, json=None, timeout=None):
        self.posted = (url, json)
        return FakeResponse(self.login_payload)


@pytest.fixture
def fake_session(monkeypatch):
    def install(payload):
        s = FakeSession(payload)
        monkeypatch.setattr(requests, "Session", lambda: s)
        return s
    return install


def test_login_returns_account_token(fake_session):
    s = fake_session({"status": 200, "actived": True, "result": [{"access_token": "real"}]})
    assert lg.login("mail", "a@b.c", "pw") == "real"
    url, body = s.posted
    assert url.endswith("/LandsMaps/Login")
    assert body == {"mail": "a@b.c", "user_password": "pw"}
    assert s.headers["Authorization"] == "Bearer anon"


def test_login_uses_endpoint_per_account_kind(fake_session):
    s = fake_session({"result": [{"access_token": "real"}]})
    lg.login("personal_id", "123", "pw")
    assert s.posted[0].endswith("/LandsMaps/LoginDepartment")
    assert s.posted[1] == {"personal_id": "123", "user_password": "pw"}


def test_login_rejects_unknown_kind():
    with pytest.raises(lg.LoginError, match="ไม่รู้จักชนิดบัญชี"):
        lg.login("nope", "a", "pw")


def test_login_raises_landsmaps_message(fake_session):
    fake_session({"error": True, "message": "อีเมลหรือรหัสผ่านไม่ถูกต้อง", "result": None})
    with pytest.raises(lg.LoginError, match="อีเมลหรือรหัสผ่านไม่ถูกต้อง"):
        lg.login("mail", "a@b.c", "pw")


def test_login_raises_when_account_not_activated(fake_session):
    fake_session({"actived": False, "result": [{"access_token": "tmp"}]})
    with pytest.raises(lg.LoginError, match="ยังไม่ยืนยันตัวตน"):
        lg.login("mail", "a@b.c", "pw")


def test_login_raises_when_token_missing(fake_session):
    fake_session({"result": [{"mail": "a@b.c"}]})
    with pytest.raises(lg.LoginError, match="ไม่ได้ส่ง access_token"):
        lg.login("mail", "a@b.c", "pw")


def test_save_token_writes_file(tmp_path):
    p = lg.save_token("abc", tmp_path / "Access_Key.txt")
    assert lg.keystore.load(p)["key"] == "abc"


def test_ensure_token_always_logs_in_again(monkeypatch, tmp_path):
    """ล็อกอินใหม่เสมอ แม้ token เดิมยังไม่หมดอายุ"""
    saved = {}
    monkeypatch.setattr(lg, "read_token", lambda: "old")
    monkeypatch.setattr(lg, "credentials", lambda: ("mail", "a@b.c", "pw"))
    monkeypatch.setattr(lg, "has_credentials", lambda: True)
    monkeypatch.setattr(lg, "login_any", lambda *a: "fresh")
    monkeypatch.setattr(lg, "save_credentials", lambda *a: saved.setdefault("args", a))
    assert lg.ensure_token() == "fresh"
    assert saved["args"] == ("mail", "a@b.c", "pw", "fresh")


def test_ensure_token_without_credentials_returns_existing(monkeypatch):
    monkeypatch.setattr(lg, "read_token", lambda: "old")
    monkeypatch.setattr(lg, "has_credentials", lambda: False)
    monkeypatch.setattr(lg, "login_any", lambda *a: pytest.fail("ไม่มีบัญชี ไม่ควรล็อกอิน"))
    assert lg.ensure_token() == "old"


def test_login_any_routes_openid(monkeypatch):
    monkeypatch.setattr(lg.openid, "login_openid", lambda u, p: "dga-token")
    monkeypatch.setattr(lg, "login", lambda *a: pytest.fail("openid ไม่ควรไปทาง endpoint เดิม"))
    assert lg.login_any("openid", "123", "pw") == "dga-token"


def test_login_any_wraps_openid_error(monkeypatch):
    def boom(u, p):
        raise lg.openid.OpenIDError("ยังไม่ได้พิสูจน์ตัวตน")
    monkeypatch.setattr(lg.openid, "login_openid", boom)
    with pytest.raises(lg.LoginError, match="ยังไม่ได้พิสูจน์ตัวตน"):
        lg.login_any("openid", "123", "pw")


def test_login_any_routes_other_kinds(monkeypatch):
    monkeypatch.setattr(lg, "login", lambda kind, u, p: f"{kind}-token")
    assert lg.login_any("mail", "a@b.c", "pw") == "mail-token"


# ─────────────────────────── บัญชีจาก Access_Key.txt ───────────────────────────

def test_credentials_falls_back_to_keystore(monkeypatch):
    monkeypatch.setattr(lg, "read_env", lambda: {})
    monkeypatch.setattr(os, "environ", {})
    monkeypatch.setattr(lg.keystore, "load",
                        lambda: {"kind": "openid", "user": "123", "pass": "pw"})
    assert lg.credentials() == ("openid", "123", "pw")


def test_credentials_prefers_env_over_keystore(monkeypatch):
    monkeypatch.setattr(lg, "read_env", lambda: {"LANDSMAPS_MAIL": "a@b.c",
                                                 "LANDSMAPS_PASSWORD": "env-pw"})
    monkeypatch.setattr(os, "environ", {})
    monkeypatch.setattr(lg.keystore, "load",
                        lambda: {"kind": "openid", "user": "123", "pass": "file-pw"})
    assert lg.credentials() == ("mail", "a@b.c", "env-pw")


def test_credentials_rejects_bad_kind_in_keystore(monkeypatch):
    monkeypatch.setattr(lg, "read_env", lambda: {})
    monkeypatch.setattr(os, "environ", {})
    monkeypatch.setattr(lg.keystore, "load",
                        lambda: {"kind": "nope", "user": "123", "pass": "pw"})
    with pytest.raises(lg.LoginError, match="ไม่ถูกต้อง"):
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


def test_read_env_strips_trailing_comment(tmp_path):
    f = tmp_path / ".env"
    f.write_text("LANDSMAPS_MAIL=a@b.c          # บัญชีอีเมล", encoding="utf-8")
    assert lg.read_env(f) == {"LANDSMAPS_MAIL": "a@b.c"}
