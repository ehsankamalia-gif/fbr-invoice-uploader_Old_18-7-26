@echo off
TITLE Honda FBR Invoice Uploader - Install
echo Installing Honda FBR Invoice Uploader...
call setup.bat
if %errorlevel% neq 0 (
    echo Setup failed.
    pause
    exit /b 1
)
echo Launching application...
start "" wscript.exe "%~dp0run_silent.vbs"
