@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "SCRIPT_PATH=%ROOT_DIR%dev_launcher\start_fastapi.ps1"
set "CONFIG_PATH=%ROOT_DIR%dev_launcher\config\local-dev.json"

if not exist "%SCRIPT_PATH%" (
    echo [ERROR] Launcher script not found: %SCRIPT_PATH%
    exit /b 1
)

if not exist "%CONFIG_PATH%" (
    echo [ERROR] Launcher config not found: %CONFIG_PATH%
    exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_PATH%" -ConfigPath "%CONFIG_PATH%"
exit /b %ERRORLEVEL%
