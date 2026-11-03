@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo === AI IQ 300 - Kurulum ===

where py >nul 2>nul
if %errorlevel%==0 (
  py -3.12 --version >nul 2>nul && set "PY=py -3.12"
)
if not defined PY (
  python --version 2>nul | findstr /b "Python 3.12" >nul && set "PY=python"
)
if not defined PY (
  echo [HATA] Python 3.12 bulunamadi. https://www.python.org/downloads/ adresinden 3.12.x kurun.
  exit /b 1
)
where node >nul 2>nul || (echo [HATA] Node.js bulunamadi. & exit /b 1)
for /f "delims=" %%v in ('node --version') do echo Node %%v

if not exist .venv (
  echo Sanal ortam olusturuluyor...
  %PY% -m venv .venv || exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || exit /b 1
python -m playwright install chromium

pushd frontend
call npm install || (popd & exit /b 1)
call npm run build || (popd & exit /b 1)
popd

echo.
echo Kurulum tamamlandi. Baslatmak icin: run.bat
endlocal
