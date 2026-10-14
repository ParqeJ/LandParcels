"""ดึงแปลงที่ดินจาก LandsMaps (กรมที่ดิน) ตามไฟล์ขอบเขตพื้นที่ -> Shapefile"""

from .area import load_area
from .pipeline import Result, run_area

__all__ = ["Result", "load_area", "run_area"]
