@echo off
chcp 65001 >nul
echo ========================================
echo   Starting Django Development Server
echo ========================================
echo.

cd /d "%~dp0"
call venv\Scripts\activate

echo Current directory: %cd%
echo.
echo Checking Python installation...
python --version
if errorlevel 1 (
    echo ERROR: Python not found! Make sure Python is installed and in PATH.
    pause
    exit /b 1
)
echo.

echo Running Django system checks first...
python manage.py check
if errorlevel 1 (
    echo.
    echo ERROR: Django system checks failed! Please check the errors above.
    pause
    exit /b 1
)
echo.
echo Django system checks passed!
echo.
echo ========================================
echo Starting server on http://127.0.0.1:8000
echo Press Ctrl+C to stop the server
echo ========================================
echo.

python manage.py runserver 127.0.0.1:8000

pause
