import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import FBRConfiguration, AppConfiguration
import logging
import time
import threading
from typing import Any, Callable, Dict, Optional
import uuid
from sqlalchemy.exc import SQLAlchemyError
import json

logger = logging.getLogger(__name__)

ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

def should_regenerate_invoice_number(current_invoice_number: str, previous_usin: str, changed_keys: list[str]) -> bool:
    current_inv = (current_invoice_number or "").strip()
    old_usin = (previous_usin or "").strip()
    if "usin" in changed_keys or "env" in changed_keys:
        if not current_inv or current_inv == "ERROR":
            return True
        if old_usin and current_inv.startswith(f"{old_usin}-"):
            return True
    return False

class SettingsService:
    def __init__(self):
        self.env_path = ENV_FILE
        # Removed _initialize_defaults() from __init__ to prevent crash during import
        # It will be called manually after DB connection is verified.
        self._lock = threading.RLock()
        self._active_settings_cache: Optional[Dict[str, Any]] = None
        self._active_settings_cache_loaded_at: float = 0.0
        self._active_environment_cache: Optional[str] = None
        self._active_environment_cache_loaded_at: float = 0.0
        self._observers: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        self._revision: int = 0

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]) -> str:
        token = uuid.uuid4().hex
        with self._lock:
            self._observers[token] = callback
        return token

    def unsubscribe(self, token: str) -> None:
        with self._lock:
            self._observers.pop(token, None)

    def _notify(self, event: Dict[str, Any]) -> None:
        with self._lock:
            callbacks = list(self._observers.values())
        for cb in callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.error(f"Settings observer callback failed: {e}", exc_info=True)

    def _mask_secret(self, value: str) -> str:
        if not value:
            return ""
        v = str(value)
        if len(v) <= 4:
            return "****"
        return f"****{v[-4:]}"

    def _invalidate_cache(self) -> None:
        with self._lock:
            self._active_settings_cache = None
            self._active_settings_cache_loaded_at = 0.0
            self._active_environment_cache = None
            self._active_environment_cache_loaded_at = 0.0

    def _bump_revision(self) -> int:
        with self._lock:
            self._revision += 1
            return self._revision

    def get_revision(self) -> int:
        with self._lock:
            return self._revision

    def _env_prefix(self, env: str) -> str:
        env = (env or "").upper()
        if env == "SANDBOX":
            return "FBR_SANDBOX"
        return "FBR_PROD"

    def _read_fbr_settings_from_env(self, env: str) -> Dict[str, Any]:
        prefix = self._env_prefix(env)
        data = {
            "env": env.upper(),
            "base_url": os.getenv(f"{prefix}_API_BASE_URL", "").strip(),
            "pos_id": os.getenv(f"{prefix}_POS_ID", "").strip(),
            "usin": os.getenv(f"{prefix}_USIN", "").strip(),
            "token": os.getenv(f"{prefix}_AUTH_TOKEN", "").strip(),
            "secret_key": os.getenv(f"{prefix}_SECRET_KEY", "").strip(),
            "tax_rate": os.getenv(f"{prefix}_TAX_RATE", "18.0").strip(),
            "pct_code": os.getenv(f"{prefix}_PCT_CODE", "8711.2010").strip(),
            "invoice_type": os.getenv(f"{prefix}_INVOICE_TYPE", "Standard").strip(),
            "discount": os.getenv(f"{prefix}_DISCOUNT", "0.0").strip(),
            "item_code": os.getenv(f"{prefix}_ITEM_CODE", "").strip(),
            "item_name": os.getenv(f"{prefix}_ITEM_NAME", "").strip(),
            "business_name": os.getenv(f"{prefix}_BUSINESS_NAME", "").strip() or "Ehsan Trader",
        }
        if not data["base_url"]:
            if env.upper() == "SANDBOX":
                data["base_url"] = "https://esp.fbr.gov.pk:8243/PT/v1"
            else:
                data["base_url"] = "https://gw.fbr.gov.pk/imsp/v1/api/Live"
        return data

    def _write_fbr_settings_to_env(
        self,
        env: str,
        *,
        base_url: str,
        pos_id: str,
        usin: str,
        token: str,
        secret_key: str,
        tax_rate: str,
        pct_code: str,
        invoice_type: str,
        discount: str,
        item_code: str,
        item_name: str,
        business_name: str,
    ) -> None:
        env = env.upper()
        prefix = self._env_prefix(env)
        payload = {
            "FBR_ENV": env,
            f"{prefix}_API_BASE_URL": base_url,
            f"{prefix}_POS_ID": pos_id,
            f"{prefix}_USIN": usin,
            f"{prefix}_AUTH_TOKEN": token,
            f"{prefix}_SECRET_KEY": secret_key,
            f"{prefix}_TAX_RATE": str(tax_rate),
            f"{prefix}_PCT_CODE": pct_code,
            f"{prefix}_INVOICE_TYPE": invoice_type,
            f"{prefix}_DISCOUNT": str(discount),
            f"{prefix}_ITEM_CODE": item_code,
            f"{prefix}_ITEM_NAME": item_name,
            f"{prefix}_BUSINESS_NAME": business_name,
        }
        self._write_env(payload)

    def _get_environment_from_db(self, env: str) -> Optional[Dict[str, Any]]:
        env = env.upper()
        db = SessionLocal()
        try:
            config = db.query(FBRConfiguration).filter_by(environment=env).first()
            if not config:
                return None
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
        
        float(tax_rate)
        float(discount)

        before_db = self._get_environment_from_db(env) or {}
        db = SessionLocal()
        saved_to_db = False
        try:
            config = db.query(FBRConfiguration).filter_by(environment=env).first()
            if not config:
                config = FBRConfiguration(environment=env, api_base_url=base_url)
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
            saved_to_db = True
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"DB persistence failed while saving FBR settings for {env}: {e}")
        finally:
            db.close()

        self._write_fbr_settings_to_env(
            env,
            base_url=base_url,
            pos_id=pos_id,
            usin=usin,
            token=token,
            secret_key=secret_key,
            tax_rate=tax_rate,
            pct_code=pct_code,
            invoice_type=invoice_type,
            discount=discount,
            item_code=item_code,
            item_name=item_name,
            business_name=business_name,
        )

        after_db = self._get_environment_from_db(env) if saved_to_db else None
        after_effective = after_db or self._read_fbr_settings_from_env(env)
        changed_keys = [k for k in after_effective.keys() if before_db.get(k) != after_effective.get(k)]

        if saved_to_db and after_db:
            validation_errors = []
            if after_db.get("base_url") != base_url:
                validation_errors.append("base_url")
            if after_db.get("pos_id") != pos_id:
                validation_errors.append("pos_id")
            if after_db.get("usin") != usin:
                validation_errors.append("usin")
            if after_db.get("token") != token:
                validation_errors.append("token")
            if after_db.get("secret_key") != secret_key:
                validation_errors.append("secret_key")
            if after_db.get("pct_code") != pct_code:
                validation_errors.append("pct_code")
            if after_db.get("invoice_type") != invoice_type:
                validation_errors.append("invoice_type")
            if after_db.get("item_code") != item_code:
                validation_errors.append("item_code")
            if after_db.get("item_name") != item_name:
                validation_errors.append("item_name")
            try:
                if float(after_db.get("tax_rate") or 0) != float(tax_rate or 0):
                    validation_errors.append("tax_rate")
            except Exception:
                validation_errors.append("tax_rate")
            try:
                if float(after_db.get("discount") or 0) != float(discount or 0):
                    validation_errors.append("discount")
            except Exception:
                validation_errors.append("discount")

            if validation_errors:
                logger.error(f"FBR settings post-save validation failed for {env}. Fields: {validation_errors}")
                raise RuntimeError(f"Settings validation failed for fields: {', '.join(validation_errors)}")

        safe_snapshot = {
            "env": env,
            "base_url": after_effective.get("base_url"),
            "pos_id": after_effective.get("pos_id"),
            "usin": after_effective.get("usin"),
            "token": self._mask_secret(after_effective.get("token", "")),
            "secret_key": self._mask_secret(after_effective.get("secret_key", "")),
            "tax_rate": after_effective.get("tax_rate"),
            "pct_code": after_effective.get("pct_code"),
            "invoice_type": after_effective.get("invoice_type"),
            "discount": after_effective.get("discount"),
            "item_code": after_effective.get("item_code"),
            "item_name": after_effective.get("item_name"),
            "business_name": after_effective.get("business_name"),
            "db_persisted": saved_to_db,
        }
        logger.info(f"FBR settings saved for {env}. Changed: {changed_keys}. Snapshot: {safe_snapshot}")
        self._invalidate_cache()
        revision = self._bump_revision()
        self._notify({
            "type": "fbr_settings_saved",
            "environment": env,
            "is_active": bool(env == self.get_active_environment()),
            "changed_keys": changed_keys,
            "settings": self.get_environment(env),
            "revision": revision,
            "ts": time.time(),
        })

    def set_active_environment(self, env: str):
        env = env.upper()
        if env not in ("SANDBOX", "PRODUCTION"):
            raise ValueError("Environment must be SANDBOX or PRODUCTION")
        
        before_env = self.get_active_environment()
        db = SessionLocal()
        try:
            db.query(FBRConfiguration).update({"is_active": False})
            config = db.query(FBRConfiguration).filter_by(environment=env).first()
            if config:
                config.is_active = True
                db.commit()
            else:
                logger.warning(f"Configuration for {env} not found.")
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"DB persistence failed while setting active environment to {env}: {e}")
        finally:
            db.close()

        self._write_env({"FBR_ENV": env})
        self._invalidate_cache()
        active_settings = self.get_active_settings()
        logger.info(f"Active environment changed: {before_env} -> {env}")
        revision = self._bump_revision()
        self._notify({
            "type": "fbr_active_environment_changed",
            "before_environment": before_env,
            "environment": env,
            "settings": active_settings,
            "revision": revision,
            "ts": time.time(),
        })

    def get_active_environment(self) -> str:
        with self._lock:
            if self._active_environment_cache and (time.time() - self._active_environment_cache_loaded_at) < 5:
                return self._active_environment_cache

        db = SessionLocal()
        try:
            config = db.query(FBRConfiguration).filter_by(is_active=True).first()
            env = config.environment if config else "SANDBOX"
            with self._lock:
                self._active_environment_cache = env
                self._active_environment_cache_loaded_at = time.time()
            return env
        except Exception as e:
            logger.warning(f"Falling back to env-based active environment due to DB error: {e}")
            env = os.getenv("FBR_ENV", "SANDBOX").upper()
            with self._lock:
                self._active_environment_cache = env
                self._active_environment_cache_loaded_at = time.time()
            return env
        finally:
            db.close()

    def get_environment(self, env: str) -> dict:
        env = env.upper()
        db = SessionLocal()
        try:
            config = db.query(FBRConfiguration).filter_by(environment=env).first()
            if not config:
                return self._read_fbr_settings_from_env(env)
            
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
        except Exception as e:
            logger.warning(f"Falling back to env-based settings for {env} due to DB error: {e}")
            return self._read_fbr_settings_from_env(env)
        finally:
            db.close()
    
    def get_active_settings(self) -> dict:
        """Get the full configuration for the currently active environment."""
        with self._lock:
            if self._active_settings_cache and (time.time() - self._active_settings_cache_loaded_at) < 5:
                return dict(self._active_settings_cache)

        try:
            db = SessionLocal()
            try:
                config = db.query(FBRConfiguration).filter_by(is_active=True).first()
                if not config:
                    config = db.query(FBRConfiguration).filter_by(environment="SANDBOX").first()

                if not config:
                    fallback = self._read_fbr_settings_from_env(self.get_active_environment())
                    with self._lock:
                        self._active_settings_cache = dict(fallback)
                        self._active_settings_cache_loaded_at = time.time()
                    return fallback

                result = {
                    "env": config.environment,
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
                with self._lock:
                    self._active_settings_cache = dict(result)
                    self._active_settings_cache_loaded_at = time.time()
                return result
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to get active settings: {e}")
            fallback = self._read_fbr_settings_from_env(self.get_active_environment())
            with self._lock:
                self._active_settings_cache = dict(fallback)
                self._active_settings_cache_loaded_at = time.time()
            return fallback

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
                "auto_push_interval": config.auto_push_interval,
                "address_shortcodes": config.address_shortcodes or {},
                "urdu_font_enabled": bool(getattr(config, "urdu_font_enabled", False)),
                "urdu_font_family": str(getattr(config, "urdu_font_family", "") or ""),
                "urdu_font_path": str(getattr(config, "urdu_font_path", "") or ""),
                "urdu_font_size": int(getattr(config, "urdu_font_size", 14) or 14),
                "ui_font_enabled": bool(getattr(config, "ui_font_enabled", False)),
                "ui_font_family": str(getattr(config, "ui_font_family", "") or ""),
                "ui_font_size": int(getattr(config, "ui_font_size", 13) or 13),
                "sidebar_font_size": int(getattr(config, "sidebar_font_size", 15) or 15),
                "sidebar_group_font_size": int(getattr(config, "sidebar_group_font_size", 12) or 12),
                "sidebar_header_font_size": int(getattr(config, "sidebar_header_font_size", 18) or 18),
                "sidebar_footer_font_size": int(getattr(config, "sidebar_footer_font_size", 15) or 15),
                "sidebar_exit_font_size": int(getattr(config, "sidebar_exit_font_size", 16) or 16),
                "sidebar_collapsed_font_size": int(getattr(config, "sidebar_collapsed_font_size", 18) or 18),
            }
        except Exception as e:
            logger.error(f"Error getting app config: {e}")
            return {
                "auto_push_enabled": False,
                "auto_push_interval": 5,
                "address_shortcodes": {},
                "urdu_font_enabled": False,
                "urdu_font_family": "",
                "urdu_font_path": "",
                "urdu_font_size": 14,
                "ui_font_enabled": False,
                "ui_font_family": "",
                "ui_font_size": 13,
                "sidebar_font_size": 15,
                "sidebar_group_font_size": 12,
                "sidebar_header_font_size": 18,
                "sidebar_footer_font_size": 15,
                "sidebar_exit_font_size": 16,
                "sidebar_collapsed_font_size": 18,
            }
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

    def get_address_shortcodes(self) -> Dict[str, str]:
        defaults = {
            "KT": "Tehsil Kamalia District Toba Tek Singh",
        }
        try:
            cfg = self.get_app_config() or {}
            raw = cfg.get("address_shortcodes") or {}
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    raw = {}
            if not isinstance(raw, dict):
                raw = {}
            merged: Dict[str, str] = {}
            for k, v in {**defaults, **raw}.items():
                key = str(k or "").strip().upper()
                val = str(v or "").strip()
                if key and val:
                    merged[key] = val
            return merged
        except Exception:
            return defaults

    def set_address_shortcodes(self, shortcodes: Dict[str, str]) -> None:
        payload: Dict[str, str] = {}
        for k, v in (shortcodes or {}).items():
            key = str(k or "").strip().upper()
            val = str(v or "").strip()
            if key and val:
                payload[key] = val

        db = SessionLocal()
        try:
            config = db.query(AppConfiguration).first()
            if not config:
                config = AppConfiguration(auto_push_enabled=False, auto_push_interval=5)
                db.add(config)
                db.flush()
            config.address_shortcodes = payload
            db.commit()
            self._invalidate_cache()
            self._bump_revision()
            self._notify({"type": "address_shortcodes_updated", "shortcodes": dict(payload)})
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving address shortcodes: {e}")
            raise
        finally:
            db.close()

    def set_urdu_font_config(
        self,
        enabled: bool,
        family: str = "Jameel Noori Nastaleeq",
        path: str = "",
        size: int = 14,
    ) -> None:
        db = SessionLocal()
        try:
            config = db.query(AppConfiguration).first()
            if not config:
                config = AppConfiguration(auto_push_enabled=False, auto_push_interval=5)
                db.add(config)
                db.flush()

            config.urdu_font_enabled = bool(enabled)
            config.urdu_font_family = str(family or "").strip()
            config.urdu_font_path = str(path or "").strip()
            config.urdu_font_size = int(size or 14)
            db.commit()
            self._invalidate_cache()
            self._bump_revision()
            self._notify(
                {
                    "type": "urdu_font_updated",
                    "enabled": config.urdu_font_enabled,
                    "family": config.urdu_font_family,
                    "path": config.urdu_font_path,
                    "size": config.urdu_font_size,
                }
            )
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving Urdu font config: {e}")
            raise
        finally:
            db.close()

    def set_ui_font_config(
        self,
        enabled: bool,
        family: str,
        size: int,
        sidebar_font_size: int,
        sidebar_group_font_size: int,
        sidebar_header_font_size: int,
        sidebar_footer_font_size: int,
        sidebar_exit_font_size: int,
        sidebar_collapsed_font_size: int,
    ) -> None:
        db = SessionLocal()
        try:
            config = db.query(AppConfiguration).first()
            if not config:
                config = AppConfiguration(auto_push_enabled=False, auto_push_interval=5)
                db.add(config)
                db.flush()

            config.ui_font_enabled = bool(enabled)
            config.ui_font_family = str(family or "").strip()
            config.ui_font_size = int(size or 13)
            config.sidebar_font_size = int(sidebar_font_size or 15)
            config.sidebar_group_font_size = int(sidebar_group_font_size or 12)
            config.sidebar_header_font_size = int(sidebar_header_font_size or 18)
            config.sidebar_footer_font_size = int(sidebar_footer_font_size or 15)
            config.sidebar_exit_font_size = int(sidebar_exit_font_size or 16)
            config.sidebar_collapsed_font_size = int(sidebar_collapsed_font_size or 18)

            db.commit()
            self._invalidate_cache()
            self._bump_revision()
            self._notify(
                {
                    "type": "ui_font_updated",
                    "enabled": config.ui_font_enabled,
                    "family": config.ui_font_family,
                    "size": config.ui_font_size,
                    "sidebar_font_size": config.sidebar_font_size,
                    "sidebar_group_font_size": config.sidebar_group_font_size,
                    "sidebar_header_font_size": config.sidebar_header_font_size,
                    "sidebar_footer_font_size": config.sidebar_footer_font_size,
                    "sidebar_exit_font_size": config.sidebar_exit_font_size,
                    "sidebar_collapsed_font_size": config.sidebar_collapsed_font_size,
                }
            )
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving UI font config: {e}")
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
                    "invoice_template": "Hello {customer}, your invoice {invoice_no} for Rs. {amount} has been generated. FBR ID: {fbr_id}",
                    "booking_template": "Dear {customer}, your booking for {model} ({color}) is confirmed. Booking #: {booking_no}. Paid: Rs. {paid}. Balance: Rs. {balance}."
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
                "invoice_template": config.invoice_template,
                "booking_template": getattr(config, 'booking_template', "")
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
