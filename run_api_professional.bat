@echo off
setlocal enabledelayedexpansion

title FBR Invoice Uploader API - Professional Mode

REM Set working directory to script location
cd /d "%~dp0"

echo ============================================
echo   FBR Invoice Uploader API Server
echo ============================================
echo.

REM Check if virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo Please run setup.bat first.
    echo.
    pause
    exit /b 1
)

REM Activate virtual environment
echo [1/4] Activating virtual environment...
call venv\Scripts\activate.bat

REM Clean pip cache
echo [2/4] Cleaning pip cache...
python -m pip cache purge >nul 2>&1

REM Install/update requirements
echo [3/4] Checking dependencies...
python -m pip install -r requirements.txt >nul 2>&1

REM Initialize database (ensure tables exist)
echo [4/4] Initializing database...
python -c "from app.db.session import init_db; init_db()"

echo.
echo ============================================
echo   API Server Starting...
echo   Docs: http://localhost:8000/docs
echo   API: http://localhost:8000
echo ============================================
echo.
echo Press Ctrl+C to stop the server
echo.

REM Start server with auto-reload
:loop
python -m uvicorn app.api.server:app --host 0.0.0.0 --port 8000 --reload --log-level info
echo.
echo [WARNING] Server stopped unexpectedly. Restarting in 3 seconds...
timeout /t 3 /nobreak >nul
goto loop
