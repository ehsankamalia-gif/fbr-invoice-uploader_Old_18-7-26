@echo off
TITLE Honda FBR Invoice Uploader - Setup
echo ===================================================
echo      Honda FBR Invoice Uploader - First Time Setup
echo ===================================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not found! 
    echo Please install Python 3.10 or later from python.org and try again.
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b
)

echo [1/4] Creating virtual environment...
python -m venv venv

echo [2/4] Activating virtual environment...
call venv\Scripts\activate

echo [3/4] Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo Installing Playwright browsers...
python -m playwright install

echo [4/4] Configuring environment...
if not exist .env (
    copy .env.example .env
    echo Created .env file. Please edit it with your FBR credentials.
) else (
    echo .env file already exists. Skipping.
)

echo Initializing database...
python -c "from app.db.session import init_db; init_db()"

echo.
echo ===================================================
echo      Setup Complete!
echo ===================================================
echo You can now run the application using 'run.bat'
echo.
pause
