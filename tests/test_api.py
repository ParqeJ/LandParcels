import base64
import json
from datetime import datetime, timedelta

import pytest

from landsmaps.api import (QuotaExceeded, check_token, load_detail_cache, open_detail_cache,
                           read_token, token_expiry)


def fake_jwt(exp: datetime) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": int(exp.timestamp())}).encode()).decode()
    return f"header.{payload.rstrip('=')}.signature"


def test_read_token_prefers_env(tmp_path, monkeypatch):
    f = tmp_path / "Access_Key.txt"
    f.write_text("from-file")
    monkeypatch.setenv("LANDSMAPS_TOKEN", "from-env")
    assert read_token(f) == "from-env"


def test_read_token_from_file_strips_bearer(tmp_path, monkeypatch):
    monkeypatch.delenv("LANDSMAPS_TOKEN", raising=False)
    f = tmp_path / "Access_Key.txt"
    f.write_text("﻿Bearer abc.def.ghi\n", encoding="utf-8")
    assert read_token(f) == "abc.def.ghi"


def test_read_token_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("LANDSMAPS_TOKEN", raising=False)
    assert read_token(tmp_path / "nope.txt") == ""


def test_token_expiry():
    exp = datetime.now().replace(microsecond=0) + timedelta(hours=3)
    assert token_expiry(fake_jwt(exp)) == exp
    assert token_expiry("not-a-jwt") is None


def test_check_token():
    assert "ไม่ล็อกอิน" in check_token("")
    assert "หมดอายุ" in check_token(fake_jwt(datetime.now() + timedelta(hours=1)))
    with pytest.raises(QuotaExceeded, match="หมดอายุแล้ว"):
        check_token(fake_jwt(datetime.now() - timedelta(hours=1)))


def test_load_detail_cache(tmp_path):
    f = tmp_path / "x_detail.jsonl"
    f.write_text('{"seq": "1", "info": {"rai": "2"}}\n\n{"seq": "2", "info": null}\n', encoding="utf-8")
    assert load_detail_cache(f) == {"1": {"rai": "2"}, "2": None}
    assert load_detail_cache(tmp_path / "nope.jsonl") == {}


def test_truncated_detail_line_is_skipped_and_next_append_starts_new_line(tmp_path):
    f = tmp_path / "x_detail.jsonl"
    f.write_text('{"seq": "1", "info": null}\n{"seq": "2", "inf', encoding="utf-8")   # ถูกหยุดกลางทาง
    assert load_detail_cache(f) == {"1": None}
    with open_detail_cache(f) as fh:
        fh.write('{"seq": "3", "info": null}\n')
    assert load_detail_cache(f) == {"1": None, "3": None}
