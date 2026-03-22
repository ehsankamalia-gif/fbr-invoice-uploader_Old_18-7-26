import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Base Directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables
load_dotenv(BASE_DIR / ".env")

class Config:
    """Central configuration management."""
    APP_NAME = "WhatsPlay Pro"
    VERSION = "1.0.0"
    
    # WhatsApp (WhatsPlay) Config
    WHATSAPP_SESSION_DIR = BASE_DIR / "sessions"
    WHATSAPP_HEADLESS = os.getenv("WHATSAPP_HEADLESS", "false").lower() == "true"
    WHATSAPP_BROWSER_CHANNEL = os.getenv("WHATSAPP_BROWSER_CHANNEL", "chrome")
    WHATSAPP_PROXY_ENABLED = os.getenv("WHATSAPP_PROXY_ENABLED", "false").lower() == "true"
    WHATSAPP_PROXY_SERVER = os.getenv("WHATSAPP_PROXY_SERVER", "")
    
    # WhatsApp Gateway (API) Config
    WA_GATEWAY_ENABLED = os.getenv("WA_GATEWAY_ENABLED", "false").lower() == "true"
    WA_GATEWAY_IP = os.getenv("WA_GATEWAY_IP", "")
    WA_GATEWAY_PORT = os.getenv("WA_GATEWAY_PORT", "8080")
    WA_GATEWAY_INSTANCE = os.getenv("WA_GATEWAY_INSTANCE", "")
    WA_GATEWAY_API_KEY = os.getenv("WA_GATEWAY_API_KEY", "")
    WA_GATEWAY_USE_HTTPS = os.getenv("WA_GATEWAY_USE_HTTPS", "false").lower() == "true"
    
    # Database
    DB_PATH = BASE_DIR / "data" / "whatsplay.db"
    
    # AI Config
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    AI_MODEL = os.getenv("AI_MODEL", "gpt-4-turbo")
    AUTO_REPLY_DELAY = int(os.getenv("AUTO_REPLY_DELAY", "5")) # Seconds
    
    # Anti-Ban Safety
    MIN_DELAY = int(os.getenv("MIN_DELAY", "10"))
    MAX_DELAY = int(os.getenv("MAX_DELAY", "30"))
    RANDOM_DELAY_ENABLED = True

    @classmethod
    def ensure_dirs(cls):
        """Ensure necessary directories exist."""
        cls.WHATSAPP_SESSION_DIR.mkdir(parents=True, exist_ok=True)
        cls.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        (BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)

Config.ensure_dirs()
