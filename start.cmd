@echo off
set PYTHONUTF8=1
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please run setup.ps1 first. See README.md.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m speak_sound
if errorlevel 1 pause
