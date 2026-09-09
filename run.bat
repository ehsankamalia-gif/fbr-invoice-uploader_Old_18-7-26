@echo off
setlocal

if /i "%~1"=="--console" (
    call "%~dp0run_console.bat"
    exit /b %errorlevel%
)

if not exist "%~dp0run_silent.vbs" (
    echo Silent launcher not found: "%~dp0run_silent.vbs"
    pause
    exit /b 1
)

:: run_silent.vbs verifies the Python environment and repairs it if the
:: interpreter it was built against is no longer present.
start "" wscript.exe "%~dp0run_silent.vbs"
exit /b 0
