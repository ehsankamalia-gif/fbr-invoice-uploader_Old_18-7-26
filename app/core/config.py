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
        # Installed EXE: the install folder (often Program Files) is not
        # writable, so settings live in the per-user data folder. An .env
        # placed next to the EXE still wins, which keeps portable/USB setups
        # and existing installs working.
        beside_exe = Path(sys.executable).parent / ".env"
        if beside_exe.exists():
            return beside_exe

        from app.core.paths import data_dir

        return data_dir() / ".env"
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

def _sqlite_fallback_url() -> str:
    """Persistent per-user SQLite path, used when no database server is present."""
    if sys.platform == "win32":
        app_data = os.getenv("APPDATA")
        db_dir = Path(app_data) / "EhsanTraderFBR"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / "fbr_invoices.db"
        return f"sqlite:///{db_path}"

    return os.getenv("DB_URL", "sqlite:///./fbr_invoices.db")


def _mysql_url() -> str:
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")
    server = os.getenv("DB_SERVER")
    port = os.getenv("DB_PORT", "3306")
    name = os.getenv("DB_NAME", "fbr_invoice_uploader")
    encoded_password = urllib.parse.quote_plus(password)
    return f"mysql+pymysql://{user}:{encoded_password}@{server}:{port}/{name}"


def _server_is_listening(host: str, port: str, timeout: float = 1.5) -> bool:
    """Cheap TCP probe so a missing Laragon/XAMPP doesn't block startup."""
    import socket

    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def _backend_marker_path() -> Path:
    from app.core.paths import data_path

    return data_path("db_backend.json")


def _remembered_backend() -> str:
    """Returns 'mysql' once this install has successfully used a MySQL server.

    This matters for safety: if the machine already keeps its data in MySQL and
    the server merely isn't running yet, we must NOT quietly switch to an empty
    SQLite file. In that case the existing connection-error path is correct.
    """
    try:
        marker = _backend_marker_path()
        if marker.exists():
            import json

            return str(json.loads(marker.read_text()).get("backend") or "")
    except Exception:
        pass
    return ""


def remember_backend(backend: str) -> None:
    """Records the backend after a verified successful connection."""
    try:
        import json

        _backend_marker_path().write_text(json.dumps({"backend": backend}, indent=2))
    except Exception:
        pass


_DB_URL_CACHE: str | None = None


def get_database_url() -> str:
    """Construct database URL, auto-detecting a local MySQL server (Laragon/XAMPP).

    Precedence:
      1. DB_SERVER configured and the server answers  -> MySQL (database is
         created automatically by app.db.session.create_mysql_db_if_missing)
      2. DB_SERVER configured, server silent, but this install previously used
         MySQL -> still MySQL, so the user gets a clear "start your server"
         error rather than a silently empty database
      3. Otherwise -> per-user SQLite, so the app runs on a machine with no
         database server installed at all
    """
    global _DB_URL_CACHE
    if _DB_URL_CACHE:
        return _DB_URL_CACHE

    server = os.getenv("DB_SERVER")
    if server:
        port = os.getenv("DB_PORT", "3306")
        if _server_is_listening(server, port) or _remembered_backend() == "mysql":
            _DB_URL_CACHE = _mysql_url()
            return _DB_URL_CACHE

    _DB_URL_CACHE = _sqlite_fallback_url()
    return _DB_URL_CACHE


def reset_database_url_cache() -> None:
    """Forces re-detection, e.g. after database settings are changed in the UI."""
    global _DB_URL_CACHE
    _DB_URL_CACHE = None

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

    # Update System
    APP_UPDATE_URL: str = Field(default_factory=lambda: os.getenv("APP_UPDATE_URL", "https://bitbucket.org/python_desktop/python_repository/raw/main/version.json"))

settings = Settings()

def reload_settings():
    """Reload settings from .env and re-apply environment selection."""
    global settings, FBR_ENV, SANDBOX, PRODUCTION
    
    load_dotenv(dotenv_path=env_path, override=True)

    # Database settings may have changed; re-detect on next lookup.
    reset_database_url_cache()

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
