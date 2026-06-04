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

:: Add MinGW-w64 to PATH for Rust GNU toolchain (no Visual Studio Build Tools needed)
set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\mingw64\bin;%PATH%"

:: Note: Ye 'dev' mode ka terminal open rahega jab tak hum final .exe nahi banate.
npm run tauri dev