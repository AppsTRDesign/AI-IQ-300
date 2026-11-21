@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title AI IQ 300
if not exist .venv\Scripts\python.exe (
  powershell -NoProfile -Command "if ((Get-UICulture).TwoLetterISOLanguageName -eq 'tr') { Write-Host '  Once install.bat calistirin.' -ForegroundColor Yellow } else { Write-Host '  Run install.bat first.' -ForegroundColor Yellow }"
  pause
  exit /b 1
)
rem run.bat [port] [--verbose]
set "AIIQ_PORT=8300"
set "EXTRA="
for %%a in (%*) do (
  if /i "%%~a"=="--verbose" (set "EXTRA=--verbose") else (set "AIIQ_PORT=%%~a")
)
.venv\Scripts\python.exe launcher.py --port %AIIQ_PORT% %EXTRA%
endlocal
