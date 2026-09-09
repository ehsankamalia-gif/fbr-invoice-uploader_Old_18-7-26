@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

TITLE Honda FBR Invoice Uploader

:: Development guard: only applies inside a git checkout. A copied or installed
:: folder has no branch, and must still be able to run.
set "CUR_BRANCH="
for /f "tokens=*" %%b in ('git branch --show-current 2^>nul') do set "CUR_BRANCH=%%b"
if defined CUR_BRANCH (
    if /i not "!CUR_BRANCH!"=="master" (
        echo Current branch is "!CUR_BRANCH!". Please switch to "master" before running.
        pause
        exit /b 1
    )
)

echo Checking Python environment...
call "%~dp0scripts\ensure_python.bat"
if errorlevel 1 (
    pause
    exit /b 1
)
echo Using Python: %APP_PY%

echo Checking for dependency updates...
echo This may take a moment if packages are being updated.
"%APP_PY%" -m pip install -r requirements.txt

echo.
echo Launching application...
"%APP_PY%" -m app.main

if %errorlevel% neq 0 (
    echo.
    echo Application crashed or closed with an error.
    pause
)
