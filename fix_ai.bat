@echo off
rem Double-click to repair the AI install and download the female starter voices.
cd /d "%~dp0"
set "VPY=%~dp0.venv\Scripts\python.exe"
if exist "%VPY%" (
    "%VPY%" "%~dp0fix_ai.py"
) else (
    python "%~dp0fix_ai.py"
)
