# Professional Auto-Update System for Windows Desktop Apps

This document outlines the architecture and integration steps for the modular update system implemented in the `app/updater/` package.

## 1. Directory Structure
```text
app/
└── updater/
    ├── __init__.py
    ├── version_manager.py      # Semantic versioning logic
    ├── update_checker.py       # Remote JSON fetching (HTTPS)
    ├── downloader.py           # Secure chunked downloads
    ├── installer_launcher.py   # App hand-off to installer
    ├── notification_ui.py      # Detailed Update Dialog (PyQt6)
    ├── toast_notification.py   # Professional Toast Alert (PyQt6)
    └── updater_manager.py      # High-level orchestration
```

## 2. Notification System
The system uses a two-tier notification approach:
1. **Toast Notification**: A non-intrusive alert in the bottom-right corner.
2. **Detailed Dialog**: A modal window with the changelog and progress bar.
To use Bitbucket as your update server, you can host the `version.json` in your repository and access it via the **Raw** URL.

### Raw URL Format
`https://bitbucket.org/<workspace>/<repo>/raw/<branch>/version.json`

Example for this project:
`https://bitbucket.org/python_desktop/python_repository/raw/main/version.json`

### Handling Private Repositories
If your repository is private, you must use a Bitbucket **App Password** for the updater to fetch the file.

```python
# In your integration code
self.updater = UpdaterManager(
    current_version="1.1.0",
    version_url="https://bitbucket.org/python_desktop/python_repository/raw/main/version.json",
    auth=("bitbucket_username", "your_app_password"), # Required for private repos
    parent=self
)
```

## 3. Remote `version.json` Example

## 3. Update Workflow Diagram
1. **Startup**: App launches and initializes `UpdaterManager`.
2. **Check**: `UpdaterManager` starts a background thread to fetch `version.json`.
3. **Compare**: `VersionManager` parses `latest_version` and compares it with the local `APP_VERSION`.
4. **Notify**: If an update exists, `UpdaterManager` emits a signal to the main thread.
5. **UI**: `UpdateNotificationDialog` appears with the changelog.
6. **Action**: User clicks "Update".
7. **Download**: `Downloader` fetches the `.exe` to the system TEMP folder with a progress bar.
8. **Hand-off**: `InstallerLauncher` starts the installer and exits the app immediately.
9. **Install**: The installer overwrites the old files and optionally restarts the app.

## 4. Integration Guide

### Step A: Initialize in Main Window
Add the following to your `MainWindow.__init__`:

```python
from app.updater.updater_manager import UpdaterManager

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # ... your UI init code ...
        
        # Initialize Updater
        self.updater = UpdaterManager(
            current_version="1.1.0", 
            version_url="https://your-server.com/version.json",
            parent=self
        )
        
        # Start background check (non-blocking)
        self.updater.check_for_updates_async()
```

### Step B: PyInstaller Build Instructions
When building your executable, ensure you include the `updater` package and required assets.

```bash
pyinstaller --noconfirm --onefile --windowed --name "EhsanTraderFBR" \
    --add-data "app/updater;app/updater" \
    --collect-all "PyQt6" \
    main.py
```

*Note: If you use a custom installer (like Inno Setup or NSIS), the `InstallerLauncher` will work perfectly as it simply executes whatever `.exe` you provide in the `download_url`.*

## 5. Security & Reliability
- **HTTPS Only**: All requests are forced to use SSL verification.
- **Error Resilience**: Failed downloads are cleaned up from the TEMP folder.
- **Thread-Safe**: UI updates only occur via Qt Signals to prevent application crashes.
- **Timeout Protection**: Network requests will timeout after 10-30 seconds to prevent "hanging" on poor connections.
