@echo off
setlocal
cd /d "%~dp0"
title Duztec Sales CRM Dashboard
set PORT=8016
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv || (echo Python 3.10+ is required & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r backend\requirements.txt
echo Starting on http://127.0.0.1:%PORT%/
start "" http://127.0.0.1:%PORT%/
python -m uvicorn backend.main:app --host 0.0.0.0 --port %PORT%
pause
