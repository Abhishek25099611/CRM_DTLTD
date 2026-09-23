@echo off
REM Nightly backup: timestamped copy of the SQLite database, 30-day retention.
REM Schedule daily (~20:00) in Task Scheduler. Copy data\backup off-machine weekly.
setlocal
cd /d "%~dp0"
if not exist "data\backup" mkdir "data\backup"
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
set STAMP=%DT:~0,8%_%DT:~8,6%
copy /y "data\crm.db" "data\backup\crm_%STAMP%.db" >nul
if errorlevel 1 (
  echo [%date% %time%] BACKUP FAILED >> data\logs\backup.log
  exit /b 1
)
echo [%date% %time%] Backup written: crm_%STAMP%.db >> data\logs\backup.log
forfiles /p "data\backup" /m crm_*.db /d -30 /c "cmd /c del @path" 2>nul
exit /b 0
