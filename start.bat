@echo off
title JARVIS AI Assistant - Launcher
color 0B

echo.
echo  ========================================
echo       JARVIS AI ASSISTANT v2.0
echo       Zero Budget, Maximum Impact
echo  ========================================
echo.

:: Check if Python is available
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Install Python 3.10+ from python.org
    pause
    exit /b 1
)

:: Check if Node.js is available
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found! Install from nodejs.org
    pause
    exit /b 1
)

echo [1/4] Setting up backend...

:: Navigate to backend and check/create venv
cd /d "%~dp0backend"

if not exist ".venv" (
    echo       Creating virtual environment...
    python -m venv .venv
)

:: Activate venv and install requirements
echo [2/4] Installing backend dependencies...
call .venv\Scripts\activate.bat
pip install -r requirements.txt --quiet --disable-pip-version-check 2>nul

:: Start backend in background
echo [3/4] Starting backend server...
start "JARVIS-Backend" cmd /c "cd /d %~dp0backend && call .venv\Scripts\activate.bat && python main.py"

:: Wait for backend to start
timeout /t 3 /nobreak >nul

:: Start frontend
echo [4/4] Starting frontend...
cd /d "%~dp0frontend"

:: Install npm packages if needed
if not exist "node_modules" (
    echo       Installing frontend dependencies...
    call npm install
)

:: Start Vite dev server
start "JARVIS-Frontend" cmd /c "cd /d %~dp0frontend && npm run dev"

:: Wait and open browser
timeout /t 4 /nobreak >nul
start http://localhost:5173

echo.
echo  ========================================
echo   JARVIS is running!
echo   Frontend: http://localhost:5173
echo   Backend:  http://localhost:8000
echo   
echo   Press Ctrl+C to stop.
echo  ========================================
echo.

:: Keep window open
pause
