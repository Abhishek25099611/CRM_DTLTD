@echo off
REM Nightly backup: timestamped copy of the SQLite database, 30-day retention.
REM Schedule daily (~20:00) in Task Scheduler. Copy data\backup off-machine weekly.
setlocal
cd /d "%~dp0"
if not exist "data\backup" mkdir "data\backup"
REM wmic is removed on current Windows 11 builds; PowerShell gives a locale-independent stamp.
set STAMP=
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set STAMP=%%I
if not defined STAMP (
  echo [%date% %time%] BACKUP FAILED: could not read timestamp >> data\logs\backup.log
  exit /b 1
)
copy /y "data\crm.db" "data\backup\crm_%STAMP%.db" >nul
if errorlevel 1 (
  echo [%date% %time%] BACKUP FAILED >> data\logs\backup.log
  exit /b 1
)
echo [%date% %time%] Backup written: crm_%STAMP%.db >> data\logs\backup.log
forfiles /p "data\backup" /m crm_*.db /d -30 /c "cmd /c del @path" 2>nul
exit /b 0
