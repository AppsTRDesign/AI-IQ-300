@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title AI IQ 300 - Setup

rem Language of the messages below: Turkish on a Turkish Windows, English everywhere else (AIIQ_LANG=tr/en forces it).
set "UILANG=%AIIQ_LANG%"
if "%UILANG%"=="" for /f "usebackq delims=" %%l in (`powershell -NoProfile -Command "(Get-UICulture).TwoLetterISOLanguageName" 2^>nul`) do set "UILANG=%%l"
if /i not "%UILANG%"=="tr" set "UILANG=en"
set "AIIQ_LANG=%UILANG%"

if /i "%UILANG%"=="tr" (
  set "M_PY=Python 3.12 bulunamadi. https://www.python.org/downloads/ adresinden 3.12.x kurun ve tekrar deneyin."
  set "M_NODE=Node.js bulunamadi. https://nodejs.org adresinden LTS surumunu kurun ve tekrar deneyin."
  set "M_CHECK=Gereksinimler denetleniyor..."
  set "M_FAIL=Kurulum tamamlanamadi. Ayrintilar icin data\logs klasorundeki kayda bakin."
) else (
  set "M_PY=Python 3.12 was not found. Install 3.12.x from https://www.python.org/downloads/ and run this again."
  set "M_NODE=Node.js was not found. Install the LTS version from https://nodejs.org and run this again."
  set "M_CHECK=Checking requirements..."
  set "M_FAIL=Setup did not finish. See the log in the data\logs folder for details."
)

echo.
echo   !M_CHECK!
where py >nul 2>nul
if %errorlevel%==0 (
  py -3.12 --version >nul 2>nul && set "PY=py -3.12"
)
if not defined PY (
  python --version 2>nul | findstr /b "Python 3.12" >nul && set "PY=python"
)
if not defined PY (
  echo   [x] !M_PY!
  pause
  exit /b 1
)
where node >nul 2>nul || (
  echo   [x] !M_NODE!
  pause
  exit /b 1
)

rem The installer itself (steps, progress bar, elapsed / remaining time, log): installer.py, standard library only.
%PY% installer.py
if errorlevel 1 (
  echo   !M_FAIL!
  pause
  exit /b 1
)
endlocal
exit /b 0
