@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Once install.bat calistirin.
  exit /b 1
)
set "AIIQ_PORT=%1"
if "%AIIQ_PORT%"=="" set "AIIQ_PORT=8300"
.venv\Scripts\python.exe launcher.py --port %AIIQ_PORT%
endlocal
