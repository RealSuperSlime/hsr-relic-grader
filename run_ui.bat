@echo off
title HSR Relic Grader
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

echo Starting the relic grader UI - your browser will open in a moment.
echo Leave this window open while you use it; close it to stop the tool.
echo.
".venv\Scripts\python.exe" ui\app.py
echo.
echo The UI stopped.
pause
