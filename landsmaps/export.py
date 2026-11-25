"""แปลงผล LandsMaps เป็นแถว 14 attributes แล้วบันทึก Shapefile"""

from pathlib import Path

import geopandas as gpd
import pandas as pd

from .config import FIELDS

DEED = "โฉนดที่ดิน"
NS3K = "น.ส.3ก"
REMARK_PENDING = "ยังไม่ได้ดึงรายละเอียด"
REMARK_NOT_FOUND = "ไม่พบรายละเอียดใน LandsMaps"
REMARK_MISMATCH = "ตำแหน่งชี้ไปแปลงอื่น"
REMARK_COVERED = "ถูกแปลงอื่นทับทั้งหมด"
SHP_PARTS = (".shp", ".shx", ".dbf", ".prj", ".cpg")


def rawang(utm: str | None) -> str:
    return (utm or "").split(" (")[0]          # "5339 IV 7808-00 (4000)" -> "5339 IV 7808-00"


def status(info: dict) -> str:
    st = info.get("lands_status") or {}
    return ", ".join(f"{k}:{v}" for k, v in st.items() if v)


def empty_row(land_no, type_land: str, remark: str) -> dict:
    row = {f: "" for f in FIELDS}
    row.update({"Type_land": type_land, "Plang": land_no or "", "Remark": remark,
                "Rai": None, "Ngan": None, "Wa": None})
    return row


def detail_row(land_no, info: dict, cert_no: str) -> dict:
    row = empty_row(land_no, info.get("parcel_type") or "", "")
    row.update({
        "Rawang": rawang(info.get("utm")),
        "Cert_No": cert_no,
        "Rai": int(info.get("rai") or 0),
        "Ngan": int(info.get("ngan") or 0),
        "Wa": float(info.get("wa") or 0) + float(info.get("subwa") or 0) / 10,
        "Status": status(info),
    })
    return row


def classify(parcel_seq, land_no, details: dict, covered: bool = False) -> tuple[dict | None, str]:
    """แยกแยะแปลง -> (info ที่ใช้ได้, remark); info เป็น None = ไม่มีรายละเอียดใช้ได้ (remark บอกสาเหตุ)
    covered = แปลงนี้ถูกแปลงอื่นทับทั้งใบ ยิงพิกัดไปตรงไหนก็ได้รายละเอียดของแปลงอื่น"""
    key = str(parcel_seq)
    if key not in details:
        return None, REMARK_PENDING
    info = details[key]
    if not info:
        return None, REMARK_NOT_FOUND
    if str(info.get("parcel_seq")) != key:
        return None, (REMARK_COVERED if covered else REMARK_MISMATCH)
    return info, ""


def parcel_row(parcel_seq, land_no, details: dict, covered: bool = False) -> dict:
    info, remark = classify(parcel_seq, land_no, details, covered)
    if info is None:
        return empty_row(land_no, DEED, remark)
    return detail_row(land_no, info, info.get("parcelno") or "")


def parcel_record(parcel_seq, land_no, details: dict, covered: bool = False) -> dict:
    """ข้อมูลดิบ 1 แปลงไว้ map ตาม user_schema (ดู landsmaps/user_schema.project_parcel)"""
    info, remark = classify(parcel_seq, land_no, details, covered)
    return {"seq": str(parcel_seq), "land_no": land_no or "", "info": info or {},
            "remark": remark, "type_default": DEED}


def ns3k_record(land_no) -> dict:
    """น.ส.3ก มีแค่รูปแปลง + เลขที่ดิน (ไม่มีรายละเอียดราย API)"""
    return {"seq": "", "land_no": land_no or "", "info": {}, "remark": "", "type_default": NS3K}


def _write_shp(rows: list, geometries, crs, path: Path, columns: list,
               int_cols: tuple = (), float_cols: tuple = ()) -> gpd.GeoDataFrame:
    """สร้าง GeoDataFrame ตามลำดับคอลัมน์ที่ให้ + cast ชนิด แล้วบันทึก Shapefile
    ถ้าไม่มีแปลงเลยจะไม่สร้างไฟล์ (Shapefile ว่างระบุชนิด geometry ไม่ได้) และลบผลเก่าทิ้ง"""
    out = gpd.GeoDataFrame(pd.DataFrame(rows, columns=columns), geometry=list(geometries), crs=crs)
    dtypes = {c: "Int64" for c in int_cols}
    dtypes.update({c: "float64" for c in float_cols})
    if dtypes:
        out = out.astype(dtypes)
    out = out[list(columns) + ["geometry"]]
    if len(out):
        path.parent.mkdir(parents=True, exist_ok=True)
        out.to_file(path, driver="ESRI Shapefile", encoding="utf-8")
    else:
        for ext in SHP_PARTS:                          # ลบผลเก่าของรอบก่อน ไม่ให้เข้าใจผิดว่าเป็นผลล่าสุด
            path.with_suffix(ext).unlink(missing_ok=True)
    return out


def to_shp(rows: list, geometries, crs, path: Path) -> gpd.GeoDataFrame:
    """บันทึก Shapefile 14 ฟิลด์เดิม (preset — ใช้เมื่อไม่มี user_schema.json)"""
    return _write_shp(rows, geometries, crs, path, FIELDS,
                      int_cols=("Rai", "Ngan"), float_cols=("Wa",))


def to_shp_layout(rows: list, geometries, crs, path: Path, layout) -> gpd.GeoDataFrame:
    """บันทึก Shapefile ตาม layout ที่ผู้ใช้ตั้ง (ดู landsmaps/user_schema.ParcelLayout)"""
    cols = [c.name for c in layout.columns]
    int_cols = tuple(c.name for c in layout.columns if c.type == "int")
    float_cols = tuple(c.name for c in layout.columns if c.type == "float")
    return _write_shp(rows, geometries, crs, path, cols, int_cols, float_cols)
