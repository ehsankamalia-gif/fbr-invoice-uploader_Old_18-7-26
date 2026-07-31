# Local Dev Launcher Setup

## Folder Structure

```text
fbr-invoice-uploader_Old_18-7-26/
|-- start_system.bat
`-- dev_launcher/
    |-- start_fastapi.ps1
    |-- config/
    |   `-- local-dev.json
    |-- logs/
    `-- state/
```

## What This Launcher Does

- Starts Laragon if it is not already running.
- Waits for MySQL before starting FastAPI.
- Checks Apache availability as part of the Laragon stack.
- Starts FastAPI with the configured virtual environment Python.
- Avoids starting duplicate Laragon or FastAPI instances.
- Restarts FastAPI automatically if it crashes.
- Writes launcher and API logs under `dev_launcher/logs`.
- Stops the managed FastAPI process when the launcher is closed.
- Can optionally stop Laragon too by setting `stop_laragon_on_exit` to `true` in the config.

## One-Time Setup

1. Confirm Laragon is installed at `C:\laragon`, or update `laragon.install_path` in [local-dev.json](file:///C:/laragon/www/fbr-invoice-uploader_Old_18-7-26/dev_launcher/config/local-dev.json).
2. Confirm your project path in [local-dev.json](file:///C:/laragon/www/fbr-invoice-uploader_Old_18-7-26/dev_launcher/config/local-dev.json) matches your repo location.
3. Confirm your virtual environment exists at `venv\Scripts\python.exe` under the project path, or update `fastapi.venv_path`.
4. In Laragon, make sure Apache and MySQL are enabled and Auto Start is configured in Laragon preferences.
5. If you want a different API host or port, update `fastapi.host` and `fastapi.port` in [local-dev.json](file:///C:/laragon/www/fbr-invoice-uploader_Old_18-7-26/dev_launcher/config/local-dev.json).

## How To Start Everything

1. Double-click [start_system.bat](file:///C:/laragon/www/fbr-invoice-uploader_Old_18-7-26/start_system.bat).
2. Watch for these status messages in the console:
   - `Starting Laragon...`
   - `Waiting for MySQL...`
   - `Starting FastAPI...`
   - `API Server is running.`
3. Open Swagger at `http://127.0.0.1:8000/docs` unless you changed the host or port.

## How To Stop Everything

1. Focus the launcher console window.
2. Press `Ctrl+C` or close the window.
3. The launcher will stop the managed FastAPI server in its shutdown routine.
4. Laragon will keep running unless `stop_laragon_on_exit` is set to `true`.

## Log Files

- Launcher log: `dev_launcher/logs/launcher-YYYYMMDD.log`
- FastAPI stdout: `dev_launcher/logs/fastapi.stdout.log`
- FastAPI stderr: `dev_launcher/logs/fastapi.stderr.log`
- Runtime state: `dev_launcher/state/fastapi-process.json`

## Configuration Notes

The main settings live in [local-dev.json](file:///C:/laragon/www/fbr-invoice-uploader_Old_18-7-26/dev_launcher/config/local-dev.json):

- `laragon.install_path`: Laragon install directory.
- `laragon.mysql_host` and `laragon.mysql_port`: MySQL readiness check target.
- `laragon.apache_host` and `laragon.apache_port`: Apache readiness check target.
- `laragon.stop_laragon_on_exit`: Set `true` if you want the launcher to stop Laragon too.
- `fastapi.project_path`: FastAPI project root.
- `fastapi.venv_path`: Virtual environment folder. Relative values are resolved from `project_path`.
- `fastapi.app`: Uvicorn app import path.
- `fastapi.host` and `fastapi.port`: API binding target.
- `fastapi.enable_reload`: Keep `false` for a stable supervised process. Set to `true` only if you explicitly want Uvicorn reload mode.

## Troubleshooting

- If MySQL never becomes available, open Laragon once manually and confirm MySQL starts normally.
- If Apache fails, check for a port `80` conflict with IIS, Skype, or another local server.
- If FastAPI does not start, verify the Python executable exists in the configured virtual environment.
- If the launcher says another instance is already running, close the existing launcher window first.
