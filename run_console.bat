@echo off
setlocal enabledelayedexpansion
for /f "tokens=*" %%b in ('git branch --show-current') do set CUR_BRANCH=%%b
if /i not "!CUR_BRANCH!"=="master" (
    echo Current branch is "!CUR_BRANCH!". Please switch to "master" before running.
    pause
    exit /b 1
)

TITLE Honda FBR Invoice Uploader
echo Starting application...

if not exist venv (
    echo Virtual environment not found. Running setup first...
    call setup.bat
)

call venv\Scripts\activate

echo Checking for dependency updates...
echo This may take a moment if packages are being updated.
venv\Scripts\python -m pip install -r requirements.txt

echo.
echo Launching application...
venv\Scripts\python -m app.main

if %errorlevel% neq 0 (
    echo.
    echo Application crashed or closed with an error.
    pause
)
