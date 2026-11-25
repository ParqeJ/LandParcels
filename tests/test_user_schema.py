"""ทดสอบการต่อ user_schema.json เข้ากับ pipeline (parcel + cityplanning)"""
import json

import geopandas as gpd
import pytest
from shapely.geometry import box

from landsmaps import config, user_schema
from landsmaps.cityplanning import export as city_export
from landsmaps.export import ns3k_record, parcel_record, to_shp_layout
from landsmaps.user_schema import Column
from landsmaps.zones import Zone

# catalog จริงในโปรเจกต์ (map source -> type)
PARCEL_CATALOG = config.SCHEMA_DIR / "catalog_parcel.json"
CITY_CATALOG = config.SCHEMA_DIR / "catalog_cityplanning.json"

INFO = {
    "parcel_seq": "123", "parcel_type": "น.ส.3ก", "utm": "5339 IV 7808-00 (4000)",
    "parcelno": "xxxx19", "rai": "3", "ngan": "2", "wa": "71", "subwa": "9",
    "provname": "ชัยภูมิ", "lands_status": {"obligation": "จำนอง", "freeze": None},
}

# config ที่ผู้ใช้ตั้ง: base (เปลี่ยนชื่อ Remark -> Note) + addon 2 + extra 2
PARCEL_CFG = {
    "base_fields": [
        {"field": "Plang", "name": "Plang"},
        {"field": "Rai", "name": "Rai"},
        {"field": "Remark", "name": "Note"},
    ],
    "addon_fields": [{"name": "Owner", "type": "str"}, {"name": "Cost", "type": "int"}],
    "extra_fields": [
        {"source": "info.provname", "name": "Province"},
        {"source": "virtual.area_m2", "name": "AreaM2"},
    ],
}


def _catalog(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_user_schema(tmp_path, data):
    p = tmp_path / "user_schema.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


# ─────────────────────── build_parcel_layout ───────────────────────

def test_layout_none_when_no_base_fields():
    """รูปแบบเดิม (ไม่มี base_fields) = preset เดิม -> None"""
    assert user_schema.build_parcel_layout({"extra_fields": []}, _catalog(PARCEL_CATALOG)) is None
    assert user_schema.build_parcel_layout(None, {}) is None


def test_layout_columns_order_and_remark_name():
    layout = user_schema.build_parcel_layout(PARCEL_CFG, _catalog(PARCEL_CATALOG))
    assert [c.name for c in layout.columns] == ["Plang", "Rai", "Note", "Owner", "Cost", "Province", "AreaM2"]
    assert [c.kind for c in layout.columns] == ["base", "base", "base", "addon", "addon", "extra", "extra"]
    assert layout.remark_name == "Note"                 # Remark ถูกเปลี่ยนชื่อ -> pipeline ยังนับแปลงค้างได้


def test_layout_none_on_duplicate_names():
    cfg = {"base_fields": [{"field": "Rai", "name": "X"}],
           "addon_fields": [{"name": "x", "type": "str"}]}   # 'Rai'->X ชนกับ addon 'x' (DBF ไม่แยกเคส)
    assert user_schema.build_parcel_layout(cfg, _catalog(PARCEL_CATALOG)) is None


# ─────────────────────── resolve / cast ───────────────────────

def test_resolve_parcel_sources():
    rec = parcel_record("123", "45", {"123": INFO})
    assert user_schema.resolve_parcel("wfs.land_no", rec) == "45"
    assert user_schema.resolve_parcel("info.parcelno", rec) == "xxxx19"
    assert user_schema.resolve_parcel("info.parcel_type", rec) == "น.ส.3ก"
    assert user_schema.resolve_parcel("virtual.rawang_short", rec) == "5339 IV 7808-00"
    assert user_schema.resolve_parcel("virtual.wa_total", rec) == pytest.approx(71.9)
    assert user_schema.resolve_parcel("virtual.area_m2", rec) == pytest.approx(5887.6)
    assert user_schema.resolve_parcel("info.lands_status.obligation", rec) == "จำนอง"
    assert user_schema.resolve_parcel("system", rec) == ""


def test_resolve_parcel_type_fallback_when_no_detail():
    """แปลงยังไม่มีรายละเอียด -> Type ใช้ค่า default, wa_total ว่าง (ไม่ใช่ 0)"""
    rec = parcel_record("123", "45", {})                # pending
    assert user_schema.resolve_parcel("info.parcel_type", rec) == "โฉนดที่ดิน"
    assert user_schema.resolve_parcel("virtual.wa_total", rec) is None
    assert user_schema.resolve_parcel("info.rai", rec) is None


def test_cast_types():
    assert user_schema.cast("3", "int") == 3
    assert user_schema.cast("71.9", "float") == pytest.approx(71.9)
    assert user_schema.cast(5, "str") == "5"
    assert user_schema.cast("", "str") == ""
    assert user_schema.cast(None, "int") is None
    assert user_schema.cast("", "float") is None
    assert user_schema.cast({"a": 1}, "str") == '{"a": 1}'


# ─────────────────────── project_parcel ───────────────────────

def test_project_parcel_base_addon_extra():
    layout = user_schema.build_parcel_layout(PARCEL_CFG, _catalog(PARCEL_CATALOG))
    row = user_schema.project_parcel(parcel_record("123", "45", {"123": INFO}), layout)
    assert row == {"Plang": "45", "Rai": 3, "Note": "", "Owner": "", "Cost": None,
                   "Province": "ชัยภูมิ", "AreaM2": pytest.approx(5887.6)}


def test_project_ns3k_record_is_mostly_empty():
    layout = user_schema.build_parcel_layout(PARCEL_CFG, _catalog(PARCEL_CATALOG))
    row = user_schema.project_parcel(ns3k_record("77"), layout)
    assert row["Plang"] == "77" and row["Province"] == "" and row["AreaM2"] is None


# ─────────────────────── to_shp_layout roundtrip ───────────────────────

def test_to_shp_layout_roundtrip(tmp_path):
    layout = user_schema.build_parcel_layout(PARCEL_CFG, _catalog(PARCEL_CATALOG))
    rows = [user_schema.project_parcel(parcel_record("123", "45", {"123": INFO}), layout)]
    path = tmp_path / "out" / "x.shp"
    to_shp_layout(rows, [box(0, 0, 10, 10)], 24047, path, layout)
    back = gpd.read_file(path)
    assert list(back.columns) == [c.name for c in layout.columns] + ["geometry"]
    assert back.loc[0, "Province"] == "ชัยภูมิ"
    assert back.loc[0, "Rai"] == 3
    assert back.crs.to_epsg() == 24047


# ─────────────────────── load จากไฟล์จริง (tmp) ───────────────────────

def test_load_parcel_layout_from_file(tmp_path):
    schema_file = _write_user_schema(tmp_path, {"parcel": PARCEL_CFG, "cityplanning": {"extra_fields": []}})
    layout = user_schema.load_parcel_layout(schema_file, PARCEL_CATALOG)
    assert layout is not None and layout.remark_name == "Note"


def test_load_parcel_layout_missing_file_returns_none(tmp_path):
    assert user_schema.load_parcel_layout(tmp_path / "nope.json", PARCEL_CATALOG) is None


# ─────────────────────── cityplanning extras ───────────────────────

def test_load_city_extras_and_skip_fixed_collision(tmp_path):
    cfg = {"parcel": {"extra_fields": []}, "cityplanning": {"extra_fields": [
        {"source": "props.NAME", "name": "PlanRaw"},
        {"source": "virtual.area_m2", "name": "AreaM2"},
        {"source": "props.PL_USE", "name": "PL_USE"},   # ชนฟิลด์ล็อก -> ต้องถูกข้าม
    ]}}
    schema_file = _write_user_schema(tmp_path, cfg)
    cols = user_schema.load_city_extras(schema_file, CITY_CATALOG)
    assert [c.name for c in cols] == ["PlanRaw", "AreaM2"]


def test_resolve_city_sources():
    props = {"NAME": "ผังเมืองรวม", "PL_USE": 1110}
    assert user_schema.resolve_city("props.NAME", props, 1600.0, "x", "#fff") == "ผังเมืองรวม"
    assert user_schema.resolve_city("virtual.area_rai", props, 1600.0, "x", "#fff") == 1.0
    assert user_schema.resolve_city("virtual.area_m2", props, 1600.0, "x", "#fff") == 1600.0
    assert user_schema.resolve_city("virtual.zone_hex", props, 1600.0, "x", "#fff") == "#fff"


def _city_feature():
    return {
        "type": "Feature",
        "properties": {"PL_USE": 1110, "NAME": "ผังทดสอบ", "YEAR": "2560"},
        "geometry": {"type": "Polygon", "coordinates": [[
            [101.50, 15.40], [101.51, 15.40], [101.51, 15.41], [101.50, 15.41], [101.50, 15.40]]]},
    }


def test_city_build_appends_extra_columns():
    extras = (Column("PlanRaw", "props.NAME", "str", "extra"),
              Column("AreaM2", "virtual.area_m2", "float", "extra"))
    gdf = city_export.build([_city_feature()], Zone(47), "นครสวรรค์", "L", extras=extras)
    assert list(gdf.columns) == city_export.FIELDS + ["PlanRaw", "AreaM2", "geometry"]
    assert gdf.iloc[0]["PlanRaw"] == "ผังทดสอบ"
    assert gdf.iloc[0]["AreaM2"] > 0


def test_city_build_no_extras_keeps_12_fields():
    gdf = city_export.build([_city_feature()], Zone(47), "x", "L", extras=())
    assert list(gdf.columns) == city_export.FIELDS + ["geometry"]


# ─────────────────── cityplanning layout (ปลดล็อก 12 ฟิลด์: ติ๊กออก/เปลี่ยนชื่อ) ───────────────────

def test_load_city_layout_default_preset(tmp_path):
    """ไม่มี base_fields = preset 12 ฟิลด์เดิม ชื่อเดิมครบ (merge ปลอดภัย)"""
    schema_file = _write_user_schema(tmp_path, {"cityplanning": {"extra_fields": []}})
    layout = user_schema.load_city_layout(schema_file, CITY_CATALOG)
    assert [c.name for c in layout.base] == list(user_schema.CITY_BASE_FIELDS)
    assert all(c.source == c.name for c in layout.base)      # preset: source=field=ชื่อเดิม
    assert layout.extras == ()


def test_load_city_layout_missing_file_is_preset():
    layout = user_schema.load_city_layout(config.SCHEMA_DIR / "nope.json", CITY_CATALOG)
    assert [c.name for c in layout.base] == list(user_schema.CITY_BASE_FIELDS)


def test_load_city_layout_rename_and_exclude(tmp_path):
    cfg = {"cityplanning": {"base_fields": [
        {"field": "PL_USE", "name": "LandUse"}, {"field": "YEAR", "name": "Year"}],
        "extra_fields": [{"source": "props.NAME", "name": "PlanRaw"}]}}
    schema_file = _write_user_schema(tmp_path, cfg)
    layout = user_schema.load_city_layout(schema_file, CITY_CATALOG)
    assert [(c.name, c.source, c.type) for c in layout.base] == [
        ("LandUse", "PL_USE", "int"), ("Year", "YEAR", "str")]
    assert [c.name for c in layout.extras] == ["PlanRaw"]


def test_load_city_layout_extra_skips_base_name_collision(tmp_path):
    """extra ชนชื่อ base ที่เลือก (ตั้งใหม่) -> ถูกข้าม"""
    cfg = {"cityplanning": {"base_fields": [{"field": "PL_USE", "name": "Zone"}],
           "extra_fields": [{"source": "props.NAME", "name": "Zone"}]}}
    schema_file = _write_user_schema(tmp_path, cfg)
    layout = user_schema.load_city_layout(schema_file, CITY_CATALOG)
    assert [c.name for c in layout.base] == ["Zone"] and layout.extras == ()


def test_load_city_layout_bad_falls_back_to_preset(tmp_path):
    """ชื่อ base ซ้ำกัน = ตั้งค่าเสีย -> คง preset 12 ฟิลด์ (ไม่ทำรอบดึงพัง)"""
    cfg = {"cityplanning": {"base_fields": [
        {"field": "PL_USE", "name": "Dup"}, {"field": "YEAR", "name": "Dup"}]}}
    schema_file = _write_user_schema(tmp_path, cfg)
    layout = user_schema.load_city_layout(schema_file, CITY_CATALOG)
    assert [c.name for c in layout.base] == list(user_schema.CITY_BASE_FIELDS)


def test_city_build_with_layout_renames_and_excludes():
    layout = user_schema.CityLayout(
        base=(Column("LandUse", "PL_USE", "int", "base"), Column("Yr", "YEAR", "str", "base")),
        extras=(Column("PlanRaw", "props.NAME", "str", "extra"),))
    gdf = city_export.build([_city_feature()], Zone(47), "นครสวรรค์", "L", layout=layout)
    assert list(gdf.columns) == ["LandUse", "Yr", "PlanRaw", "geometry"]
    assert gdf.iloc[0]["LandUse"] == 1110
    assert gdf.iloc[0]["Yr"] == "2560"
    assert gdf.iloc[0]["PlanRaw"] == "ผังทดสอบ"
