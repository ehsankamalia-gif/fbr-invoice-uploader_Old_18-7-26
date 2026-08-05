@echo off
setlocal

if /i "%~1"=="--console" (
    call "%~dp0run_console.bat"
    exit /b %errorlevel%
)

if not exist "%~dp0venv\Scripts\pythonw.exe" (
    echo Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)

if not exist "%~dp0run_silent.vbs" (
    echo Silent launcher not found: "%~dp0run_silent.vbs"
    pause
    exit /b 1
)

start "" wscript.exe "%~dp0run_silent.vbs"
exit /b 0
