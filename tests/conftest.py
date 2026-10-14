import sys
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# กรอบเล็ก ๆ ใน zone 47 (101.5°E) และ zone 48 (104.8°E)
BOX_47 = box(101.50, 15.40, 101.51, 15.41)
BOX_48 = box(104.80, 15.20, 104.81, 15.21)


@pytest.fixture
def area_file(tmp_path):
    def make(geom=BOX_47, name="My Site.geojson", crs=4326):
        path = tmp_path / name
        gpd.GeoDataFrame(geometry=[geom], crs=crs).to_file(path)
        return path
    return make
