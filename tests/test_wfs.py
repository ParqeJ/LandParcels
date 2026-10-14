import json

from shapely.geometry import box, mapping

from conftest import BOX_47
from landsmaps import wfs
from landsmaps.area import load_area


def feature(seq, geom, land_no="1"):
    return {"type": "Feature", "geometry": mapping(geom),
            "properties": {"parcel_seq": seq, "land_no": land_no}}


def test_sheet_code():
    assert wfs.sheet_code("5239 IV 2692-00") == "52394"
    assert wfs.sheet_code("5339 I") == "53391"
    assert wfs.sheet_code("garbage") is None


def test_clip_keeps_touching_parcels_once(area_file):
    area = load_area(area_file(BOX_47))
    inside = area.native.centroid.buffer(20)
    far = box(0, 0, 10, 10)
    out = wfs.clip([feature(1, inside), feature(1, inside), feature(2, far)], area)
    assert list(out["parcel_seq"]) == [1]
    assert out.crs.to_epsg() == 24047


def test_clip_empty_returns_empty_frame(area_file):
    out = wfs.clip([], load_area(area_file(BOX_47)))
    assert len(out) == 0 and "parcel_seq" in out.columns


def test_fetch_features_uses_cache_until_bbox_changes(area_file, tmp_path, monkeypatch):
    calls = []

    def fake_wfs_get(layer, bbox, **extra):
        calls.append(extra["viewparams"])
        return {"type": "FeatureCollection", "features": [feature(1, box(0, 0, 1, 1))]}

    monkeypatch.setattr(wfs, "wfs_get", fake_wfs_get)
    area = load_area(area_file(BOX_47))

    wfs.fetch_features("L", ["53394"], area, tmp_path, "parcel")
    wfs.fetch_features("L", ["53394"], area, tmp_path, "parcel")
    assert calls == ["utmmap:53394"]                    # ครั้งที่ 2 อ่านจาก cache

    cache = tmp_path / "parcel_53394_my_site.json"
    data = json.loads(cache.read_text())
    cache.write_text(json.dumps({**data, "_bbox": [0, 0, 1, 1]}))
    wfs.fetch_features("L", ["53394"], area, tmp_path, "parcel")
    assert len(calls) == 2                              # กรอบเปลี่ยน -> ดึงใหม่

    cache.write_text('{"type": "FeatureColl')            # ไฟล์เสีย -> ดึงใหม่ ไม่พัง
    wfs.fetch_features("L", ["53394"], area, tmp_path, "parcel")
    assert len(calls) == 3
    assert json.loads(cache.read_text())["features"]
