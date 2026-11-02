@echo off
rem Double-click to run Voicefork. The first run sets everything up (5-15 min with AI voices).
setlocal
cd /d "%~dp0"
title Voicefork

if exist ".venv\Scripts\python.exe" if exist ".venv\.ready" goto run

echo.
echo  Voicefork first-time setup
echo  --------------------------
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3.12") else (set "PY=python")
%PY% --version >nul 2>nul
if errorlevel 1 (
    echo  Python 3.12 is not installed.
    echo  Get it from https://www.python.org/downloads/release/python-3128/
    echo  and tick "Add python.exe to PATH" in the installer. Then run this again.
    pause
    exit /b 1
)

if not exist ".venv" %PY% -m venv .venv || goto fail
set "VPY=.venv\Scripts\python.exe"
"%VPY%" -m pip install -q --upgrade pip
echo  Installing the app ...
"%VPY%" -m pip install -q -r requirements.txt || goto fail

where nvidia-smi >nul 2>nul
if %errorlevel%==0 (
    echo  NVIDIA GPU found: installing AI voices (about 3 GB, takes a while^) ...
    "%VPY%" -m pip install -q torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128 || goto fail
    "%VPY%" -m pip install -q -r requirements-ai.txt || goto fail
) else (
    echo  No NVIDIA GPU found: installing Laptop mode for AI voices (CPU^) ...
    "%VPY%" -m pip install -q torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cpu || goto fail
    "%VPY%" -m pip install -q -r requirements-ai.txt || goto fail
)
echo ok> ".venv\.ready"
echo  Done.

:run
rem a minimised console stays open; if the app crashes the reason ends up in crash-log.txt
start "Voicefork (leave open)" /min cmd /c ".venv\Scripts\python.exe -m voicefork gui 2> crash-log.txt"
exit /b 0

:fail
echo.
echo  Setup failed. Please open an issue on GitHub with a screenshot of this window.
pause
exit /b 1
