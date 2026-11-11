@echo off
rem Double-click to run the relic grader.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv || goto :err
    ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt || goto :err
)
".venv\Scripts\python.exe" main.py
pause
goto :eof
:err
echo Setup failed.
pause
