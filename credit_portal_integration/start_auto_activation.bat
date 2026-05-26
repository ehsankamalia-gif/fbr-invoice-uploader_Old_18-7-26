
@echo off
cd /d "%~dp0"
echo ========================================
echo   Starting Auto-Activation Service
echo ========================================
echo.
echo This service will:
echo   - Monitor for new credit sales
echo   - Auto-activate portal access for new customers
echo   - Generate login credentials
echo   - Save credentials to files for staff
echo.
echo ========================================
echo.

python auto_activation_service.py

echo.
echo Service stopped.
pause
