@echo off
title MAX AI Assistant - Launcher
color 0B

echo.
echo  ========================================
echo           MAX AI ASSISTANT v4.5
echo       The Ultimate Desktop Companion
echo  ========================================
echo.

:: Check if Python is available
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Install Python 3.10+ from python.org
    pause
    exit /b 1
)

echo [1/3] Setting up Python backend...
cd /d "%~dp0backend"
if not exist ".venv" (
    echo       Creating virtual environment...
    python -m venv .venv
)

echo [2/3] Starting MAX Backend server (Headless)...
start "MAX-Backend" /min cmd /c "cd /d %~dp0backend && call .venv\Scripts\activate.bat && python main.py"

timeout /t 3 /nobreak >nul

echo [3/3] Starting MAX Desktop Interface...
cd /d "%~dp0max-desktop"
if not exist "node_modules" (
    call npm install
)

start "MAX-Desktop" /min cmd /c "cd /d %~dp0max-desktop && npm run tauri dev"

:: Yahan 'pause' tha jiski wajah se window ruki thi. Ab 'exit' lagaya hai.
exit