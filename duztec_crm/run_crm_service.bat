@echo off
REM Headless launcher for Windows Task Scheduler (no browser, no pause).
REM Task: run at startup, "run whether user is logged on or not", restart on failure.
setlocal
cd /d "%~dp0"
set PORT=8016
if not exist "data\logs" mkdir "data\logs"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv || exit /b 1
  .venv\Scripts\python -m pip install --quiet --upgrade pip
  .venv\Scripts\python -m pip install --quiet -r backend\requirements.txt
)
echo [%date% %time%] Starting Duztec Sales CRM on port %PORT% >> data\logs\service.log
.venv\Scripts\python -m uvicorn backend.main:app --host 0.0.0.0 --port %PORT% >> data\logs\service.log 2>&1
echo [%date% %time%] CRM process exited with code %errorlevel% >> data\logs\service.log
exit /b %errorlevel%
