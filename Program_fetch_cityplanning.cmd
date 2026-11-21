@echo off
rem Double-click to fetch a province city planning plan from LandsMaps as Shapefile/GPKG.
rem PY = the Python that has geopandas installed. Change it if your env is elsewhere.
set "PY=C:\Users\User\anaconda3\envs\satellite\python.exe"
cd /d "%~dp0"
if not exist "%PY%" (
    echo Python not found: %PY%
    echo Edit the PY line in %~nx0
    pause
    exit /b 1
)
echo ======================================================
echo   Fetch City Planning from LandsMaps
echo ======================================================
echo.
"%PY%" fetch_cityplanning.py --list-provinces --hints
echo.
set "PV="
set /p PV=Province code or Thai name (blank = quit): 
if not defined PV (
    echo cancelled
    pause
    exit /b 0
)
echo.
"%PY%" fetch_cityplanning.py %PV%
echo done
pause
