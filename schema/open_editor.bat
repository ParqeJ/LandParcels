@echo off
rem เปิด Schema Editor ใน browser — รัน HTTP server ชั่วคราวเพื่อให้ fetch catalog JSON ได้
rem Double-click ไฟล์นี้เพื่อเปิด editor

cd /d "%~dp0"
set PORT=8765

echo.
echo === LandParcels Schema Editor ===
echo กำลังรัน http.server ที่ http://localhost:%PORT%/schema_editor.html
echo ปิด server ด้วย Ctrl+C แล้วปิดหน้าต่างนี้
echo.

start "" "http://localhost:%PORT%/schema_editor.html"
python -m http.server %PORT%
