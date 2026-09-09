@echo off
:: Prepares Python (detecting it automatically) and starts the application.
:: Used by run.bat and by run_silent.vbs when the environment needs repair.

setlocal
cd /d "%~dp0"

echo Checking Python environment...
call "%~dp0scripts\ensure_python.bat"
if errorlevel 1 (
    echo.
    echo The application could not be started because Python is unavailable.
    echo.
    pause
    exit /b 1
)

echo Starting Ehsan Trader FBR System...
start "" "%APP_PYW%" "%~dp0main.pyw"
exit /b 0
