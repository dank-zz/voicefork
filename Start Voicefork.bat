@echo off
rem Double-click to run Voicefork. First run sets everything up, 5-15 min with AI voices.
setlocal
cd /d "%~dp0"
title Voicefork
set "ROOT=%~dp0"
set "VPY=%ROOT%.venv\Scripts\python.exe"

rem .venv\.ready holds the package lists it was set up with. A newer version with
rem different lists re-runs the install, which is quick: pip skips what is already there.
copy /b /y "%ROOT%requirements.txt"+"%ROOT%requirements-ai.txt" "%TEMP%\voicefork-req.txt" >nul
set "READY="
if exist "%VPY%" if exist "%ROOT%.venv\.ready" set "READY=1"
if defined READY (
    fc /b "%TEMP%\voicefork-req.txt" "%ROOT%.venv\.ready" >nul && goto run
    call :visible
    echo.
    echo  Voicefork updated: checking packages ...
) else (
    call :visible
    echo.
    echo  Voicefork first-time setup
    echo  --------------------------
)

rem Find a usable Python. Voicefork needs 3.10 - 3.13, 3.12 recommended. Try the py
rem launcher versioned shims first, then python and python3 on PATH, and confirm each
rem one reports a supported 3.1x before using it. The check runs in the trypy label so
rem the inline Python stays out of this for-block, which CMD would otherwise mis-parse.
set "PY="
for %%P in ("py -3.12" "py -3.13" "py -3.11" "py -3.10" "python" "python3" "py -3") do call :trypy %%~P

rem New Python install manager present but no runtime installed. Install 3.12, then retry.
if not defined PY (
    where py >nul 2>nul && (
        echo  No Python 3.10-3.13 runtime found; installing Python 3.12 ...
        py install 3.12 >nul 2>nul
        call :trypy py -3.12
    )
)

if not defined PY (
    echo.
    echo  Voicefork needs Python 3.10 - 3.13 and none was found.
    echo  Get it from https://www.python.org/downloads/release/python-3128/
    echo  and tick the Add python.exe to PATH box in the installer. Then run this again.
    pause
    exit /b 1
)

if not exist "%ROOT%.venv" %PY% -m venv "%ROOT%.venv" || goto fail
"%VPY%" -m pip install -q --upgrade pip
echo  Installing the app ...
"%VPY%" -m pip install -q -r "%ROOT%requirements.txt" || goto fail

where nvidia-smi >nul 2>nul
if %errorlevel%==0 (
    echo  NVIDIA GPU found: installing AI voices, about 3 GB, takes a while ...
    "%VPY%" -m pip install -q torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu128 || goto fail
    "%VPY%" -m pip install -q -r "%ROOT%requirements-ai.txt" || goto fail
) else (
    echo  No NVIDIA GPU found: installing Laptop mode for AI voices on CPU ...
    "%VPY%" -m pip install -q torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cpu || goto fail
    "%VPY%" -m pip install -q -r "%ROOT%requirements-ai.txt" || goto fail
)
copy /b /y "%TEMP%\voicefork-req.txt" "%ROOT%.venv\.ready" >nul
echo  Done.

:run
rem once per install: put Voicefork on the desktop and in the Start menu
if not exist "%ROOT%.venv\.shortcut" (
    "%VPY%" -m voicefork shortcut
    echo made> "%ROOT%.venv\.shortcut"
)
rem no console window; if the app crashes the reason ends up in crash-log.txt
start "" "%ROOT%.venv\Scripts\pythonw.exe" -m voicefork gui
exit /b 0

:trypy
rem Keep the first candidate launcher that reports Python 3.10 to 3.13.
if defined PY exit /b 0
%* -c "import sys;sys.exit(0 if sys.version_info[:2] in ((3,10),(3,11),(3,12),(3,13)) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=%*"
exit /b 0

:visible
rem setup needs a window you can see: the desktop shortcut starts this file minimised
if defined VF_SHOWN exit /b 0
set "VF_SHOWN=1"
start "Voicefork setup" cmd /c ""%~f0""
exit

:fail
echo.
echo  Setup failed. Please open an issue on GitHub with a screenshot of this window.
pause
exit /b 1
