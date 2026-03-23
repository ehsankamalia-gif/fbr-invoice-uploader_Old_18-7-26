import os
import sys
import urllib.parse
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

# Load environment variables
def get_env_path():
    """Get the path to .env file, considering both script and frozen (EXE) modes."""
    if getattr(sys, 'frozen', False):
        # Running as a bundled EXE
        return Path(sys.executable).parent / ".env"
    else:
        # Running as a script
        return Path(__file__).resolve().parent.parent.parent / ".env"

env_path = get_env_path()
load_dotenv(dotenv_path=env_path)

# Resolve environment-specific FBR settings
FBR_ENV = os.getenv("FBR_ENV", "SANDBOX").upper()
SANDBOX = {
    "FBR_API_BASE_URL": os.getenv("FBR_SANDBOX_API_BASE_URL", "https://esp.fbr.gov.pk:8243/PT/v1"),
    "FBR_POS_ID": os.getenv("FBR_SANDBOX_POS_ID", os.getenv("FBR_POS_ID", "")),
    "FBR_USIN": os.getenv("FBR_SANDBOX_USIN", os.getenv("FBR_USIN", "")),
    "FBR_AUTH_TOKEN": os.getenv("FBR_SANDBOX_AUTH_TOKEN", os.getenv("FBR_AUTH_TOKEN", "")),
    "FBR_TAX_RATE": os.getenv("FBR_SANDBOX_TAX_RATE", "18.0"),
    "FBR_PCT_CODE": os.getenv("FBR_SANDBOX_PCT_CODE", "8711.2010"),
    "FBR_INVOICE_TYPE": os.getenv("FBR_SANDBOX_INVOICE_TYPE", "Standard"),
    "FBR_DISCOUNT": os.getenv("FBR_SANDBOX_DISCOUNT", "0.0"),
    "FBR_ITEM_CODE": os.getenv("FBR_SANDBOX_ITEM_CODE", ""),
    "FBR_ITEM_NAME": os.getenv("FBR_SANDBOX_ITEM_NAME", ""),
}
PRODUCTION = {
    "FBR_API_BASE_URL": os.getenv("FBR_PROD_API_BASE_URL", "https://esp.fbr.gov.pk:8243/PT/v1"),
    "FBR_POS_ID": os.getenv("FBR_PROD_POS_ID", os.getenv("FBR_POS_ID", "")),
    "FBR_USIN": os.getenv("FBR_PROD_USIN", os.getenv("FBR_USIN", "")),
    "FBR_AUTH_TOKEN": os.getenv("FBR_PROD_AUTH_TOKEN", os.getenv("FBR_AUTH_TOKEN", "")),
    "FBR_TAX_RATE": os.getenv("FBR_PROD_TAX_RATE", "18.0"),
    "FBR_PCT_CODE": os.getenv("FBR_PROD_PCT_CODE", "8711.2010"),
    "FBR_INVOICE_TYPE": os.getenv("FBR_PROD_INVOICE_TYPE", "Standard"),
    "FBR_DISCOUNT": os.getenv("FBR_PROD_DISCOUNT", "0.0"),
    "FBR_ITEM_CODE": os.getenv("FBR_PROD_ITEM_CODE", ""),
    "FBR_ITEM_NAME": os.getenv("FBR_PROD_ITEM_NAME", ""),
}

def _pick_env_value(key: str) -> str:
    selected = SANDBOX if FBR_ENV == "SANDBOX" else PRODUCTION
    return selected.get(key) or os.getenv(key, "")

def get_database_url() -> str:
    """Construct database URL from environment variables with professional persistent paths."""
    server = os.getenv("DB_SERVER")
    if server:
        user = os.getenv("DB_USER", "root")
        password = os.getenv("DB_PASSWORD", "")
        port = os.getenv("DB_PORT", "3306")
        name = os.getenv("DB_NAME", "fbr_invoice_uploader")
        encoded_password = urllib.parse.quote_plus(password)
        return f"mysql+pymysql://{user}:{encoded_password}@{server}:{port}/{name}"
    
    # Professional persistent path for SQLite in %APPDATA%
    if sys.platform == "win32":
        app_data = os.getenv("APPDATA")
        db_dir = Path(app_data) / "EhsanTraderFBR"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / "fbr_invoices.db"
        return f"sqlite:///{db_path}"
    
    return os.getenv("DB_URL", "sqlite:///./fbr_invoices.db")

class Settings(BaseModel):
    model_config = ConfigDict(case_sensitive=True)

    APP_NAME: str = "FBR Invoice Uploader"
    FBR_ENV: str = Field(default_factory=lambda: FBR_ENV)
    FBR_API_BASE_URL: str = Field(default_factory=lambda: _pick_env_value("FBR_API_BASE_URL"))
    FBR_POS_ID: str = Field(default_factory=lambda: _pick_env_value("FBR_POS_ID"))
    FBR_USIN: str = Field(default_factory=lambda: _pick_env_value("FBR_USIN"))
    FBR_AUTH_TOKEN: str = Field(default_factory=lambda: _pick_env_value("FBR_AUTH_TOKEN"))
    FBR_TAX_RATE: float = Field(default_factory=lambda: float(_pick_env_value("FBR_TAX_RATE") or 18.0))
    FBR_PCT_CODE: str = Field(default_factory=lambda: _pick_env_value("FBR_PCT_CODE"))
    
    FBR_INVOICE_TYPE: str = Field(default_factory=lambda: _pick_env_value("FBR_INVOICE_TYPE") or "Standard")
    FBR_DISCOUNT: float = Field(default_factory=lambda: float(_pick_env_value("FBR_DISCOUNT") or 0.0))
    FBR_ITEM_CODE: str = Field(default_factory=lambda: _pick_env_value("FBR_ITEM_CODE"))
    FBR_ITEM_NAME: str = Field(default_factory=lambda: _pick_env_value("FBR_ITEM_NAME"))

    DB_URL: str = Field(default_factory=get_database_url)
    LOG_LEVEL: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    ENCRYPTION_KEY: str = Field(default_factory=lambda: os.getenv("ENCRYPTION_KEY", ""))
    HONDA_PORTAL_USERNAME: str = Field(default_factory=lambda: os.getenv("HONDA_PORTAL_USERNAME", ""))
    HONDA_PORTAL_PASSWORD: str = Field(default_factory=lambda: os.getenv("HONDA_PORTAL_PASSWORD", ""))

    # Evolution API Settings
    EVOLUTION_API_URL: str = Field(default_factory=lambda: os.getenv("EVOLUTION_API_URL", ""))
    EVOLUTION_API_KEY: str = Field(default_factory=lambda: os.getenv("EVOLUTION_API_KEY", ""))
    EVOLUTION_INSTANCE_NAME: str = Field(default_factory=lambda: os.getenv("EVOLUTION_INSTANCE_NAME", ""))

settings = Settings()

def reload_settings():
    """Reload settings from .env and re-apply environment selection."""
    global settings, FBR_ENV, SANDBOX, PRODUCTION
    
    load_dotenv(dotenv_path=env_path, override=True)
    
    # Re-read global env vars
    FBR_ENV = os.getenv("FBR_ENV", "SANDBOX").upper()
    
    # Re-construct SANDBOX/PRODUCTION dicts
    SANDBOX.update({
        "FBR_API_BASE_URL": os.getenv("FBR_SANDBOX_API_BASE_URL", "https://esp.fbr.gov.pk:8243/PT/v1"),
        "FBR_POS_ID": os.getenv("FBR_SANDBOX_POS_ID", os.getenv("FBR_POS_ID", "")),
        "FBR_USIN": os.getenv("FBR_SANDBOX_USIN", os.getenv("FBR_USIN", "")),
        "FBR_AUTH_TOKEN": os.getenv("FBR_SANDBOX_AUTH_TOKEN", os.getenv("FBR_AUTH_TOKEN", "")),
        "FBR_TAX_RATE": os.getenv("FBR_SANDBOX_TAX_RATE", "18.0"),
        "FBR_PCT_CODE": os.getenv("FBR_SANDBOX_PCT_CODE", "8711.2010"),
        "FBR_INVOICE_TYPE": os.getenv("FBR_SANDBOX_INVOICE_TYPE", "Standard"),
        "FBR_DISCOUNT": os.getenv("FBR_SANDBOX_DISCOUNT", "0.0"),
        "FBR_ITEM_CODE": os.getenv("FBR_SANDBOX_ITEM_CODE", ""),
        "FBR_ITEM_NAME": os.getenv("FBR_SANDBOX_ITEM_NAME", ""),
    })
    
    PRODUCTION.update({
        "FBR_API_BASE_URL": os.getenv("FBR_PROD_API_BASE_URL", "https://esp.fbr.gov.pk:8243/PT/v1"),
        "FBR_POS_ID": os.getenv("FBR_PROD_POS_ID", os.getenv("FBR_POS_ID", "")),
        "FBR_USIN": os.getenv("FBR_PROD_USIN", os.getenv("FBR_USIN", "")),
        "FBR_AUTH_TOKEN": os.getenv("FBR_PROD_AUTH_TOKEN", os.getenv("FBR_AUTH_TOKEN", "")),
        "FBR_TAX_RATE": os.getenv("FBR_PROD_TAX_RATE", "18.0"),
        "FBR_PCT_CODE": os.getenv("FBR_PROD_PCT_CODE", "8711.2010"),
        "FBR_INVOICE_TYPE": os.getenv("FBR_PROD_INVOICE_TYPE", "Standard"),
        "FBR_DISCOUNT": os.getenv("FBR_PROD_DISCOUNT", "0.0"),
        "FBR_ITEM_CODE": os.getenv("FBR_PROD_ITEM_CODE", ""),
        "FBR_ITEM_NAME": os.getenv("FBR_PROD_ITEM_NAME", ""),
    })

    # Re-initialize the settings object
    settings = Settings()
    return settings
