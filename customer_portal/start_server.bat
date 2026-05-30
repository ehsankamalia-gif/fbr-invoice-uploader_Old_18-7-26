
@echo off
cd /d "%~dp0"
echo ========================================
echo   Starting Customer Portal Server
echo ========================================
echo.
echo The server will be available at:
echo   http://127.0.0.1:8000
echo.
echo Press CTRL+C to stop the server.
echo.
echo ========================================
echo.

IF EXIST "..\venv\Scripts\python.exe" (
    echo [INFO] Using virtual environment found in root...
    "..\venv\Scripts\python.exe" manage.py runserver
) ELSE IF EXIST "venv\Scripts\python.exe" (
    echo [INFO] Using local virtual environment...
    "venv\Scripts\python.exe" manage.py runserver
) ELSE (
    echo [WARNING] Virtual environment not found. Using system python...
    python manage.py runserver
)
pause
