
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
python manage.py runserver
pause
