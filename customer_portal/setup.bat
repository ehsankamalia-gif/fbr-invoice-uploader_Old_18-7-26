
@echo off
cd /d "%~dp0"
echo ========================================
echo   Customer Portal Setup
echo ========================================
echo.

echo [1] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install dependencies!
    pause
    exit /b 1
)

echo.
echo [2] Creating Django superuser...
echo Please create an admin account:
python manage.py createsuperuser

echo.
echo ========================================
echo   Setup Complete!
echo ========================================
echo.
echo Now run: python manage.py runserver
echo.
pause
