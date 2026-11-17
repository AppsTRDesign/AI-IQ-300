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

rem Optional system tools the agent uses (video, git, GitHub, PHP/Composer): installed with winget when missing.
rem A failure only prints a note; the app also fetches ffmpeg and Composer by itself (backend/app/toolchain.py).
where winget >nul 2>nul
if %errorlevel%==0 (
  call :tool ffmpeg Gyan.FFmpeg
  call :tool git Git.Git
  call :tool gh GitHub.cli
  call :tool php PHP.PHP.8.4
) else (
  echo [UYARI] winget yok: ffmpeg, git, gh, php elle kurulabilir. Uygulama ffmpeg ve Composer'i kendisi indirir.
)

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
exit /b 0

:tool
where %1 >nul 2>nul && (echo [OK] %1 & exit /b 0)
echo %1 kuruluyor (winget %2)...
winget install --id %2 --exact --silent --accept-source-agreements --accept-package-agreements --scope user >nul 2>nul || winget install --id %2 --exact --silent --accept-source-agreements --accept-package-agreements >nul 2>nul || echo [UYARI] %1 kurulamadi; elle kurabilirsiniz.
exit /b 0
