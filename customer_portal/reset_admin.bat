
@echo off
cd /d "%~dp0"
echo ========================================
echo   Resetting Admin Account...
echo ========================================
echo.
python reset_admin.py
echo.
pause
