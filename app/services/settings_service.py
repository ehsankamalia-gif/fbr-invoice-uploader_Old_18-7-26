import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import FBRConfiguration, AppConfiguration
import logging
import time

logger = logging.getLogger(__name__)

ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

class SettingsService:
    def __init__(self):
        self.env_path = ENV_FILE
        # Removed _initialize_defaults() from __init__ to prevent crash during import
        # It will be called manually after DB connection is verified.

    def initialize_if_connected(self):
        """Public method to safely initialize defaults after DB is ready."""
        try:
            self._initialize_defaults()
        except Exception as e:
            logger.error(f"Safe initialization failed: {e}")

    def _initialize_defaults(self):
        """Initialize default configurations in DB if they don't exist."""
        db = SessionLocal()
        try:
            # Check for SANDBOX
            sandbox = db.query(FBRConfiguration).filter_by(environment="SANDBOX").first()
            if not sandbox:
                sandbox = FBRConfiguration(
                    environment="SANDBOX",
                    is_active=True,
                    api_base_url="https://esp.fbr.gov.pk:8243/PT/v1",
                    pos_id="",
                    usin="",
                    auth_token="",
                    secret_key="",
                    tax_rate=18.0,
                    invoice_type="Standard",
                    discount=0.0,
                    pct_code="8711.2010"
                )
                db.add(sandbox)
            
            # Check for PRODUCTION
            prod = db.query(FBRConfiguration).filter_by(environment="PRODUCTION").first()
            if not prod:
                prod = FBRConfiguration(
                    environment="PRODUCTION",
                    is_active=False,
                    api_base_url="https://gw.fbr.gov.pk/imsp/v1/api/Live",
                    pos_id="",
                    usin="",
                    auth_token="",
                    secret_key="",
                    tax_rate=18.0,
                    invoice_type="Standard",
                    discount=0.0,
                    pct_code="8711.2010"
                )
                db.add(prod)
            else:
                # Fix for incorrect default URL if present (Auto-Correction)
                # Known bad URLs: imfs/v1, or without api/Live
                if prod.api_base_url in ["https://gw.fbr.gov.pk/imfs/v1", "https://gw.fbr.gov.pk/imfs/v1/PostData"]:
                    prod.api_base_url = "https://gw.fbr.gov.pk/imsp/v1/api/Live"
                    logger.info("Auto-corrected Production API URL to https://gw.fbr.gov.pk/imsp/v1/api/Live")
                    # Ensure we don't overwrite user customizations if they are different, 
                    # but here we specifically target the known bad default we shipped.
            
            db.commit()
        except Exception as e:
            logger.error(f"Failed to initialize default settings: {e}")
            db.rollback()
        finally:
            db.close()

    def _read_env(self) -> dict:
        """Legacy method for Honda credentials only."""
        data = {}
        if self.env_path.exists():
            for line in self.env_path.read_text(encoding="utf-8").splitlines():
                if not line or line.strip().startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    data[k.strip()] = v.strip()
        return data

    def _write_env(self, items: dict):
        """Legacy method for Honda credentials only."""
        existing = self._read_env()
        existing.update(items)
        lines = [f"{k}={existing[k]}" for k in sorted(existing.keys())]
        self.env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        load_dotenv(dotenv_path=self.env_path, override=True)

    def save_environment(self, env: str, base_url: str, pos_id: str, usin: str, token: str, tax_rate: str, pct_code: str, 
                         invoice_type: str, discount: str, item_code: str, item_name: str, secret_key: str = "", business_name: str = "Ehsan Trader"):
        env = env.upper()
        if env not in ("SANDBOX", "PRODUCTION"):
            raise ValueError("Environment must be SANDBOX or PRODUCTION")
        
        db = SessionLocal()
        try:
            config = db.query(FBRConfiguration).filter_by(environment=env).first()
            if not config:
                config = FBRConfiguration(environment=env)
                db.add(config)
            
            config.api_base_url = base_url
            config.pos_id = pos_id
            config.usin = usin
            config.auth_token = token
            config.secret_key = secret_key
            config.tax_rate = float(tax_rate)
            config.pct_code = pct_code
            config.invoice_type = invoice_type
            config.discount = float(discount)
            config.item_code = item_code
            config.item_name = item_name
            config.business_name = business_name
            
            db.commit()
            logger.info(f"Updated settings for {env}")
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving settings: {e}")
            raise
        finally:
            db.close()

    def set_active_environment(self, env: str):
        env = env.upper()
        if env not in ("SANDBOX", "PRODUCTION"):
            raise ValueError("Environment must be SANDBOX or PRODUCTION")
        
        db = SessionLocal()
        try:
            # Set all to inactive first
            db.query(FBRConfiguration).update({"is_active": False})
            
            # Set selected to active
            config = db.query(FBRConfiguration).filter_by(environment=env).first()
            if config:
                config.is_active = True
                db.commit()
                logger.info(f"Active environment set to {env}")
            else:
                logger.warning(f"Configuration for {env} not found.")
        except Exception as e:
            db.rollback()
            logger.error(f"Error setting active environment: {e}")
            raise
        finally:
            db.close()

    def get_active_environment(self) -> str:
        db = SessionLocal()
        try:
            config = db.query(FBRConfiguration).filter_by(is_active=True).first()
            return config.environment if config else "SANDBOX"
        finally:
            db.close()

    def get_environment(self, env: str) -> dict:
        env = env.upper()
        db = SessionLocal()
        try:
            config = db.query(FBRConfiguration).filter_by(environment=env).first()
            if not config:
                return {}
            
            return {
                "env": env,
                "base_url": config.api_base_url,
                "pos_id": config.pos_id,
                "usin": config.usin,
                "token": config.auth_token,
                "secret_key": config.secret_key,
                "tax_rate": str(config.tax_rate),
                "pct_code": config.pct_code,
                "invoice_type": config.invoice_type,
                "discount": str(config.discount),
                "item_code": config.item_code,
                "item_name": config.item_name,
                "business_name": config.business_name or "Ehsan Trader",
            }
        finally:
            db.close()
    
    def get_active_settings(self) -> dict:
        """Get the full configuration for the currently active environment."""
        try:
            db = SessionLocal()
            try:
                config = db.query(FBRConfiguration).filter_by(is_active=True).first()
                if not config:
                    # Fallback to SANDBOX if no active env found
                    config = db.query(FBRConfiguration).filter_by(environment="SANDBOX").first()
                
                if not config:
                    return self._get_fallback_settings()
                
                return {
                    "env": config.environment,
                    "base_url": config.api_base_url,
                    "pos_id": config.pos_id,
                    "usin": config.usin,
                    "token": config.auth_token,
                    "secret_key": config.secret_key, # Added secret_key
                    "tax_rate": str(config.tax_rate),
                    "pct_code": config.pct_code,
                    "invoice_type": config.invoice_type,
                    "discount": str(config.discount),
                    "item_code": config.item_code,
                    "item_name": config.item_name,
                    "business_name": config.business_name or "Ehsan Trader",
                }
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to get active settings: {e}")
            return self._get_fallback_settings()

    def _get_fallback_settings(self) -> dict:
        """Returns standard default settings when DB is unavailable."""
        return {
            "env": "SANDBOX",
            "base_url": "https://esp.fbr.gov.pk:8243/PT/v1",
            "pos_id": "",
            "usin": "",
            "token": "",
            "secret_key": "", # Added secret_key
            "tax_rate": "18.0",
            "pct_code": "8711.2010",
            "invoice_type": "Standard",
            "discount": "0.0",
            "item_code": "",
            "item_name": "",
            "business_name": "Ehsan Trader",
        }

    def get_all_settings(self) -> dict:
        return {
            "active": self.get_active_environment(),
            "sandbox": self.get_environment("SANDBOX"),
            "production": self.get_environment("PRODUCTION"),
        }

    def save_honda_credentials(self, username: str, password: str):
        """Save Honda Portal credentials to .env file."""
        self._write_env({
            "HONDA_PORTAL_USERNAME": username,
            "HONDA_PORTAL_PASSWORD": password
        })

    def get_db_settings(self) -> dict:
        """Get database connection settings from .env file."""
        env_vars = self._read_env()
        return {
            "server": env_vars.get("DB_SERVER", "localhost"),
            "port": env_vars.get("DB_PORT", "3306"),
            "name": env_vars.get("DB_NAME", "fbr_invoice_uploader"),
            "user": env_vars.get("DB_USER", "root"),
            "password": env_vars.get("DB_PASSWORD", "")
        }

    def save_db_settings(self, server, port, name, user, password):
        """Save database connection settings to .env file."""
        self._write_env({
            "DB_SERVER": server,
            "DB_PORT": port,
            "DB_NAME": name,
            "DB_USER": user,
            "DB_PASSWORD": password
        })

    def get_app_config(self) -> dict:
        """Get general application settings."""
        db = SessionLocal()
        try:
            config = db.query(AppConfiguration).first()
            if not config:
                # Initialize default app config if missing
                config = AppConfiguration(auto_push_enabled=False, auto_push_interval=5)
                db.add(config)
                db.commit()
            
            return {
                "auto_push_enabled": config.auto_push_enabled,
                "auto_push_interval": config.auto_push_interval
            }
        except Exception as e:
            logger.error(f"Error getting app config: {e}")
            return {"auto_push_enabled": False, "auto_push_interval": 5}
        finally:
            db.close()

    def set_app_config(self, auto_push_enabled: bool, auto_push_interval: int = 5):
        """Update general application settings."""
        db = SessionLocal()
        try:
            config = db.query(AppConfiguration).first()
            if not config:
                config = AppConfiguration()
                db.add(config)
            
            config.auto_push_enabled = auto_push_enabled
            config.auto_push_interval = auto_push_interval
            db.commit()
            logger.info(f"Updated app config: auto_push={auto_push_enabled}")
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving app config: {e}")
            raise
        finally:
            db.close()

    def get_sms_config(self) -> dict:
        """Get SMS configuration from database."""
        db = SessionLocal()
        try:
            from app.db.models import SMSConfiguration
            config = db.query(SMSConfiguration).first()
            if not config:
                # Default settings
                return {
                    "is_enabled": False,
                    "gateway_type": "WIFI",
                    "gateway_ip": "",
                    "gateway_port": "8080",
                    "api_key": "",
                    "api_url": "",
                    "use_https": False,
                    "invoice_template": "Hello {customer}, your invoice {invoice_no} for Rs. {amount} has been generated. FBR ID: {fbr_id}"
                }
            
            return {
                "is_enabled": config.is_enabled,
                "gateway_type": config.gateway_type,
                "gateway_ip": config.gateway_ip,
                "gateway_port": config.gateway_port,
                "gateway_username": getattr(config, 'gateway_username', ""),
                "gateway_password": getattr(config, 'gateway_password', ""),
                "use_https": config.use_https,
                "api_url": config.api_url,
                "cloud_username": getattr(config, 'cloud_username', ""),
                "cloud_password": getattr(config, 'cloud_password', ""),
                "api_key": config.api_key,
                "invoice_template": config.invoice_template
            }
        except Exception as e:
            logger.error(f"Error getting SMS config: {e}")
            return {}
        finally:
            db.close()

    def save_sms_config(self, **kwargs):
        """Update SMS configuration in database with robust attribute validation."""
        db = SessionLocal()
        try:
            from app.db.models import SMSConfiguration
            config = db.query(SMSConfiguration).first()
            if not config:
                config = SMSConfiguration()
                db.add(config)
            
            # Use setattr for each valid attribute in the model
            for key, value in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, value)
                else:
                    logger.warning(f"SMSConfiguration model has no attribute '{key}'. Skipping.")
            
            db.commit()
            logger.info("Updated SMS configuration successfully.")
        except Exception as e:
            db.rollback()
            logger.error(f"CRITICAL: Error saving SMS/WhatsApp configuration: {e}", exc_info=True)
            raise RuntimeError(f"Failed to save settings: {str(e)}")
        finally:
            db.close()

settings_service = SettingsService()
