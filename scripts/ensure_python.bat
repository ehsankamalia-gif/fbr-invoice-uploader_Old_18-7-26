@echo off
:: Locates Python on this computer and prepares the virtual environment.
:: Call this with CALL; it sets APP_PY and APP_PYW for the caller.
::
::   call "%~dp0scripts\ensure_python.bat"
::   if errorlevel 1 goto :python_missing
::   "%APP_PYW%" "%~dp0main.pyw"

setlocal

set "PROJECT_DIR=%~dp0.."
for %%I in ("%PROJECT_DIR%") do set "PROJECT_DIR=%%~fI"

:: 1. Find any interpreter able to run the preparation script.
set "BOOT_PY="
call :try_python "%PROJECT_DIR%\venv\Scripts\python.exe"
if defined BOOT_PY goto :have_boot

for /f "usebackq delims=" %%I in (`py -3 -c "import sys;print(sys.executable)" 2^>nul`) do call :try_python "%%I"
if defined BOOT_PY goto :have_boot

for /f "usebackq delims=" %%I in (`where python 2^>nul`) do call :try_python "%%I"
if defined BOOT_PY goto :have_boot

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do call :try_python "%%D\python.exe"
if defined BOOT_PY goto :have_boot

for /d %%D in ("%ProgramFiles%\Python3*") do call :try_python "%%D\python.exe"
if defined BOOT_PY goto :have_boot

for /d %%D in ("C:\Python3*") do call :try_python "%%D\python.exe"
if defined BOOT_PY goto :have_boot

echo.
echo [ERROR] Python was not found on this computer.
echo Install Python 3.10 or newer from https://www.python.org/downloads/
echo and tick "Add Python to PATH" during installation.
echo.
endlocal & exit /b 1

:have_boot

:: 2. Let the preparation script validate, repair, or rebuild the environment.
::    It prints the interpreter to use; progress messages go to stderr.
set "APP_PY="
:: The extra outer quotes are required: a backquoted command that begins with a
:: quoted path is otherwise mis-parsed by cmd.
for /f "usebackq delims=" %%I in (`""%BOOT_PY%" "%PROJECT_DIR%\scripts\ensure_venv.py" "%PROJECT_DIR%""`) do set "APP_PY=%%I"

if not defined APP_PY (
    endlocal & exit /b 1
)

:: 3. Prefer the windowless interpreter next to it for GUI launches.
set "APP_PYW=%APP_PY%"
for %%I in ("%APP_PY%") do (
    if exist "%%~dpIpythonw.exe" set "APP_PYW=%%~dpIpythonw.exe"
)

endlocal & set "APP_PY=%APP_PY%" & set "APP_PYW=%APP_PYW%" & exit /b 0

:try_python
if defined BOOT_PY exit /b 0
if "%~1"=="" exit /b 0
if not exist "%~1" exit /b 0
:: Skip the Microsoft Store placeholder, which opens the Store instead of running.
echo %~1 | findstr /i "WindowsApps" >nul && exit /b 0
"%~1" -c "import sys" >nul 2>&1
if not errorlevel 1 set "BOOT_PY=%~1"
exit /b 0
