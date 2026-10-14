"""UTM zone 47/48 ของประเทศไทย: ชื่อ layer WFS, EPSG และการแปลงพิกัดแบบที่กรมที่ดินใช้"""

from dataclasses import dataclass
from functools import lru_cache

from pyproj import Transformer

ZONE_SPLIT_LON = 102.0      # ลองจิจูด < 102°E = zone 47, ตั้งแต่ 102°E = zone 48


@dataclass(frozen=True)
class Zone:
    number: int

    @property
    def epsg(self) -> int:
        return 24000 + self.number      # Indian 1975 / UTM 47N = 24047, 48N = 24048

    @property
    def parcel_layer(self) -> str:
        return f"V_PARCEL{self.number}_LANDNO"

    @property
    def ns3k_layer(self) -> str:
        return f"map_ns3k_{self.number}_LANDNO"

    @property
    def index_layers(self) -> list[str]:
        n = self.number
        return [f"V_INDEX4000_{n}_LANDNO", f"V_INDEX2000_{n}", f"V_INDEX1000_{n}"]

    @property
    def transformer(self) -> Transformer:
        """lon/lat (WGS84) -> EPSG:240xx ใช้ direction="INVERSE" เพื่อแปลงกลับ"""
        return _transformer(self.number)


@lru_cache(maxsize=None)
def _transformer(zone: int) -> Transformer:
    # แบบเดียวกับที่ GeoServer กรมที่ดินใช้ (Indian1975 -> WGS84 (2)) ซ้อนกับ WMS กรมที่ดินได้ตรง
    pipe = ("+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad "
            "+step +proj=push +v_3 +step +proj=cart +ellps=WGS84 "
            "+step +inv +proj=helmert +x=210 +y=814 +z=289 "
            "+step +inv +proj=cart +ellps=evrst30 +step +proj=pop +v_3 "
            f"+step +proj=utm +zone={zone} +ellps=evrst30")
    return Transformer.from_pipeline(pipe)


def zone_for_lon(lon: float) -> Zone:
    return Zone(47 if lon < ZONE_SPLIT_LON else 48)
