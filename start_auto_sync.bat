@echo off
title FBR Invoice Uploader - Auto Sync Service
echo ========================================================
echo      Starting Auto-Sync Service
echo ========================================================
echo.

:: 1. Check for .venv
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Found .venv. Activating...
    call .venv\Scripts\activate.bat
    goto :START_SERVICE
)

:: 2. Check for venv
if exist "venv\Scripts\activate.bat" (
    echo [INFO] Found venv. Activating...
    call venv\Scripts\activate.bat
    goto :START_SERVICE
)

:: 3. No venv found
echo [WARNING] No virtual environment found!
echo Attempting to run with system Python...

:START_SERVICE
echo.
echo [INFO] Installing/Verifying watchdog dependency...
python -m pip install watchdog >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Could not install watchdog. Python might not be in PATH.
)

echo.
echo [INFO] Monitoring started.
echo This window will monitor your project and automatically sync changes to GitHub.
echo.

python auto_sync_service.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] The service crashed with error code: %ERRORLEVEL%
    echo Possible reasons:
    echo 1. Python is not installed or not in PATH.
    echo 2. 'watchdog' library is missing.
    echo 3. Git is not installed or configured.
)

echo.
echo Press any key to close...
pause
