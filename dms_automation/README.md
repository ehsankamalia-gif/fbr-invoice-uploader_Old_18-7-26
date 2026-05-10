
# DMS Portal Automation

A completely independent module for automating DMS Portal operations. This module has no dependencies or interactions with the main FBR Invoice Uploader application.

## Features

- Runs in **background thread** - use your PC for other tasks while automation runs
- Persistent browser profile (saves cookies, login state)
- Auto-fill login credentials
- Frame and Engine number filling
- Headless or visible mode

## Directory Structure

```
dms_automation/
├── config/              # Configuration files
├── data/                # Data storage
├── logs/                # Log files
├── browser_profile/     # Chrome browser profile (auto-created)
├── requirements.txt     # Python dependencies
├── .env                 # Environment variables (copy from .env.example)
├── dms_automator.py     # Main automation class
├── main.py             # Interactive interface
└── quick_start.py      # Quick start script
```

## Setup Instructions

1. **Install dependencies** (from dms_automation directory):
   ```bash
   cd dms_automation
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Configure environment**:
   - Copy `.env.example` to `.env`
   - Edit `.env` and add your DMS credentials
   - Set `HEADLESS_MODE=false` to see the browser, `true` for background

3. **Run the automation**:

   **Interactive mode (recommended first):**
   ```bash
   python main.py
   ```

   **Quick start with command line:**
   ```bash
   python quick_start.py "FRAME123456" "ENG789012"
   ```

## Usage

### Interactive Mode (main.py)
1. Run `python main.py`
2. The browser opens and navigates to DMS portal
3. Complete login manually if needed
4. Choose option 1 to fill frame and engine numbers
5. The automation works in the background while you use your PC

### Programmatic Usage

```python
from dms_automator import DMSAutomator
import time

automator = DMSAutomator()
automator.start()
time.sleep(2)

# Login
automator.login()

# Fill details
result = automator.fill_vehicle_details("FRAME123", "ENG456")
print(result)

# When done
automator.stop()
```

## Configuration (.env)

| Variable | Description | Default |
|----------|-------------|---------|
| DMS_PORTAL_URL | DMS Portal login URL | https://dms.ahlportal.com/login |
| DMS_USERNAME | Your DMS username | |
| DMS_PASSWORD | Your DMS password | |
| HEADLESS_MODE | Run browser without window | false |
| BROWSER_PROFILE_DIR | Browser profile directory | ./browser_profile |

## Important Notes

- This module is **completely independent** - no interaction with main application
- All files are in the `dms_automation/` directory
- Browser runs in a separate thread, so your PC remains responsive
