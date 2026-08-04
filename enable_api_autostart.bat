@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SCRIPT_PATH=%ROOT_DIR%start_system_silent.vbs"
set "SHORTCUT_PATH=%STARTUP_DIR%\FBR Invoice Uploader API Launcher.lnk"

if not exist "%SCRIPT_PATH%" (
    echo [ERROR] Silent startup script not found: %SCRIPT_PATH%
    exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$shell = New-Object -ComObject WScript.Shell; " ^
  "$shortcut = $shell.CreateShortcut('%SHORTCUT_PATH%'); " ^
  "$shortcut.TargetPath = 'wscript.exe'; " ^
  "$shortcut.Arguments = '""%SCRIPT_PATH%""'; " ^
  "$shortcut.WorkingDirectory = '%ROOT_DIR%'; " ^
  "$shortcut.IconLocation = '%SystemRoot%\System32\SHELL32.dll,13'; " ^
  "$shortcut.Description = 'Auto-start FBR Invoice Uploader API launcher at Windows sign-in'; " ^
  "$shortcut.Save()"

if errorlevel 1 (
    echo [ERROR] Failed to create startup shortcut.
    exit /b 1
)

echo [OK] Auto-start enabled.
echo [OK] The API launcher will start automatically when you sign in to Windows.
echo [INFO] Shortcut created at:
echo        %SHORTCUT_PATH%

exit /b 0
