from datetime import datetime, timedelta

import pytest

import fetch_parcels
import search_parcel
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
