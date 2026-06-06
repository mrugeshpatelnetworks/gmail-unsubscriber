@echo off
setlocal enabledelayedexpansion
title Gmail Unsubscriber Setup

echo.
echo =============================================
echo   Gmail Unsubscriber - Windows Auto-Setup
echo =============================================
echo.

:: ─────────────────────────────────────────────
:: STEP 1 — Find or install Python
:: ─────────────────────────────────────────────
echo [1/3] Checking for Python...

:: Try the Windows py launcher first (most reliable)
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py -3"
    for /f "tokens=*" %%v in ('py -3 --version 2^>^&1') do echo        Found: %%v
    goto :deps
)

:: Try plain python command
python --version >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; exit(0 if sys.version_info.major==3 else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON=python"
        for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo        Found: %%v
        goto :deps
    )
)

:: Not found — try winget (built into Windows 10/11)
echo        Python not found. Installing automatically...
echo.
winget --version >nul 2>&1
if not errorlevel 1 (
    echo        Using Windows Package Manager (winget)...
    winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    py -3 --version >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON=py -3"
        echo        Python installed successfully!
        goto :deps
    )
)

:: Last resort — download installer via PowerShell
echo        Downloading Python installer from python.org...
powershell -NoProfile -Command ^
    "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe' -OutFile '$env:TEMP\py_installer.exe'"
if errorlevel 1 (
    echo.
    echo [ERROR] Could not download Python.
    echo Please install Python 3.9+ manually from https://python.org
    echo Make sure to tick "Add Python to PATH" during install, then run this file again.
    pause
    exit /b 1
)
echo        Running Python installer (this takes ~1 minute)...
"%TEMP%\py_installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1
del "%TEMP%\py_installer.exe" >nul 2>&1

py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py -3"
    echo        Python installed successfully!
    goto :deps
)

echo.
echo [ERROR] Automatic Python install failed.
echo Please install Python 3.9+ from https://python.org
echo Tick "Add Python to PATH", then run this file again.
pause
exit /b 1

:: ─────────────────────────────────────────────
:: STEP 2 — Install Python dependencies
:: ─────────────────────────────────────────────
:deps
echo.
echo [2/3] Installing dependencies (PySide6 + Gmail libraries)...
echo        This may take a few minutes on first run...
echo.
%PYTHON% -m pip install --upgrade pip --quiet --no-warn-script-location
%PYTHON% -m pip install -r requirements.txt --no-warn-script-location
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install dependencies.
    echo Try running this in a terminal: pip install -r requirements.txt
    pause
    exit /b 1
)
echo        All dependencies installed!

:: ─────────────────────────────────────────────
:: STEP 3 — Launch the app
:: ─────────────────────────────────────────────
echo.
echo [3/3] Launching Gmail Unsubscriber...
echo.
%PYTHON% gmail_unsubscriber.py

if errorlevel 1 (
    echo.
    echo [ERROR] The app closed with an error.
    echo Please screenshot the error above and report it.
)
pause
