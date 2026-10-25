import json

import pytest

from landsmaps import keystore as ks


def test_load_missing_file(tmp_path):
    assert ks.load(tmp_path / "nope.txt") == {}


def test_load_empty_file(tmp_path):
    p = tmp_path / "Access_Key.txt"
    p.write_text("   \n", encoding="utf-8")
    assert ks.load(p) == {}


def test_load_legacy_bare_token(tmp_path):
    """ไฟล์แบบเก่า (token เปล่าบรรทัดเดียว) ต้องใช้ต่อได้ ไม่ต้องแปลงมือ"""
    p = tmp_path / "Access_Key.txt"
    p.write_text("eyJhbGci.payload.sig\n", encoding="utf-8")
    assert ks.load(p) == {"key": "eyJhbGci.payload.sig"}


def test_load_json_dict(tmp_path):
    p = tmp_path / "Access_Key.txt"
    p.write_text(json.dumps({"kind": "openid", "user": "123", "pass": "pw", "key": "k"}),
                 encoding="utf-8")
    assert ks.load(p) == {"kind": "openid", "user": "123", "pass": "pw", "key": "k"}


def test_load_json_that_is_not_a_dict(tmp_path):
    p = tmp_path / "Access_Key.txt"
    p.write_text('["a"]', encoding="utf-8")
    with pytest.raises(ks.KeyFileError):
        ks.load(p)


def test_save_writes_readable_json(tmp_path):
    p = tmp_path / "Access_Key.txt"
    ks.save(p, kind="openid", user="123", key="tok", **{"pass": "pw"})
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["kind"] == "openid"
    assert data["user"] == "123"
    assert data["pass"] == "pw"
    assert data["key"] == "tok"
    assert data["saved_at"]


def test_save_keeps_fields_not_passed(tmp_path):
    p = tmp_path / "Access_Key.txt"
    ks.save(p, kind="openid", user="123", **{"pass": "pw"})
    ks.save(p, key="newtok")
    data = ks.load(p)
    assert data["user"] == "123" and data["pass"] == "pw"
    assert data["key"] == "newtok"


def test_save_upgrades_legacy_file_in_place(tmp_path):
    p = tmp_path / "Access_Key.txt"
    p.write_text("old.jwt.token\n", encoding="utf-8")
    ks.save(p, key="newtoken", user="123")
    data = ks.load(p)
    assert data["key"] == "newtoken"
    assert data["user"] == "123"


def test_save_leaves_no_temp_file(tmp_path):
    p = tmp_path / "Access_Key.txt"
    ks.save(p, key="tok")
    assert list(tmp_path.iterdir()) == [p]


def test_save_field_order_puts_key_after_credentials(tmp_path):
    p = tmp_path / "Access_Key.txt"
    ks.save(p, key="tok", user="123", kind="openid", **{"pass": "pw"})
    assert list(json.loads(p.read_text(encoding="utf-8"))) == list(ks.FIELDS)


@pytest.mark.parametrize("value, expected_prefix", [("", "-"), ("pw", "**")])
def test_mask_hides_value(value, expected_prefix):
    assert ks.mask(value).startswith(expected_prefix)


def test_mask_never_leaks_the_value():
    assert "hunter2" not in ks.mask("hunter2")


def test_describe_missing_file_tells_what_to_do(tmp_path):
    out = ks.describe(tmp_path / "nope.txt")
    assert "ยังไม่มีไฟล์นี้" in out and "get_token.py" in out


def test_describe_shows_fields_without_leaking_password(tmp_path):
    p = tmp_path / "Access_Key.txt"
    ks.save(p, kind="openid", user="1234567890123", key="eyJ" + "x" * 500,
            **{"pass": "secret-pw"})
    out = ks.describe(p)
    assert "1234567890123" in out and "openid" in out
    assert "secret-pw" not in out
    assert "eyJ" + "x" * 500 not in out
