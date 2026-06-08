@echo off
setlocal enabledelayedexpansion
title Email Unsubscriber Setup

:: ── Always run from the folder this .bat file lives in ──────────────────────
cd /d "%~dp0"

echo.
echo =============================================
echo   Email Unsubscriber - Windows Auto-Setup
echo =============================================
echo.
echo Running from: %CD%
echo.

:: ─────────────────────────────────────────────
:: Verify required files are present
:: ─────────────────────────────────────────────
if not exist "gmail_unsubscriber.py" (
    echo [ERROR] gmail_unsubscriber.py not found in this folder.
    echo.
    echo Make sure you extracted ALL files from the ZIP before running setup.
    echo Expected files in the same folder as setup.bat:
    echo   - gmail_unsubscriber.py
    echo   - requirements.txt
    echo.
    pause
    exit /b 1
)
if not exist "requirements.txt" (
    echo [ERROR] requirements.txt not found in this folder.
    echo Please re-download the project and extract all files.
    pause
    exit /b 1
)

:: ─────────────────────────────────────────────
:: STEP 1 — Find or install Python
:: ─────────────────────────────────────────────
echo [1/4] Checking for Python...

set "PYTHON="

py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py -3"
    for /f "tokens=*" %%v in ('py -3 --version 2^>^&1') do echo        Found: %%v
    goto :make_venv
)

python --version >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; exit(0 if sys.version_info.major==3 and sys.version_info.minor>=9 else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON=python"
        for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo        Found: %%v
        goto :make_venv
    )
)

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
    echo        Existing virtual environment found - reusing it.
) else (
    echo        Creating .venv\ in %CD%...
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo        Virtual environment created!
)

set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"

:: ─────────────────────────────────────────────
:: STEP 3 — Install dependencies into venv
:: ─────────────────────────────────────────────
echo.
echo [3/4] Installing dependencies...
echo        (PySide6, Google Auth — first run may take a few minutes)
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
echo [4/4] Checking for saved credentials (Gmail + Yahoo)...
set "FOUND_CREDS=0"
if defined GMAIL_EMAIL      ( echo        Gmail:  %GMAIL_EMAIL%   & set "FOUND_CREDS=1" )
if defined GMAIL_EMAIL_1    ( echo        Gmail:  %GMAIL_EMAIL_1% & set "FOUND_CREDS=1" )
if defined GMAIL_EMAIL_2    ( echo        Gmail:  %GMAIL_EMAIL_2% & set "FOUND_CREDS=1" )
if defined GMAIL_EMAIL_3    ( echo        Gmail:  %GMAIL_EMAIL_3% & set "FOUND_CREDS=1" )
if defined GOOGLE_EMAIL     ( echo        Gmail:  %GOOGLE_EMAIL%  & set "FOUND_CREDS=1" )
if defined YAHOO_EMAIL      ( echo        Yahoo:  %YAHOO_EMAIL%   & set "FOUND_CREDS=1" )
if defined YAHOO_EMAIL_1    ( echo        Yahoo:  %YAHOO_EMAIL_1% & set "FOUND_CREDS=1" )
if defined YAHOO_EMAIL_2    ( echo        Yahoo:  %YAHOO_EMAIL_2% & set "FOUND_CREDS=1" )
if "%FOUND_CREDS%"=="1" (
    echo        These will be auto-filled in the app.
) else (
    echo        No saved credentials found.
    echo        You can enter them manually in the app, or run these once to save them:
    echo.
    echo          Gmail:
    echo            setx GMAIL_EMAIL "you@gmail.com"
    echo            setx GMAIL_APP_PASSWORD "xxxx xxxx xxxx xxxx"
    echo.
    echo          Yahoo:
    echo            setx YAHOO_EMAIL "you@yahoo.com"
    echo            setx YAHOO_APP_PASSWORD "xxxx xxxx xxxx xxxx"
)

echo.
echo =============================================
echo   Launching Email Unsubscriber...
echo =============================================
echo.
"%VENV_PYTHON%" "%CD%\gmail_unsubscriber.py"

if errorlevel 1 (
    echo.
    echo [ERROR] The app closed with an error.
    echo Please screenshot everything above and report it.
)
pause
