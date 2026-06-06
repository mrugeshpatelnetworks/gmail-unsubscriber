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
echo [1/4] Checking for Python...

set "PYTHON="

:: Try the Windows py launcher first (most reliable)
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py -3"
    for /f "tokens=*" %%v in ('py -3 --version 2^>^&1') do echo        Found: %%v
    goto :make_venv
)

:: Try plain python command
python --version >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; exit(0 if sys.version_info.major==3 and sys.version_info.minor>=9 else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON=python"
        for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo        Found: %%v
        goto :make_venv
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
        echo        Python installed!
        goto :make_venv
    )
)

:: Last resort — download Python installer silently via PowerShell
echo        Downloading Python from python.org...
powershell -NoProfile -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe' -OutFile '$env:TEMP\py_installer.exe'"
if errorlevel 1 goto :no_python
echo        Installing Python (this takes about a minute)...
"%TEMP%\py_installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1
del "%TEMP%\py_installer.exe" >nul 2>&1
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py -3"
    echo        Python installed!
    goto :make_venv
)

:no_python
echo.
echo [ERROR] Could not install Python automatically.
echo Please install Python 3.9+ from https://python.org
echo Tick "Add Python to PATH", then run this file again.
pause
exit /b 1

:: ─────────────────────────────────────────────
:: STEP 2 — Create virtual environment
:: ─────────────────────────────────────────────
:make_venv
echo.
echo [2/4] Setting up virtual environment...

if exist ".venv\Scripts\python.exe" (
    echo        Existing virtual environment found — reusing it.
) else (
    echo        Creating virtual environment in .venv\...
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo        Virtual environment created!
)

:: Use the venv Python directly (no activation needed)
set "VENV_PYTHON=.venv\Scripts\python.exe"

:: ─────────────────────────────────────────────
:: STEP 3 — Install dependencies into venv
:: ─────────────────────────────────────────────
echo.
echo [3/4] Installing dependencies into virtual environment...
echo        (PySide6, Google Auth, IMAP libraries)
echo        First run may take a few minutes...
echo.
"%VENV_PYTHON%" -m pip install --upgrade pip --quiet --no-warn-script-location
"%VENV_PYTHON%" -m pip install -r requirements.txt --no-warn-script-location
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo        All dependencies installed!

:: ─────────────────────────────────────────────
:: STEP 4 — Show detected credentials + launch
:: ─────────────────────────────────────────────
echo.
echo [4/4] Checking for saved Gmail credentials...
set "FOUND_CREDS=0"
if defined GMAIL_EMAIL      ( echo        Found: %GMAIL_EMAIL% & set "FOUND_CREDS=1" )
if defined GMAIL_EMAIL_1    ( echo        Found: %GMAIL_EMAIL_1% & set "FOUND_CREDS=1" )
if defined GMAIL_EMAIL_2    ( echo        Found: %GMAIL_EMAIL_2% & set "FOUND_CREDS=1" )
if defined GMAIL_EMAIL_3    ( echo        Found: %GMAIL_EMAIL_3% & set "FOUND_CREDS=1" )
if defined GOOGLE_EMAIL     ( echo        Found: %GOOGLE_EMAIL% & set "FOUND_CREDS=1" )
if "%FOUND_CREDS%"=="1" (
    echo        These will be auto-filled in the app.
) else (
    echo        No saved credentials found.
    echo        You can enter them manually in the app, or save them
    echo        as environment variables for auto-fill next time:
    echo.
    echo          setx GMAIL_EMAIL "you@gmail.com"
    echo          setx GMAIL_APP_PASSWORD "xxxx xxxx xxxx xxxx"
)

echo.
echo =============================================
echo   Launching Gmail Unsubscriber...
echo =============================================
echo.
"%VENV_PYTHON%" gmail_unsubscriber.py

if errorlevel 1 (
    echo.
    echo [ERROR] The app closed with an error.
    echo Please screenshot everything above and report it.
)
pause
