"""เทสต์ offline ของ Feature ผังเมือง (ไม่ยิง network จริง)"""

import pytest

from landsmaps.cityplanning import legend, provinces
from landsmaps.cityplanning import export, service
from landsmaps.cityplanning.service import LayerRef, ServiceError, ServiceInfo
from landsmaps.zones import Zone


# ───────────────────────────── provinces ─────────────────────────────

@pytest.mark.parametrize("value, code, name", [
    ("37", "37", "อำนาจเจริญ"),
    (60, "60", "นครสวรรค์"),
    ("อำนาจเจริญ", "37", "อำนาจเจริญ"),
    ("จังหวัดนครสวรรค์", "60", "นครสวรรค์"),
    ("กทม", "10", "กรุงเทพมหานคร"),
])
def test_resolve_province(value, code, name):
    prov = provinces.resolve(value)
    assert prov.code == code and prov.name == name
    assert prov.service_name == f"PLLU{code}"


def test_resolve_province_unknown_raises():
    with pytest.raises(ValueError):
        provinces.resolve("ไม่มีจังหวัดนี้")


def test_all_provinces_count():
    assert len(provinces.all_provinces()) == 77


# ───────────────────────────── legend ─────────────────────────────

def test_legend_known_code():
    assert legend.label_for("1110") == "ที่อยู่อาศัยหนาแน่นน้อย"
    assert legend.color_for(1110) == "#ffff00"


def test_legend_unknown_code_has_defaults():
    assert legend.label_for("0000") == legend.UNKNOWN_LABEL
    assert legend.color_for(None) == legend.DEFAULT_COLOR


def test_legend_merge_renderer_adds_new_class():
    try:
        legend.merge_renderer([
            {"value": "9998", "label": "9998 เขตทดสอบ",
             "symbol": {"color": [1, 2, 3, 255]}},
        ])
        assert legend.label_for("9998") == "เขตทดสอบ"
        assert legend.color_for("9998") == "#010203"
    finally:
        legend._table.cache_clear()     # กันค่าทดสอบรั่วไปเทสต์อื่น


# ───────────────────────────── service / ServiceInfo ─────────────────────────────

def _info() -> ServiceInfo:
    return ServiceInfo("60", 32647, 47, [
        LayerRef(0, "PLLU_6012100"), LayerRef(10, "PLLU_6000000"),
        LayerRef(11, "COMP_BND60"),
    ])


def test_master_layer_picks_all_zeros_plan():
    assert _info().master_layer().name == "PLLU_6000000"


def test_resolve_layer_by_id_and_name():
    info = _info()
    assert info.resolve_layer(0).name == "PLLU_6012100"
    assert info.resolve_layer("PLLU_6000000").id == 10
    assert info.resolve_layer(None).id == 10      # None = ชั้นผังรวม


def test_resolve_layer_unknown_raises():
    with pytest.raises(ServiceError):
        _info().resolve_layer(99)


def test_resolve_token_env_wins(monkeypatch):
    monkeypatch.setenv(service.TOKEN_ENV, " envtok ")
    assert service.resolve_token("argtok") == "envtok"


def test_resolve_token_explicit_then_none(monkeypatch):
    monkeypatch.delenv(service.TOKEN_ENV, raising=False)
    assert service.resolve_token("argtok") == "argtok"
    assert service.resolve_token() is None


@pytest.mark.parametrize("lon, wkid_store, expected_zone", [
    (101.9, 32647, 47),     # ชัยภูมิ ฝั่งตะวันตกของเส้นแบ่ง -> zone 47
    (104.6, 32648, 48),     # อุบลฯ ฝั่งตะวันออก -> zone 48
    (101.9, 3857, 47),      # จังหวัดที่ service เก็บเป็น Web Mercator ก็ต้องได้ zone ถูก
    (104.6, 3857, 48),
])
def test_zone_from_extent_handles_mercator_and_utm(lon, wkid_store, expected_zone):
    from pyproj import Transformer
    lat = 15.8
    if wkid_store == 3857:
        x, y = Transformer.from_crs(4326, 3857, always_xy=True).transform(lon, lat)
    else:
        x, y = Transformer.from_crs(4326, wkid_store, always_xy=True).transform(lon, lat)
    extent = {"xmin": x - 1000, "ymin": y - 1000, "xmax": x + 1000, "ymax": y + 1000,
              "spatialReference": {"latestWkid": wkid_store}}
    assert service._zone_from_extent(extent, wkid_store) == expected_zone


def test_envelope_params():
    assert service._envelope_params(None) == {}
    p = service._envelope_params((101.5, 15.4, 101.6, 15.5))
    assert p["geometryType"] == "esriGeometryEnvelope" and p["inSR"] == "4326"
    assert p["geometry"].startswith("101.5")


# ───────────────────────────── export ─────────────────────────────

def test_to_2d_strips_z_and_m():
    ring = [[101.5, 15.4, 0, 0], [101.6, 15.4, 0, 0]]
    assert export._to_2d(ring) == [[101.5, 15.4], [101.6, 15.4]]


def _feature():
    return {
        "type": "Feature",
        "properties": {"PL_USE": 1110, "NAME": "ผังทดสอบ", "YEAR": "2560",
                       "PL_FAR_MAX": 5.0, "PL_BCR_MAX": 0.8, "PL_DENS_H": 10, "PL_DENS_L": 5},
        "geometry": {"type": "Polygon", "coordinates": [[
            [101.50, 15.40, 0, 0], [101.51, 15.40, 0, 0], [101.51, 15.41, 0, 0],
            [101.50, 15.41, 0, 0], [101.50, 15.40, 0, 0]]]},
    }


def test_build_geodataframe_reprojects_and_maps_attributes():
    gdf = export.build([_feature()], Zone(47), "นครสวรรค์", "PLLU_6000000")
    assert len(gdf) == 1
    assert gdf.crs.to_epsg() == 24047
    row = gdf.iloc[0]
    assert row["PL_USE"] == 1110
    assert row["PL_USE_TH"] == "ที่อยู่อาศัยหนาแน่นน้อย"
    assert row["ZONE_HEX"] == "#ffff00"
    assert row["PROVINCE"] == "นครสวรรค์" and row["YEAR"] == "2560"
    assert row["AREA_RAI"] > 0                 # ~0.01° x 0.01° ≈ 740 ไร่
    assert list(gdf.columns) == export.FIELDS + ["geometry"]


def test_build_skips_empty_geometry():
    bad = {"type": "Feature", "properties": {"PL_USE": 1110}, "geometry": None}
    assert len(export.build([bad], Zone(47), "x", "L")) == 0
