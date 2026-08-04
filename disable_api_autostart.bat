@echo off
setlocal

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_DIR%\FBR Invoice Uploader API Launcher.lnk"

if exist "%SHORTCUT_PATH%" (
    del /f /q "%SHORTCUT_PATH%"
    if errorlevel 1 (
        echo [ERROR] Failed to remove startup shortcut.
        exit /b 1
    )

    echo [OK] Auto-start disabled.
    echo [INFO] Removed:
    echo        %SHORTCUT_PATH%
    exit /b 0
)

echo [INFO] Auto-start was already disabled.
echo [INFO] Shortcut not found:
echo        %SHORTCUT_PATH%

exit /b 0
