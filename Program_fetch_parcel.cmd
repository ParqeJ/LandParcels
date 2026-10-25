@echo off
rem Double-click to fetch parcels. fetch_parcels.py logs in to LandsMaps (DGA) by itself.
rem PY = the Python that has geopandas installed. Change it if your env is elsewhere.
set "PY=C:\Users\User\anaconda3\envs\satellite\python.exe"
cd /d "%~dp0"
if not exist "%PY%" (
    echo Python not found: %PY%
    echo Edit the PY line in %~nx0
    pause
    exit /b 1
)
echo start fetching parcels
"%PY%" fetch_parcels.py
echo done
pause
