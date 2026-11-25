@echo off
rem LandParcels Dashboard launcher
rem Double-click เพื่อเปิด dashboard — web UI รวมทุกอย่าง (schema, run, monitor, map)

cd /d "%~dp0"
set PORT=8765

echo.
echo === LandParcels Dashboard ===
echo URL: http://localhost:%PORT%
echo กด Ctrl+C เพื่อปิด server
echo.

rem ตรวจ dependencies (ติดตั้งครั้งแรกถ้ายังไม่มี)
python -c "import fastapi, uvicorn, multipart" 2>nul
if errorlevel 1 (
  echo [setup] ติดตั้ง fastapi + uvicorn + python-multipart ครั้งแรก...
  pip install fastapi uvicorn python-multipart
)

start "" "http://localhost:%PORT%"
python -m uvicorn dashboard.server:app --host 127.0.0.1 --port %PORT%
