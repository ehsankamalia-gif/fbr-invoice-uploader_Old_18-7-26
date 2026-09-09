@echo off
TITLE Honda FBR Invoice Uploader - Setup
cd /d "%~dp0"
echo ===================================================
echo      Honda FBR Invoice Uploader - First Time Setup
echo ===================================================
echo.

echo [1/4] Detecting Python and preparing the virtual environment...
:: Finds Python wherever it is installed and creates or repairs the
:: environment, so setup works on a computer it was not built on.
call "%~dp0scripts\ensure_python.bat"
if errorlevel 1 (
    pause
    exit /b 1
)
echo       Using Python: %APP_PY%

echo [2/4] Installing dependencies...
"%APP_PY%" -m pip install --upgrade pip
"%APP_PY%" -m pip install -r requirements.txt

echo [3/4] Installing Playwright browser support...
"%APP_PY%" -m playwright install

echo [4/4] Configuring environment...
if not exist .env (
    copy .env.example .env
    echo Created .env file. Please edit it with your FBR credentials.
) else (
    echo .env file already exists. Skipping.
)

echo Initializing database...
"%APP_PY%" -c "from app.db.session import init_db; init_db()"

echo.
echo ===================================================
echo      Setup Complete!
echo ===================================================
echo You can now run the application using 'run.bat' for silent startup.
echo Use 'run.bat --console' only when you want to see startup logs.
echo.
pause
