
@echo off
cd /d "%~dp0"
echo ========================================
echo   Customer Portal Setup
echo ========================================
echo.

echo Step 1: Installing dependencies (including MySQL support)...
python -m pip install django==4.2 python-dotenv cryptography pymysql mysqlclient
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install dependencies!
    echo.
    echo If mysqlclient fails, try installing just pymysql:
    echo   pip install django==4.2 python-dotenv cryptography pymysql
    echo.
    pause
    exit /b 1
)

echo.
echo Step 2: Verifying installation...
python -c "import django; print('OK - Django', django.get_version())"
if errorlevel 1 (
    echo ERROR: Django not installed properly!
    pause
    exit /b 1
)

echo.
echo Step 3: Checking database connection...
python -c "
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute('SELECT 1')
    print('OK - Database connected!')
"
if errorlevel 1 (
    echo.
    echo Note: Database connection might need MySQL.
    echo If you're using SQLite, it should still work.
    echo.
)

echo.
echo ========================================
echo   Setup Complete!
echo ========================================
echo.
echo Next steps:
echo.
echo 1. Create admin account (run this):
echo    python manage.py createsuperuser
echo.
echo 2. Start the server (run this):
echo    python manage.py runserver
echo.
echo Then open in browser:
echo - Customer Portal: http://127.0.0.1:8000
echo - Admin Panel:   http://127.0.0.1:8000/admin
echo.
pause
