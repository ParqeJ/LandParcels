import pytest
import requests

from landsmaps import openid as oid

LOGIN_PAGE = """
<form method="post" action="">
  <input type="hidden" id="ReturnUrl" name="ReturnUrl"
         value="/connect/authorize/callback?response_type=code&amp;client_id=abc" />
  <input id="AppClientId" name="AppClientId" type="hidden" value="abc" />
  <input id="AppName" name="AppName" type="hidden" value="&#xE23;&#xE30;&#xE1A;&#xE1A;" />
  <input id="OrgName" name="OrgName" type="hidden" value="org" />
  <input type="hidden" id="Ott" name="Ott" value="" />
  <input type="text" id="UserName" name="UserName" value="" />
  <input type="text" id="MaskedInput" name="MaskedInput" />
  <input name="__RequestVerificationToken" type="hidden" value="CfDJ8-abc" />
  <input type="hidden" id="hdfTwoFactorOtt" name="hdfTwoFactorOtt" value="" />
  <div class="login-message text-center"></div>
</form>
"""


def test_form_fields_reads_name_and_value():
    f = oid.form_fields(LOGIN_PAGE)
    assert f["AppClientId"] == "abc"
    assert f["UserName"] == ""
    assert f["__RequestVerificationToken"] == "CfDJ8-abc"


def test_form_fields_unescapes_html_entities():
    """ReturnUrl มี &amp; ถ้าไม่แปลงกลับ DGA จะตีความ query string ผิด"""
    assert "&client_id=abc" in oid.form_fields(LOGIN_PAGE)["ReturnUrl"]


def test_form_fields_falls_back_to_id_when_name_missing():
    assert oid.form_fields('<input id="qrStatus" value="Pending">') == {"qrStatus": "Pending"}


def test_form_fields_ignores_input_without_name_or_id():
    assert oid.form_fields('<input type="submit" value="go">') == {}


CONSENT_PAGE = """
<meta http-equiv="refresh" content="0;url=/connect/authorize/callback?response_type=code&amp;client_id=abc"
      data-url="/connect/authorize/callback?response_type=code&amp;client_id=abc">
"""


def test_meta_refresh_reads_target():
    """หน้า /consent ของ DGA สั่งไปต่อด้วย meta refresh ไม่ใช่ HTTP redirect"""
    assert oid.meta_refresh(CONSENT_PAGE) == "/connect/authorize/callback?response_type=code&client_id=abc"


def test_meta_refresh_reads_content_when_no_data_url():
    page = "<META HTTP-EQUIV='Refresh' CONTENT='0; URL=/next?a=1'>"
    assert oid.meta_refresh(page) == "/next?a=1"


def test_meta_refresh_none_on_normal_page():
    assert oid.meta_refresh(LOGIN_PAGE) is None


class Hop:
    """คำตอบปลอมสำหรับ follow(): redirect ด้วย Location หรือหน้า HTML ธรรมดา"""

    def __init__(self, url, location=None, text=""):
        self.url = url
        self.text = text
        self.is_redirect = location is not None
        self.status_code = 302 if location else 200
        self.headers = {"Location": location} if location else {}


class HopSession:
    def __init__(self, pages):
        self.pages = pages
        self.visited = []

    def get(self, url, timeout=None, allow_redirects=True):
        self.visited.append(url)
        return self.pages[url]


def test_follow_continues_through_meta_refresh_page():
    dga = "https://connect.egov.go.th"
    callback = f"{dga}/connect/authorize/callback?response_type=code&client_id=abc"
    landed = "https://landsmaps.dol.go.th/callback?code=xyz"
    s = HopSession({callback: Hop(callback, location=landed), landed: Hop(landed, text="ok")})

    r = oid.follow(s, Hop(f"{dga}/consent", text=CONSENT_PAGE))

    assert r.url == landed
    assert s.visited == [callback, landed]


def test_follow_refuses_meta_refresh_to_other_host():
    page = '<meta http-equiv="refresh" content="0;url=https://evil.example/steal">'
    with pytest.raises(oid.OpenIDError, match="evil.example"):
        oid.follow(HopSession({}), Hop("https://connect.egov.go.th/consent", text=page))


def test_error_message_extracts_text():
    page = '<div class="login-message text-center"><span>บัญชีไม่ถูกต้อง</span></div>'
    assert oid.error_message(page) == "บัญชีไม่ถูกต้อง"


def test_error_message_empty_when_no_error():
    assert oid.error_message(LOGIN_PAGE) == ""


class FakeResponse:
    is_redirect = False                 # follow() คืนคำตอบนี้ทันที

    def __init__(self, url="", text="", payload=None):
        self.url = url
        self.text = text
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeSession:
    """จำลอง 4 ขั้นของ flow DGA: JWT -> Account/Login -> POST ฟอร์ม -> LoginOpenID"""

    def __init__(self, after_post, openid_payload=None):
        self.after_post = after_post
        self.openid_payload = openid_payload
        self.headers = {}
        self.posted = []

    def get(self, url, timeout=None, params=None, allow_redirects=True):
        if "JWT" in url:
            return FakeResponse(payload={"result": [{"access_token": "anon"}]})
        return FakeResponse(url="https://connect.egov.go.th/Account/Login?ReturnUrl=x",
                            text=LOGIN_PAGE)

    def post(self, url, data=None, timeout=None, headers=None, json=None, allow_redirects=True):
        self.posted.append((url, data, headers))
        if "LoginOpenID" in url:
            return FakeResponse(url=url, payload=self.openid_payload)
        return self.after_post


@pytest.fixture
def fake_session(monkeypatch):
    def install(after_post, openid_payload=None):
        s = FakeSession(after_post, openid_payload)
        monkeypatch.setattr(requests, "Session", lambda: s)
        return s
    return install


def landed_on_landsmaps():
    return FakeResponse(url="https://landsmaps.dol.go.th/callback?code=xyz", text="ok")


def test_login_openid_returns_account_token(fake_session):
    s = fake_session(landed_on_landsmaps(),
                     {"result": [{"access_token": "real", "user_id": 7}]})
    assert oid.login_openid("1234567890123", "pw") == "real"

    form_url, form_data, _ = s.posted[0]
    assert form_url == "https://connect.egov.go.th/Account/Login?ReturnUrl=x"
    assert form_data["UserName"] == "1234567890123"
    assert form_data["MaskedInput"] == "pw"
    assert form_data["__RequestVerificationToken"] == "CfDJ8-abc"
    assert form_data["button"] == "login"        # ไม่ส่ง = DGA ถือว่ากด "ยกเลิก"

    openid_url, _, headers = s.posted[1]
    assert openid_url.endswith("/LandsMaps/LoginOpenID")
    assert headers["Authorization"] == "Bearer anon"


def test_login_openid_raises_dga_message(fake_session):
    page = '<div class="login-message">บัญชีหรือรหัสผ่านไม่ถูกต้อง</div>'
    fake_session(FakeResponse(url="https://connect.egov.go.th/Account/Login", text=page))
    with pytest.raises(oid.OpenIDError, match="บัญชีหรือรหัสผ่านไม่ถูกต้อง"):
        oid.login_openid("123", "pw")


def test_login_openid_detects_two_factor(fake_session):
    page = '<input id="hdfTwoFactorOtt" name="hdfTwoFactorOtt" value="OTT-123">'
    fake_session(FakeResponse(url="https://connect.egov.go.th/Account/Login", text=page))
    with pytest.raises(oid.OpenIDError, match="OTP"):
        oid.login_openid("123", "pw")


def test_login_openid_raises_when_form_changed(fake_session, monkeypatch):
    fake_session(landed_on_landsmaps())
    monkeypatch.setattr(oid, "form_fields", lambda page: {"Something": "else"})
    with pytest.raises(oid.OpenIDError, match="ฟอร์มเปลี่ยนไปแล้ว"):
        oid.login_openid("123", "pw")


def test_login_openid_raises_when_landsmaps_rejects(fake_session):
    fake_session(landed_on_landsmaps(), {"result": [], "message": "ไม่พบบัญชีนี้"})
    with pytest.raises(oid.OpenIDError, match="ไม่พบบัญชีนี้"):
        oid.login_openid("123", "pw")


def test_login_openid_raises_when_token_missing(fake_session):
    fake_session(landed_on_landsmaps(), {"result": [{"user_id": 7}]})
    with pytest.raises(oid.OpenIDError, match="ไม่ได้ส่ง access_token"):
        oid.login_openid("123", "pw")
