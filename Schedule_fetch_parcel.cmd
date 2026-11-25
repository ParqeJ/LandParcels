@echo off
rem For Windows Task Scheduler (no "pause", so the task ends by itself).
rem   Schedule_fetch_parcel.cmd                              = every file in areas\
rem   Schedule_fetch_parcel.cmd areas\bnn.gdb areas\cbd.kmz  = only these inputs
rem Any fetch_parcels.py option also works, e.g. --refetch notfound
rem Output goes to cache\autorun.log ; progress per input shows in the dashboard input page.
rem PY = the Python that has geopandas installed (same as Program_fetch_parcel.cmd).
set "PY=C:\Users\User\anaconda3\envs\satellite\python.exe"
cd /d "%~dp0"
if not exist cache mkdir cache
if not exist "%PY%" (
    echo [%date% %time%] Python not found: %PY% >> "cache\autorun.log"
    exit /b 1
)
echo. >> "cache\autorun.log"
echo ==== [%date% %time%] fetch_parcels.py %* >> "cache\autorun.log"
"%PY%" -u fetch_parcels.py %* >> "cache\autorun.log" 2>&1
set "RC=%ERRORLEVEL%"
echo ==== [%date% %time%] exit %RC% >> "cache\autorun.log"
exit /b %RC%
