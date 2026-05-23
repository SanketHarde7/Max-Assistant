@echo off
title MAX AI Assistant - Master Launcher
color 0B

echo [1/2] Verifying Python Environment...
cd /d "%~dp0backend"
if not exist ".venv" (
    python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -r requirements.txt --quiet --disable-pip-version-check 2>nul

echo [2/2] Handing over control to Rust Dictator...
cd /d "%~dp0max-desktop"

:: Note: Ye 'dev' mode ka terminal open rahega jab tak hum final .exe nahi banate.
npm run tauri dev