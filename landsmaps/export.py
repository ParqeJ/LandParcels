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


def parcel_row(parcel_seq, land_no, details: dict) -> dict:
    key = str(parcel_seq)
    if key not in details:
        return empty_row(land_no, DEED, REMARK_PENDING)
    info = details[key]
    if not info:
        return empty_row(land_no, DEED, REMARK_NOT_FOUND)
    if str(info.get("parcel_seq")) != key:
        return empty_row(land_no, DEED, REMARK_MISMATCH)
    return detail_row(land_no, info, info.get("parcelno") or "")


def to_shp(rows: list, geometries, crs, path: Path) -> gpd.GeoDataFrame:
    """บันทึก Shapefile ถ้าไม่มีแปลงเลยจะไม่สร้างไฟล์ (Shapefile ว่างระบุชนิด geometry ไม่ได้)"""
    out = gpd.GeoDataFrame(pd.DataFrame(rows, columns=FIELDS), geometry=list(geometries), crs=crs)
    out = out.astype({"Rai": "Int64", "Ngan": "Int64", "Wa": "float64"})[FIELDS + ["geometry"]]
    if len(out):
        path.parent.mkdir(parents=True, exist_ok=True)
        out.to_file(path, driver="ESRI Shapefile", encoding="utf-8")
    else:
        for ext in SHP_PARTS:                          # ลบผลเก่าของรอบก่อน ไม่ให้เข้าใจผิดว่าเป็นผลล่าสุด
            path.with_suffix(ext).unlink(missing_ok=True)
    return out
