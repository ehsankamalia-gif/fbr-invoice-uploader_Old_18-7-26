
@echo off
echo ========================================
echo   Customer Portal Quick Setup
echo ========================================
echo.

echo [1/4] Creating virtual environment...
python -m venv venv
if errorlevel 1 (
    echo Failed to create virtual environment!
    pause
    exit /b 1
)

echo.
echo [2/4] Activating virtual environment...
call venv\Scripts\activate
if errorlevel 1 (
    echo Failed to activate virtual environment!
    pause
    exit /b 1
)

echo.
echo [3/4] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies!
    pause
    exit /b 1
)

echo.
echo [4/4] Creating Django superuser...
echo Please create an admin account for Django Admin:
python manage.py createsuperuser

echo.
echo ========================================
echo   Setup Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Run the server: python manage.py runserver
echo 2. Go to http://localhost:8000/admin to manage customers
echo 3. Go to http://localhost:8000 for the customer portal
echo.
echo To activate a customer portal account, use:
echo python manage.py activate_portal ^<customer_id^> ^<username^> ^<password^>
echo.
pause
