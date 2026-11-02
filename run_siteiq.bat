@echo off
setlocal
cd /d %~dp0
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10 or newer and enable PATH.
  pause
  exit /b 1
)
if not exist .venv (
  python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --quiet -r requirements.txt
if not exist frontend\dist\index.html (
  where npm >nul 2>nul
  if errorlevel 1 (
    echo Node.js 20 or newer is needed to build the interface: https://nodejs.org
    pause
    exit /b 1
  )
  pushd frontend
  call npm ci --no-audit --no-fund
  call npx vite build
  popd
)
start "" http://127.0.0.1:8765
python -m uvicorn siteiq.api:app --host 127.0.0.1 --port 8765
