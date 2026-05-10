
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

BASE_DIR = Path(__file__).parent.parent.absolute()


class Settings:
    DMS_PORTAL_URL: str = os.getenv("DMS_PORTAL_URL", "https://dms.ahlportal.com/login")
    DMS_USERNAME: str = os.getenv("DMS_USERNAME", "")
    DMS_PASSWORD: str = os.getenv("DMS_PASSWORD", "")
    HEADLESS_MODE: bool = os.getenv("HEADLESS_MODE", "false").lower() == "true"
    BROWSER_PROFILE_DIR: Path = BASE_DIR / os.getenv("BROWSER_PROFILE_DIR", "browser_profile")
    LOG_DIR: Path = BASE_DIR / "logs"
    DATA_DIR: Path = BASE_DIR / "data"

    def __init__(self):
        self.LOG_DIR.mkdir(exist_ok=True)
        self.DATA_DIR.mkdir(exist_ok=True)
        self.BROWSER_PROFILE_DIR.mkdir(exist_ok=True)


settings = Settings()
