import base64
import io
import json
import time
import zipfile

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from dashboard import auth, docs, files, server  # noqa: E402
from landsmaps import keystore  # noqa: E402

BASE = "http://127.0.0.1:8765"


def fake_jwt(exp: float) -> str:
    def enc(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{enc({'alg': 'none'})}.{enc({'exp': int(exp)})}.sig"


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    areas, output = tmp_path / "areas", tmp_path / "output"
    areas.mkdir()
    output.mkdir()
    for mod in (server, files):
        monkeypatch.setattr(mod, "AREAS_DIR", areas)
        monkeypatch.setattr(mod, "OUTPUT_DIR", output)
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "Access_Key.txt")
    monkeypatch.setattr(auth, "ENV_FILE", tmp_path / ".env")
    for var in ("LANDSMAPS_TOKEN", "LANDSMAPS_DGA_ID", "LANDSMAPS_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    return areas, output, tmp_path


@pytest.fixture
def client(dirs):
    return TestClient(server.app, base_url=BASE)


def upload(client, *named, overwrite=False):
    payload = [("files", (name, data, "application/octet-stream")) for name, data in named]
    return client.post("/api/areas/upload", files=payload, data={"overwrite": str(overwrite).lower()})


# ─────────────────────────── กันเว็บอื่นยิงเข้ามา ───────────────────────────

def test_rejects_non_localhost_host(dirs):
    c = TestClient(server.app, base_url="http://evil.example:8765")
    assert c.get("/api/jobs").status_code == 403


def test_rejects_cross_origin_post(client):
    r = client.post("/api/auth/logout", json={}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_allows_same_origin_post(client):
    r = client.post("/api/auth/logout", json={}, headers={"Origin": BASE})
    assert r.status_code == 200


def test_display_cmd_hides_token():
    assert server._display_cmd(["py", "x.py", "--token", "SECRET", "60"]) == ["py", "x.py", "--token", "***", "60"]


# ─────────────────────────── upload ───────────────────────────

def test_upload_geojson_saves_and_checks_area(client, dirs, area_file):
    src = area_file(name="site.geojson")
    r = upload(client, ("site.geojson", src.read_bytes()))
    assert r.status_code == 200, r.text
    assert r.json()["saved"] == [{"name": "site.geojson", "kind": "geojson", "ok": True, "message": "อ่านขอบเขตได้"}]
    assert (dirs[0] / "site.geojson").exists()
    assert not [p for p in dirs[0].iterdir() if p.name.startswith(".upload_")]


def test_upload_unreadable_file_is_kept_with_warning(client, dirs):
    r = upload(client, ("broken.geojson", b"not json"))
    assert r.status_code == 200
    assert r.json()["saved"][0]["ok"] is False
    assert (dirs[0] / "broken.geojson").exists()


def test_upload_rejects_unsupported_suffix(client, dirs):
    r = upload(client, ("tool.exe", b"MZ"))
    assert r.status_code == 400
    assert not any(p for p in dirs[0].iterdir() if not p.name.startswith("."))


def test_upload_rejects_incomplete_shapefile(client):
    r = upload(client, ("a.shp", b"x"), ("a.shx", b"x"))
    assert r.status_code == 400
    assert ".dbf" in r.json()["detail"]


def test_upload_conflict_then_overwrite_moves_old_aside(client, dirs, area_file):
    data = area_file(name="site.geojson").read_bytes()
    (dirs[0] / "site.geojson").write_bytes(b"old")
    r = upload(client, ("site.geojson", data))
    assert r.status_code == 409
    assert r.json()["detail"]["conflicts"] == ["site.geojson"]
    assert (dirs[0] / "site.geojson").read_bytes() == b"old"

    r = upload(client, ("site.geojson", data), overwrite=True)
    assert r.status_code == 200
    assert (dirs[0] / "site.geojson").read_bytes() == data
    replaced = list((dirs[0] / files.REPLACED_DIR).iterdir())
    assert len(replaced) == 1 and replaced[0].read_bytes() == b"old"


def test_upload_zip_with_shapefile_and_gdb_folder(client, dirs, area_file):
    shp = area_file(name="plot.shp")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for part in shp.parent.glob("plot.*"):
            z.write(part, f"export/{part.name}")
        z.writestr("export/site.gdb/a00000001.gdbtable", b"x")
        z.writestr("export/readme.txt", b"ignored")
    r = upload(client, ("bundle.zip", buf.getvalue()))
    assert r.status_code == 200, r.text
    names = {s["name"] for s in r.json()["saved"]}
    assert names == {"plot.shp", "site.gdb"}
    assert (dirs[0] / "site.gdb" / "a00000001.gdbtable").exists()
    assert not (dirs[0] / "readme.txt").exists()


def test_upload_zip_slip_rejected(client, dirs):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../../evil.kmz", b"x")
    r = upload(client, ("bad.zip", buf.getvalue()))
    assert r.status_code == 400
    assert not (dirs[2] / "evil.kmz").exists()


@pytest.mark.parametrize("member, dest", [
    ("site.kmz", "site.kmz"),
    ("sub/dir/site.kmz", "site.kmz"),
    ("proj/bnn.gdb/a.gdbtable", "bnn.gdb/a.gdbtable"),
    ("readme.txt", None),
    ("__MACOSX/site.kmz", None),
    ("folder/", None),
])
def test_zip_dest(member, dest):
    got = files.zip_dest(member)
    assert (got.as_posix() if got else None) == dest


@pytest.mark.parametrize("member", ["../x.kmz", "/abs/x.kmz", "C:/x.kmz", "a/../../x.kmz"])
def test_zip_dest_rejects_unsafe(member):
    with pytest.raises(HTTPException):
        files.zip_dest(member)


@pytest.mark.parametrize("raw, name", [
    ("site.kmz", "site.kmz"),
    ("C:\\fakepath\\พื้นที่ A.kmz", "พื้นที่ A.kmz"),
    ("../../x.kmz", "x.kmz"),
])
def test_clean_name(raw, name):
    assert files.clean_name(raw) == name


@pytest.mark.parametrize("raw", ["", ".env", "CON.kmz", "a<b.kmz"])
def test_clean_name_rejects(raw):
    with pytest.raises(HTTPException):
        files.clean_name(raw)


# ─────────────────────────── download ───────────────────────────

def test_download_shp_zips_sidecars_without_lock(client, dirs):
    out = dirs[1] / "bnn"
    out.mkdir()
    for ext in ("shp", "shx", "dbf", "prj", "cpg", "shp.xml", "shp.PC.123.sr.lock"):
        (out / f"bnn_parcel.{ext}").write_bytes(b"x")
    (out / "bnn_other.shp").write_bytes(b"x")
    r = client.get("/api/output/download", params={"path": "bnn/bnn_parcel.shp"})
    assert r.status_code == 200
    names = set(zipfile.ZipFile(io.BytesIO(r.content)).namelist())
    assert names == {f"bnn_parcel.{e}" for e in ("shp", "shx", "dbf", "prj", "cpg", "shp.xml")}


def test_download_folder_as_zip(client, dirs):
    out = dirs[1] / "cbd"
    out.mkdir()
    (out / "a.gpkg").write_bytes(b"x")
    r = client.get("/api/output/download", params={"path": "cbd"})
    assert r.status_code == 200
    assert zipfile.ZipFile(io.BytesIO(r.content)).namelist() == ["cbd/a.gpkg"]


def test_download_outside_output_rejected(client, dirs):
    (dirs[2] / "secret.txt").write_text("x")
    r = client.get("/api/output/download", params={"path": "../secret.txt"})
    assert r.status_code == 400


def test_output_list_has_dir(client, dirs):
    (dirs[1] / "bnn").mkdir()
    (dirs[1] / "bnn" / "x.shp").write_bytes(b"x")
    (dirs[1] / "top.gpkg").write_bytes(b"x")
    items = {i["path"]: i["dir"] for i in client.get("/api/output").json()["items"]}
    assert items == {"bnn/x.shp": "bnn", "top.gpkg": ""}


# ─────────────────────────── บัญชี LandsMaps ───────────────────────────

def test_status_without_token(client):
    s = client.get("/api/auth/status").json()
    assert s["logged_in"] is False and s["remembered"] is False
    assert "LandsMaps" in s["provider"]


def test_login_remember_saves_account_without_leaking(client, dirs, monkeypatch):
    token = fake_jwt(time.time() + 3600)
    monkeypatch.setattr(auth.lg, "login", lambda u, p: token)
    r = client.post("/api/auth/login", json={"user": "1234567890123", "password": "pw#1", "remember": True})
    assert r.status_code == 200
    body = r.text
    assert token not in body and "pw#1" not in body and "1234567890123" not in body
    s = r.json()
    assert s["logged_in"] and s["remembered"] and s["user"] == "123********23"
    saved = keystore.load(auth.TOKEN_FILE)
    assert saved["key"] == token and saved["pass"] == "pw#1"
    assert auth.lg.read_env(auth.ENV_FILE)["LANDSMAPS_PASSWORD"] == "pw#1"


def test_login_without_remember_keeps_no_password(client, dirs, monkeypatch):
    auth.lg.write_env({"LANDSMAPS_DGA_ID": "old", "LANDSMAPS_PASSWORD": "old-pw"}, auth.ENV_FILE)
    monkeypatch.setattr(auth.lg, "login", lambda u, p: fake_jwt(time.time() + 3600))
    s = client.post("/api/auth/login", json={"user": "1234567890123", "password": "pw", "remember": False}).json()
    assert s["logged_in"] and not s["remembered"]
    assert "pass" not in keystore.load(auth.TOKEN_FILE)
    assert auth.lg.read_env(auth.ENV_FILE) == {}


def test_login_needs_both_fields(client):
    assert client.post("/api/auth/login", json={"user": "123"}).status_code == 400


def test_renew_without_saved_account(client):
    assert client.post("/api/auth/login", json={}).status_code == 400


def test_renew_uses_saved_account(client, dirs, monkeypatch):
    keystore.save(auth.TOKEN_FILE, kind="openid", user="1234567890123", password="pw")
    seen = {}
    monkeypatch.setattr(auth.lg, "login", lambda u, p: seen.update(u=u, p=p) or fake_jwt(time.time() + 60))
    assert client.post("/api/auth/login", json={}).status_code == 200
    assert seen == {"u": "1234567890123", "p": "pw"}


def test_login_failure_returns_401(client, monkeypatch):
    def boom(u, p):
        raise auth.lg.LoginError("รหัสผ่านไม่ถูกต้อง")
    monkeypatch.setattr(auth.lg, "login", boom)
    r = client.post("/api/auth/login", json={"user": "123", "password": "bad"})
    assert r.status_code == 401
    assert "รหัสผ่านไม่ถูกต้อง" in r.json()["detail"]


def test_expired_token_status(client, dirs):
    keystore.save(auth.TOKEN_FILE, key=fake_jwt(time.time() - 60))
    s = client.get("/api/auth/status").json()
    assert s["expired"] and not s["logged_in"] and s["remaining_sec"] == 0


def test_logout_and_forget(client, dirs):
    keystore.save(auth.TOKEN_FILE, kind="openid", user="1234567890123", password="pw",
                  key=fake_jwt(time.time() + 3600))
    s = client.post("/api/auth/logout", json={"forget": False}).json()
    assert not s["logged_in"] and s["remembered"]
    s = client.post("/api/auth/logout", json={"forget": True}).json()
    assert not s["remembered"] and s["user"] is None
    assert set(keystore.load(auth.TOKEN_FILE)) == {"kind", "saved_at"}


@pytest.mark.parametrize("user, masked", [
    ("1234567890123", "123********23"),
    ("abc", "a**"),
    ("someone@mail.com", "som***********om"),
])
def test_mask_user(user, masked):
    assert auth.mask_user(user) == masked


# ─────────────────────────── ลบ areas (ย้ายไป .deleted/) ───────────────────────────

def delete(client, *names):
    return client.post("/api/areas/delete", json={"names": list(names)})


def test_delete_moves_area_to_trash(client, dirs):
    (dirs[0] / "a.geojson").write_bytes(b"A")
    (dirs[0] / "keep.kmz").write_bytes(b"K")
    r = delete(client, "a.geojson")
    assert r.status_code == 200, r.text
    trash = dirs[0] / r.json()["trash"]
    assert (trash / "a.geojson").read_bytes() == b"A"
    assert not (dirs[0] / "a.geojson").exists()
    assert (dirs[0] / "keep.kmz").exists()
    assert [i["name"] for i in client.get("/api/areas").json()["items"]] == ["keep.kmz"]


def test_delete_shapefile_takes_whole_set_but_not_lookalike(client, dirs):
    for n in ("a.shp", "a.shx", "a.dbf", "a.prj", "a.shp.xml", "a.b.shp", "a.b.shx", "a.b.dbf"):
        (dirs[0] / n).write_bytes(b"x")
    r = delete(client, "a.shp")
    assert r.status_code == 200, r.text
    trash = dirs[0] / r.json()["trash"]
    assert sorted(p.name for p in trash.iterdir()) == ["a.dbf", "a.prj", "a.shp", "a.shp.xml", "a.shx"]
    assert sorted(p.name for p in dirs[0].iterdir() if not p.name.startswith(".")) == ["a.b.dbf", "a.b.shp", "a.b.shx"]


def test_delete_gdb_folder_and_many_at_once(client, dirs):
    gdb = dirs[0] / "site.gdb"
    gdb.mkdir()
    (gdb / "a0000001.gdbtable").write_bytes(b"x")
    (dirs[0] / "b.kml").write_bytes(b"x")
    r = delete(client, "site.gdb", "b.kml", "b.kml")
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == ["site.gdb", "b.kml"]
    trash = dirs[0] / r.json()["trash"]
    assert (trash / "site.gdb" / "a0000001.gdbtable").exists() and (trash / "b.kml").exists()


@pytest.mark.parametrize("name,status", [
    ("../secret.geojson", 400), ("sub/a.geojson", 400), (".deleted", 400),
    ("missing.kmz", 404), ("notes.txt", 400),
])
def test_delete_rejects_bad_names(client, dirs, name, status):
    (dirs[0] / "notes.txt").write_bytes(b"x")
    assert delete(client, name).status_code == status
    assert (dirs[0] / "notes.txt").exists()


def test_delete_all_or_nothing_when_one_name_bad(client, dirs):
    (dirs[0] / "a.kmz").write_bytes(b"x")
    assert delete(client, "a.kmz", "missing.kmz").status_code == 404
    assert (dirs[0] / "a.kmz").exists()


def test_delete_empty_list_rejected(client):
    assert delete(client).status_code == 400


def test_delete_rolls_back_when_a_part_is_locked(client, dirs, monkeypatch):
    for n in ("a.shp", "a.shx", "a.dbf"):
        (dirs[0] / n).write_bytes(b"x")
    real = files.os.replace

    def flaky(src, dst):
        if str(src).endswith("a.shx"):
            raise PermissionError(13, "file in use")
        return real(src, dst)

    monkeypatch.setattr(files.os, "replace", flaky)
    r = delete(client, "a.shp")
    assert r.status_code == 409
    assert sorted(p.name for p in dirs[0].iterdir() if not p.name.startswith(".")) == ["a.dbf", "a.shp", "a.shx"]
    assert not any((dirs[0] / files.DELETED_DIR).iterdir())


@pytest.mark.parametrize("kind,args,blocked", [
    ("parcel", {"areas": ["a.kmz"]}, True),
    ("parcel", {"areas": []}, True),               # ไม่เลือก = ใช้ทุกไฟล์
    ("parcel", {"areas": ["other.kmz"]}, False),
    ("cityplanning", {"area": "a.kmz"}, True),
    ("cityplanning", {"area": None}, False),
])
def test_delete_blocked_while_job_uses_area(client, dirs, monkeypatch, kind, args, blocked):
    (dirs[0] / "a.kmz").write_bytes(b"x")
    job = server.Job(id="j1", kind=kind, cmd=[], args=args, status="running")
    monkeypatch.setattr(server, "JOBS", {"j1": job})
    r = delete(client, "a.kmz")
    assert r.status_code == (409 if blocked else 200), r.text
    if blocked:
        assert r.json()["detail"]["busy"] == ["a.kmz"]
        assert (dirs[0] / "a.kmz").exists()


def test_delete_allowed_after_job_finished(client, dirs, monkeypatch):
    (dirs[0] / "a.kmz").write_bytes(b"x")
    job = server.Job(id="j1", kind="parcel", cmd=[], args={"areas": []}, status="done")
    monkeypatch.setattr(server, "JOBS", {"j1": job})
    assert delete(client, "a.kmz").status_code == 200


def test_delete_cross_origin_rejected(client, dirs):
    (dirs[0] / "a.kmz").write_bytes(b"x")
    r = client.post("/api/areas/delete", json={"names": ["a.kmz"]}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert (dirs[0] / "a.kmz").exists()


# ─────────────────────────── schema: ตรวจชื่อฟิลด์ก่อนบันทึก ───────────────────────────

@pytest.fixture
def schema_dir(tmp_path, monkeypatch):
    d = tmp_path / "schema"
    d.mkdir()
    for sec, fixed in (("parcel", ["Rai", "Owner_Name"]), ("cityplanning", ["PL_USE"])):
        (d / f"catalog_{sec}.json").write_text(json.dumps({"fixed_fields": fixed, "groups": []}), encoding="utf-8")
    monkeypatch.setattr(server, "SCHEMA_DIR", d)
    return d


def save_schema(client, parcel=(), city=()):
    body = {"parcel": {"extra_fields": [{"source": s, "name": n} for s, n in parcel]},
            "cityplanning": {"extra_fields": [{"source": s, "name": n} for s, n in city]}}
    return client.post("/api/user-schema", json=body)


def test_schema_save_ok_writes_file(client, schema_dir):
    r = save_schema(client, parcel=[("info.a", "Lat"), ("info.b", "Lon")], city=[("virtual.area_m2", "Lat")])
    assert r.status_code == 200, r.text
    saved = json.loads((schema_dir / "user_schema.json").read_text(encoding="utf-8"))
    assert [f["name"] for f in saved["parcel"]["extra_fields"]] == ["Lat", "Lon"]
    assert saved["cityplanning"]["extra_fields"][0]["name"] == "Lat"   # คนละ section ชื่อเดียวกันได้


@pytest.mark.parametrize("parcel,expect", [
    ([("info.a", "Lat"), ("info.b", "lat")], "ซ้ำกัน (info.a กับ info.b)"),
    ([("info.a", "RAI")], "ซ้ำกับฟิลด์มาตรฐาน Rai"),
    ([("info.a", "  ")], "info.a ยังไม่ได้ตั้งชื่อ"),
    ([("info.a", "ParcelNumber")], "เกิน 10 ตัวอักษร"),
])
def test_schema_save_rejects_bad_names(client, schema_dir, parcel, expect):
    r = save_schema(client, parcel=parcel)
    assert r.status_code == 400
    problems = r.json()["detail"]["problems"]
    assert any(expect in p for p in problems), problems
    assert not (schema_dir / "user_schema.json").exists()


def test_schema_problems_reports_every_issue():
    probs = server.schema_problems("parcel", [
        {"source": "a", "name": "X"}, {"source": "b", "name": "x"}, {"source": "c", "name": "Rai"}, {"bad": 1},
    ], ["Rai"])
    assert len(probs) == 3


# ─────────────────────────── 📖 คู่มือ ───────────────────────────

@pytest.fixture
def docs_root(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / "docs").mkdir(parents=True)
    (root / "README.md").write_text("# สารบัญ\n", encoding="utf-8")
    (root / "docs" / "parcel.md").write_text("# แปลงที่ดิน\nเนื้อหา", encoding="utf-8")
    (root / "docs" / "extra.md").write_text("ไม่มีหัวเรื่อง", encoding="utf-8")
    (root / "secret.md").write_text("ห้ามเห็น", encoding="utf-8")
    monkeypatch.setattr(docs, "ROOT", root)
    monkeypatch.setattr(docs, "DOCS_DIR", root / "docs")
    return root


def test_docs_list_ordered_with_titles(client, docs_root):
    items = client.get("/api/docs").json()["items"]
    assert items == [{"name": "index", "title": "สารบัญ"}, {"name": "parcel", "title": "แปลงที่ดิน"},
                     {"name": "extra", "title": "extra"}]


def test_docs_get_markdown(client, docs_root):
    r = client.get("/api/docs/parcel")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "เนื้อหา" in r.text
    assert client.get("/api/docs/index").text.startswith("# สารบัญ")


@pytest.mark.parametrize("name,status", [("secret", 404), ("..%2Fsecret", 404), ("Parcel", 400), ("a.b", 400)])
def test_docs_rejects_outside_or_bad_names(client, docs_root, name, status):
    r = client.get(f"/api/docs/{name}")
    assert r.status_code in (status, 404)
    assert "ห้ามเห็น" not in r.text
