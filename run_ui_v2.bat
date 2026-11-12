@echo off
title HSR Relic Grader V2
cd /d "%~dp0"

rem ignore any PYTHONPATH/PYTHONHOME set on the machine: this project has its own venv
set "PYTHONPATH="
set "PYTHONHOME="

set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo First run - creating the Python environment...
  python -m venv .venv
  if errorlevel 1 (
    echo.
    echo Could not create the venv. Is Python 3.10+ installed and on PATH?
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
  ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
)

rem V2 draws the character's art behind the grader. That art is HoYoverse's and is
rem deliberately not shipped with this project, so fetch it once if it is missing.
if not exist "ui\static\art\1001.webp" (
  rem no brackets in this echo: ')' inside a block aborts the whole batch file
  echo Fetching character art - one time, about 9 MB...
  ".venv\Scripts\python.exe" tools\fetch_character_art.py
  if errorlevel 1 (
    echo.
    echo Could not fetch the art - V2 still works, just without the background.
    echo.
  )
)

echo Starting the V2 relic grader - your browser will open in a moment.
echo Leave this window open while you use it; close it to stop the tool.
echo.
".venv\Scripts\python.exe" ui\app.py --ui v2
echo.
echo The UI stopped.
pause
