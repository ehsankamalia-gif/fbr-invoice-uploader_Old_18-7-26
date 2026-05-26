
@echo off
cd /d "%~dp0"
echo ========================================
echo   Initializing Django (One-time setup)
echo ========================================
echo.

echo Step 1: Creating migrations for Django apps...
python manage.py makemigrations
if errorlevel 1 (
    echo Note: Some migrations might already exist - this is OK!
)

echo.
echo Step 2: Applying migrations (THIS IS IMPORTANT!)
echo This creates Django's tables (auth, admin, sessions, etc.)
python manage.py migrate
if errorlevel 1 (
    echo.
    echo ERROR: Could not apply migrations!
    echo.
    echo Make sure your MySQL server is running!
    echo And the database "fbr_invoice_uploader" exists!
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Django Initialization Complete!
echo ========================================
echo.
echo Now you can create a superuser:
echo   python manage.py createsuperuser
echo.
echo And then start the server:
echo   python manage.py runserver
echo.
pause
