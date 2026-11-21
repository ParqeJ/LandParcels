"""ไคลเอนต์ ArcGIS REST ของ service ผังเมือง (LandusePlan/PLLU{จังหวัด}) ของกรมที่ดิน

ข้อมูลผังเมืองรวมเป็นข้อมูลเปิดที่เว็บ LandsMaps แสดงให้ดูได้ บางจังหวัด (เช่น นครสวรรค์/60)
เรียก REST ได้ตรง ๆ โดยไม่ต้อง token ส่วนจังหวัดอื่น service ต้องแนบ ArcGIS token
ซึ่ง "ผู้ใช้เป็นผู้จัดหาเอง" ผ่าน env ``LANDSMAPS_ARCGIS_TOKEN`` หรือ ``--token``
(โปรแกรมไม่ไปหยิบ token ของระบบกรมที่ดินมาใช้แทนผู้ใช้)

การดึงข้อมูลเลี่ยง 2 ข้อจำกัดของเซิร์ฟเวอร์:
  1. WAF บล็อก query ที่หน้าตาเหมือน SQL injection (เช่น where=1=1) -> ใช้ where=PL_USE>=0
  2. service นี้ไม่รองรับ pagination -> ขอ objectId ทั้งหมดก่อน (returnIdsOnly) แล้วดึงเป็นชุด ๆ
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import requests
from pyproj import Transformer

from ..zones import zone_for_lon

BASE_URL = "https://landsmaps.dol.go.th/arcgis/rest/services/LandusePlan"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://landsmaps.dol.go.th/"}
TIMEOUT = 120
OID_CHUNK = 200                 # จำนวน objectId ต่อ 1 คำขอ (คุม URL ของ GET ไม่ให้ยาวเกิน)
TOKEN_ENV = "LANDSMAPS_ARCGIS_TOKEN"
WHERE_ALL = "PL_USE>=0"         # where ที่ครอบทุกแปลงและผ่าน WAF (เลี่ยง 1=1)
RETRY_WAITS = (3, 8, 20)        # หน่วง (วินาที) ก่อนลองใหม่ เมื่อเซิร์ฟเวอร์ตอบ 5xx/429 ชั่วคราว
RETRY_STATUS = {429, 500, 502, 503, 504}


class ServiceError(RuntimeError):
    """service คืน error หรือถูก WAF บล็อก"""


class TokenRequired(ServiceError):
    """service ต้องใช้ ArcGIS token แต่ไม่ได้แนบมา (หรือ token หมดอายุ)"""


class CapabilityNotSupported(ServiceError):
    """service ไม่เปิด operation นี้ (เช่น ขาด capability 'Data' -> /query ใช้ไม่ได้)"""


@dataclass(frozen=True)
class LayerRef:
    id: int
    name: str


@dataclass(frozen=True)
class ServiceInfo:
    province_code: str
    wkid: int
    zone: int                   # 47 หรือ 48 (จาก wkid ของ service)
    layers: list[LayerRef]
    capabilities: tuple[str, ...] = ()          # เช่น ("Map", "Query", "Data")
    max_record_count: int = 1000                # เพดานจำนวนรูปต่อคำขอของ service
    extent: tuple[float, float, float, float] | None = None    # fullExtent (xmin, ymin, xmax, ymax)
    extent_wkid: int = 0                        # CRS ของ extent

    @property
    def supports_data_query(self) -> bool:
        """/query ระดับชั้นต้องมี capability 'Data' (ไม่รู้ capability = ถือว่าลองได้)"""
        return not self.capabilities or "Data" in self.capabilities

    def master_layer(self) -> LayerRef:
        """ชั้น 'ผังรวมทั้งจังหวัด' = PLLU_{จังหวัด}00000 (ส่วนผังย่อยลงท้ายด้วยเลขอื่น)"""
        master = f"PLLU_{self.province_code}00000"
        for lyr in self.layers:
            if lyr.name == master:
                return lyr
        pllu = [l for l in self.layers if l.name.upper().startswith("PLLU_")]
        if pllu:
            return pllu[0]
        raise ServiceError(
            f"ไม่พบชั้นผังเมือง (PLLU_*) ใน PLLU{self.province_code} "
            f"มีชั้น: {', '.join(l.name for l in self.layers)}"
        )

    def resolve_layer(self, selector: str | int | None) -> LayerRef:
        if selector is None:
            return self.master_layer()
        key = str(selector).strip()
        for lyr in self.layers:
            if str(lyr.id) == key or lyr.name == key:
                return lyr
        raise ServiceError(f"ไม่พบชั้น '{selector}' -> ดูชั้นทั้งหมดด้วย --list-layers")


def service_url(province_code: str) -> str:
    return f"{BASE_URL}/PLLU{province_code}/MapServer"


# ───────────────────────────── token ─────────────────────────────

def resolve_token(explicit: str | None = None) -> str | None:
    """ArcGIS token ของผู้ใช้: ENV LANDSMAPS_ARCGIS_TOKEN ก่อน แล้วค่อยค่าที่ส่งมาทาง --token

    ไม่มี token = เรียกได้เฉพาะจังหวัดที่ service เปิดสาธารณะ
    """
    env = os.environ.get(TOKEN_ENV)
    if env:
        return env.strip()
    if explicit:
        return explicit.strip()
    return None


# ───────────────────────────── HTTP ─────────────────────────────

def _params(token: str | None, **extra) -> dict:
    params = {"f": "json", **extra}
    if token:
        params["token"] = token
    return params


def _get(url: str, params: dict) -> requests.Response:
    """GET พร้อมลองใหม่เมื่อเจอ 5xx/429 ชั่วคราวหรือเน็ตสะดุด"""
    last: Exception | None = None
    for attempt in range(len(RETRY_WAITS) + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code in RETRY_STATUS and attempt < len(RETRY_WAITS):
                time.sleep(RETRY_WAITS[attempt])
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            if attempt < len(RETRY_WAITS):
                time.sleep(RETRY_WAITS[attempt])
                continue
            raise ServiceError(f"ติดต่อ service ผังเมืองไม่ได้: {e}") from e
    raise ServiceError(f"ติดต่อ service ผังเมืองไม่ได้: {last}")


def _request(url: str, params: dict) -> dict:
    r = _get(url, params)
    # f=geojson ตอบ content-type: text/plain ไม่บอก charset -> requests เดาเป็น ISO-8859-1
    # ทำให้ภาษาไทย (เช่น ชื่อผัง NAME) เพี้ยน; ArcGIS REST ส่ง UTF-8 เสมอ จึงบังคับ UTF-8
    r.encoding = "utf-8"
    text = r.text.lstrip()
    if text[:5].upper() == "<HTML" or "Unauthorized Request Blocked" in text:
        raise ServiceError("ถูก WAF ของกรมที่ดินบล็อก (คำขอหน้าตาผิดปกติ) -> ลองใหม่/ลดขนาดพื้นที่")
    try:
        data = r.json()
    except ValueError as e:
        raise ServiceError(f"service คืนค่าที่ไม่ใช่ JSON: {text[:120]}") from e

    err = data.get("error") if isinstance(data, dict) else None
    if err:
        msg = err.get("message") or ""
        details = " ".join(str(d) for d in err.get("details") or [])
        if "Token Required" in msg or err.get("code") in (403, 499):
            raise TokenRequired(msg or "ต้องใช้ ArcGIS token")
        text = f"service error {err.get('code')}: {msg} {details}".strip()
        if "capability is not supported" in details or "operation is not supported" in msg:
            raise CapabilityNotSupported(text)
        raise ServiceError(text)
    return data


# ───────────────────────────── metadata ─────────────────────────────

def _lon_from_point(x: float, y: float, wkid: int) -> float:
    """แปลงจุดใน CRS ของ service (wkid) -> ลองจิจูด (องศา) เพื่อใช้เลือก zone 47/48"""
    if wkid in (4326, 0):
        return x
    return Transformer.from_crs(wkid, 4326, always_xy=True).transform(x, y)[0]


def _zone_from_extent(full_extent: dict, service_wkid: int) -> int:
    """เลือก zone 47/48 จากลองจิจูดกลางของ fullExtent (รองรับทั้ง 32647/32648/3857)

    service รายจังหวัดเก็บได้หลาย CRS (บางจังหวัดเป็น Web Mercator 3857) แต่ GeoJSON
    คืนพิกัดเป็น 4326 เสมอ -> ใช้ตำแหน่งจริงของข้อมูลเลือก zone ไม่ใช่ตัวเลข wkid
    """
    sr = full_extent.get("spatialReference") or {}
    wkid = sr.get("latestWkid") or sr.get("wkid") or service_wkid
    cx = (full_extent["xmin"] + full_extent["xmax"]) / 2
    cy = (full_extent["ymin"] + full_extent["ymax"]) / 2
    return zone_for_lon(_lon_from_point(cx, cy, wkid)).number


def get_service(province_code: str, token: str | None) -> ServiceInfo:
    url = service_url(province_code)
    data = _request(url, _params(token))
    sr = data.get("spatialReference") or {}
    wkid = sr.get("latestWkid") or sr.get("wkid") or 0
    full_extent = data.get("fullExtent") or {}
    if not all(k in full_extent for k in ("xmin", "ymin", "xmax", "ymax")):
        raise ServiceError(
            f"service PLLU{province_code} ไม่มี fullExtent ที่ใช้ระบุ zone ได้ -> แจ้งผู้พัฒนา")
    zone = _zone_from_extent(full_extent, wkid)
    layers = [LayerRef(l["id"], l["name"]) for l in data.get("layers", [])]
    caps = tuple(c.strip() for c in (data.get("capabilities") or "").split(",") if c.strip())
    ext_sr = full_extent.get("spatialReference") or {}
    return ServiceInfo(
        province_code, wkid, zone, layers,
        capabilities=caps,
        max_record_count=int(data.get("maxRecordCount") or 1000),
        extent=tuple(float(full_extent[k]) for k in ("xmin", "ymin", "xmax", "ymax")),
        extent_wkid=int(ext_sr.get("latestWkid") or ext_sr.get("wkid") or wkid),
    )


def get_renderer(layer_url: str, token: str | None) -> list[dict]:
    """uniqueValueInfos ของชั้น (ใช้ merge legend) — ไม่มี ก็คืน list ว่าง"""
    try:
        data = _request(layer_url, _params(token))
    except ServiceError:
        return []
    return (((data.get("drawingInfo") or {}).get("renderer") or {}).get("uniqueValueInfos")) or []


# ───────────────────────────── query features ─────────────────────────────

def _query_url(layer_url: str) -> str:
    return f"{layer_url}/query"


def _envelope_params(envelope: tuple | None) -> dict:
    """envelope = (xmin, ymin, xmax, ymax) ใน lon/lat (WGS84) -> พารามิเตอร์ตัดด้วยกรอบ"""
    if not envelope:
        return {}
    return {
        "geometry": "{:.6f},{:.6f},{:.6f},{:.6f}".format(*envelope),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
    }


def count_features(layer_url: str, token: str | None, *, envelope: tuple | None = None) -> int:
    params = _params(token, where=WHERE_ALL, returnCountOnly="true", **_envelope_params(envelope))
    return int(_request(_query_url(layer_url), params).get("count", 0))


def all_object_ids(layer_url: str, token: str | None, *, envelope: tuple | None = None) -> list[int]:
    """objectId ทั้งหมดที่เข้าเงื่อนไข (ไม่ติด maxRecordCount) สำหรับดึงเป็นชุด ๆ ต่อ"""
    params = _params(token, where=WHERE_ALL, returnIdsOnly="true", **_envelope_params(envelope))
    data = _request(_query_url(layer_url), params)
    return [int(i) for i in (data.get("objectIds") or [])]


def fetch_features(layer_url: str, token: str | None, object_ids: list[int],
                   *, chunk: int = OID_CHUNK) -> list[dict]:
    """ดึง feature (GeoJSON) ตาม objectId ทีละชุด

    ใช้ GET (เซิร์ฟเวอร์กรมที่ดินบล็อก POST ไปที่ /query ด้วยรหัส 555) จึงคุมขนาดชุดด้วย OID_CHUNK
    GeoJSON ของ ArcGIS คืนพิกัดใน EPSG:4326 เสมอ (reproject เป็นเมตรในขั้น export)
    """
    features: list[dict] = []
    for start in range(0, len(object_ids), chunk):
        ids = ",".join(str(i) for i in object_ids[start:start + chunk])
        params = {"objectIds": ids, "outFields": "*", "returnGeometry": "true",
                  "outSR": "4326", "f": "geojson"}
        if token:
            params["token"] = token
        data = _request(_query_url(layer_url), params)
        features.extend(data.get("features") or [])
    return features
