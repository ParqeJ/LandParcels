from datetime import datetime, timedelta

import pytest
import requests
from shapely.geometry import box

import fetch_parcels
import get_token
import search_parcel
from landsmaps import login as lg
from landsmaps.keystore import KeyFileError
from test_api import fake_jwt


def test_fetch_parcels_name_requires_single_file():
    with pytest.raises(SystemExit):
        fetch_parcels.parse_args(["a.kmz", "b.kmz", "--name", "x"])


def test_fetch_parcels_no_area_files_returns_1(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_parcels, "AREAS_DIR", tmp_path)
    assert fetch_parcels.main([]) == 1


def test_fetch_parcels_continues_after_failure_and_stops_detail_after_quota(monkeypatch):
    seen = []

    class QuotaHit:
        quota_hit = True

    def fake_run(path, *, layer, name, fetch_detail):
        seen.append((path.name, fetch_detail))
        if path.name == "bad.kmz":
            raise ValueError("boom")
        return QuotaHit()

    monkeypatch.setattr(fetch_parcels, "run_area", fake_run)
    monkeypatch.setattr(fetch_parcels, "ensure_token", lambda: "")
    code = fetch_parcels.main(["bad.kmz", "a.kmz", "b.kmz"])
    assert code == 1
    assert seen == [("bad.kmz", True), ("a.kmz", True), ("b.kmz", False)]


def test_fetch_parcels_expired_token_stops_before_any_area(monkeypatch):
    monkeypatch.setattr(fetch_parcels, "ensure_token",
                        lambda: fake_jwt(datetime.now() - timedelta(hours=1)))
    monkeypatch.setattr(fetch_parcels, "run_area", lambda *a, **k: pytest.fail("ไม่ควรเริ่มพื้นที่ใด"))
    assert fetch_parcels.main(["a.kmz"]) == 1


def test_fetch_parcels_reports_login_failure(monkeypatch):
    """ล็อกอินไม่ผ่าน และไม่มี token เดิมให้ใช้ -> หยุดก่อนเริ่มพื้นที่ใด"""
    def boom():
        raise fetch_parcels.LoginError("อีเมลหรือรหัสผ่านไม่ถูกต้อง")

    monkeypatch.setattr(fetch_parcels, "ensure_token", boom)
    monkeypatch.setattr(fetch_parcels, "read_token", lambda: "")
    monkeypatch.setattr(fetch_parcels, "run_area", lambda *a, **k: pytest.fail("ไม่ควรเริ่มพื้นที่ใด"))
    assert fetch_parcels.main(["a.kmz"]) == 1


def test_fetch_parcels_falls_back_to_saved_token(monkeypatch):
    """ล็อกอินไม่ผ่านแต่ Access_Key.txt ยังมี token ที่ใช้ได้ -> ทำงานต่อด้วยของเดิม"""
    def boom():
        raise fetch_parcels.LoginError("ยังไม่ได้พิสูจน์ตัวตนกับ OpenID")

    seen = []
    monkeypatch.setattr(fetch_parcels, "ensure_token", boom)
    monkeypatch.setattr(fetch_parcels, "read_token",
                        lambda: fake_jwt(datetime.now() + timedelta(hours=5)))
    class Result:
        quota_hit = False

    monkeypatch.setattr(fetch_parcels, "run_area",
                        lambda path, **k: seen.append(path.name) or Result())
    assert fetch_parcels.main(["a.kmz"]) == 0
    assert seen == ["a.kmz"]


def test_fetch_parcels_falls_back_but_saved_token_expired(monkeypatch):
    """ล็อกอินไม่ผ่าน และ token เดิมก็หมดอายุแล้ว -> หยุด"""
    def boom():
        raise fetch_parcels.LoginError("ยังไม่ได้พิสูจน์ตัวตนกับ OpenID")

    monkeypatch.setattr(fetch_parcels, "ensure_token", boom)
    monkeypatch.setattr(fetch_parcels, "read_token",
                        lambda: fake_jwt(datetime.now() - timedelta(hours=1)))
    monkeypatch.setattr(fetch_parcels, "run_area", lambda *a, **k: pytest.fail("ไม่ควรเริ่มพื้นที่ใด"))
    assert fetch_parcels.main(["a.kmz"]) == 1


@pytest.mark.parametrize("argv", [
    ["--prov", "3", "--amphur", "07", "1"],
    ["--prov", "36", "--amphur", "ab", "1"],
    ["--prov", "36", "--amphur", "07", "12a"],
    ["--prov", "๓๖", "--amphur", "07", "1"],
    ["--prov", "36", "--amphur", "07", "๑๒"],
])
def test_search_parcel_rejects_bad_input(argv):
    with pytest.raises(SystemExit):
        search_parcel.parse_args(argv)


def test_search_parcel_valid_args():
    args = search_parcel.parse_args(["--prov", "36", "--amphur", "07", "30219", "30220"])
    assert args.parcel_nos == ["30219", "30220"]


# ─────────────────────────── ล็อกอินไม่ผ่าน / Access_Key.txt เสีย ───────────────────────────

def test_fetch_parcels_falls_back_when_login_network_fails(monkeypatch):
    """เน็ตล่ม/DGA ตอบ 5xx ตอนล็อกอิน แต่ token เดิมยังไม่หมดอายุ -> ทำงานต่อด้วยของเดิม (เดิมพังเป็น traceback)"""
    def down(user, password):
        raise requests.ConnectionError("Max retries exceeded")

    monkeypatch.setattr(lg, "has_credentials", lambda: True)
    monkeypatch.setattr(lg, "credentials", lambda: ("123", "pw"))
    monkeypatch.setattr(lg.openid, "login_openid", down)
    monkeypatch.setattr(lg, "save_credentials", lambda *a: pytest.fail("ล็อกอินไม่ผ่าน ไม่ควรบันทึก"))
    monkeypatch.setattr(fetch_parcels, "read_token",
                        lambda: fake_jwt(datetime.now() + timedelta(hours=5)))
    seen = []

    class Result:
        quota_hit = False

    monkeypatch.setattr(fetch_parcels, "run_area",
                        lambda path, **k: seen.append(path.name) or Result())
    assert fetch_parcels.main(["a.kmz"]) == 0
    assert seen == ["a.kmz"]


def broken_key_file():
    raise KeyFileError("Access_Key.txt ไม่ใช่ JSON ที่ถูกต้อง")


def test_fetch_parcels_reports_broken_key_file(monkeypatch, capsys):
    monkeypatch.setattr(fetch_parcels, "ensure_token", broken_key_file)
    monkeypatch.setattr(fetch_parcels, "run_area", lambda *a, **k: pytest.fail("ไม่ควรเริ่มพื้นที่ใด"))
    assert fetch_parcels.main(["a.kmz"]) == 1
    assert "ไม่ใช่ JSON ที่ถูกต้อง" in capsys.readouterr().out


def test_get_token_where_reports_broken_key_file(monkeypatch, capsys):
    monkeypatch.setattr(get_token.keystore, "describe", broken_key_file)
    assert get_token.main(["--where"]) == 1
    assert "ไม่ใช่ JSON ที่ถูกต้อง" in capsys.readouterr().out


def test_get_token_reports_broken_key_file(monkeypatch, capsys):
    monkeypatch.setattr(get_token, "credentials", broken_key_file)
    assert get_token.main([]) == 1
    assert "ไม่ใช่ JSON ที่ถูกต้อง" in capsys.readouterr().out


def test_get_token_no_longer_accepts_kind():
    with pytest.raises(SystemExit):
        get_token.parse_args(["--kind", "mail"])


def test_get_token_saves_after_login(monkeypatch):
    saved = []
    monkeypatch.setattr(get_token, "credentials", lambda: ("123", "pw"))
    monkeypatch.setattr(get_token, "login", lambda u, p: "tok")
    monkeypatch.setattr(get_token, "save_credentials", lambda *a: saved.append(a))
    assert get_token.main([]) == 0
    assert saved == [("123", "pw", "tok")]


def test_search_parcel_reports_broken_key_file(monkeypatch, capsys):
    monkeypatch.setattr(search_parcel, "read_token", broken_key_file)
    assert search_parcel.main(["--prov", "36", "--amphur", "07", "1"]) == 1
    assert "ไม่ใช่ JSON ที่ถูกต้อง" in capsys.readouterr().out


def test_search_parcel_reports_expired_token(monkeypatch, capsys):
    monkeypatch.setattr(search_parcel, "read_token",
                        lambda: fake_jwt(datetime.now() - timedelta(hours=1)))
    assert search_parcel.main(["--prov", "36", "--amphur", "07", "1"]) == 1
    assert "หมดอายุ" in capsys.readouterr().out


# ─────────────────────────── search_parcel: ข้อมูลแปลงไม่ครบ ───────────────────────────

def test_search_parcel_skips_incomplete_parcel_and_keeps_the_rest(monkeypatch, capsys):
    """แปลงแรกข้อมูลไม่ครบ (ไม่มี e/n) แปลงที่สองไม่มี tumbolname -> ข้ามแค่แปลงแรก แปลงที่สองยังถูกบันทึก"""
    infos = {
        "1": {"parcel_seq": "11", "zone": "47"},
        "2": {"parcel_seq": "22", "zone": "47", "e": "1", "n": "2", "utm1": "5339", "utm2": "4",
              "utm": "5339 IV 7808-00 (4000)", "rai": "1", "ngan": "2", "wa": "3", "parcelno": "2"},
    }

    class FakeAPI:
        def __init__(self, token):
            pass

        def parcel_by_no(self, prov, amphur, no):
            return infos[no]

    def fake_geometry(info, zone):
        float(info["e"])                        # แปลงแรกไม่มี e -> KeyError แบบเดียวกับของจริง
        return box(0, 0, 1, 1), "7"

    written = []
    monkeypatch.setattr(search_parcel, "read_token", lambda: "")
    monkeypatch.setattr(search_parcel, "LandsMapsAPI", FakeAPI)
    monkeypatch.setattr(search_parcel, "get_geometry", fake_geometry)
    monkeypatch.setattr(search_parcel, "SLEEP_SEC", 0)
    monkeypatch.setattr(search_parcel, "to_shp", lambda rows, geoms, crs, path: written.append(rows))

    assert search_parcel.main(["--prov", "36", "--amphur", "07", "1", "2"]) == 0
    out = capsys.readouterr().out
    assert "ข้อมูลจาก LandsMaps ไม่ครบ" in out
    assert len(written) == 1 and [r["Cert_No"] for r in written[0]] == ["2"]
