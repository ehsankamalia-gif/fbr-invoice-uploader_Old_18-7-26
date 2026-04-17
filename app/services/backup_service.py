import os
import shutil
import json
import sys
import time
import logging
import hashlib
import threading
import zipfile
import subprocess
import urllib.parse
import base64
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
from app.core.config import settings

# Optional dependencies with graceful fallback
try:
    import schedule
except ImportError:
    schedule = None

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import hashes, hmac
    from cryptography.hazmat.backends import default_backend
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    Cipher = None
    algorithms = None
    modes = None
    hashes = None
    hmac = None
    default_backend = None
    InvalidSignature = None
    PBKDF2HMAC = None

try:
    import platformdirs
except ImportError:
    platformdirs = None

logger = logging.getLogger(__name__)

# Constants
APP_NAME = "fbr_invoice_uploader"
BACKUP_DIR_NAME = "backups"
CONFIG_FILE_NAME = "backup_config.json"

class BackupConfig:
    def __init__(self, 
                 enabled: bool = False,
                 interval: str = "daily",
                 time_str: str = "00:00",
                 local_path: str = "",
                 cloud_path: str = "",
                 retention_days: int = 30,
                 encrypt: bool = True,
                 encryption_key: str = "",
                 encryption_keys: Optional[List[Dict]] = None,
                 active_key_id: str = "",
                 backup_mode: str = "full",
                 compression: str = "zip",
                 compression_level: int = 6,
                 retention_policy: Optional[Dict] = None,
                 retention_policy_enabled: bool = False,
                 destinations: Optional[List[Dict]] = None,
                 key_rotation_days: int = 90,
                 bandwidth_limit_mbps: Optional[float] = None,
                 parallelism: int = 2,
                 pre_backup_script: str = "",
                 post_backup_script: str = "",
                 verify_after_backup: bool = True):
        self.enabled = enabled
        self.interval = interval
        self.time_str = time_str
        self.local_path = local_path
        self.cloud_path = cloud_path
        self.retention_days = retention_days
        self.encrypt = encrypt
        self.encryption_key = encryption_key
        self.encryption_keys = encryption_keys or []
        self.active_key_id = active_key_id
        self.backup_mode = backup_mode
        self.compression = compression
        self.compression_level = int(compression_level or 6)
        self.retention_policy = retention_policy or {
            "hourly": {"keep": 24},
            "daily": {"keep": 30},
            "weekly": {"keep": 12},
            "monthly": {"keep": 24},
            "yearly": {"keep": 7},
        }
        self.retention_policy_enabled = bool(retention_policy_enabled)
        self.destinations = destinations or []
        self.key_rotation_days = int(key_rotation_days or 90)
        self.bandwidth_limit_mbps = bandwidth_limit_mbps
        self.parallelism = int(parallelism or 2)
        self.pre_backup_script = pre_backup_script
        self.post_backup_script = post_backup_script
        self.verify_after_backup = bool(verify_after_backup)

    @classmethod
    def from_dict(cls, data: Dict):
        d = dict(data or {})
        if "retention_policy_enabled" not in d:
            d["retention_policy_enabled"] = "retention_policy" in d
        return cls(**d)

    def to_dict(self):
        return self.__dict__

class BackupService:
    def __init__(self):
        if platformdirs:
            self.app_data_dir = Path(platformdirs.user_data_dir(APP_NAME, appauthor=False))
        else:
            self.app_data_dir = Path.home() / f".{APP_NAME}"
            
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        
        self.config_file = self.app_data_dir / CONFIG_FILE_NAME
        self.config = self.load_config()
        
        # Ensure local path exists or set default
        if not self.config.local_path:
            self.config.local_path = str(self.app_data_dir / BACKUP_DIR_NAME)
            self.save_config()
            
        self._ensure_key()
        self.scheduler_thread = None
        self.stop_event = threading.Event()
        self._operation_lock = threading.Lock() # Prevent simultaneous backup/restore operations

    def get_config(self) -> Dict:
        """Returns the current configuration as a dictionary."""
        return {
            "backup_path": self.config.local_path,
            "auto_backup": self.config.enabled,
            "interval": self.config.interval,
            "backup_time": self.config.time_str,
            "retention_days": self.config.retention_days,
            "encrypt": self.config.encrypt
        }

    def update_config(self, backup_path: str = None, auto_backup: bool = None, 
                      interval: str = None, backup_time: str = None, 
                      retention_days: int = None, encrypt: bool = None):
        """Updates and saves the configuration."""
        if backup_path is not None: self.config.local_path = backup_path
        if auto_backup is not None: self.config.enabled = auto_backup
        if interval is not None: self.config.interval = interval
        if backup_time is not None: self.config.time_str = backup_time
        if retention_days is not None: self.config.retention_days = retention_days
        if encrypt is not None: self.config.encrypt = encrypt
        
        self.save_config()
        
        # Restart scheduler if needed
        if self.config.enabled:
            self.start_scheduler()
        else:
            self.stop_scheduler()

    def delete_backup(self, path_str: str) -> bool:
        """Deletes a backup file."""
        try:
            path = Path(path_str)
            if path.exists():
                os.remove(path)
                logger.info(f"Deleted backup: {path.name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete backup {path_str}: {e}")
            return False

    def load_config(self) -> BackupConfig:
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                return BackupConfig.from_dict(data)
            except Exception as e:
                logger.error(f"Failed to load backup config: {e}")
        return BackupConfig()

    def save_config(self):
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config.to_dict(), f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save backup config: {e}")

    def _ensure_key(self):
        """Ensures an encryption key exists if encryption is enabled."""
        if not self.config.encrypt:
            return
        if Cipher is None:
            logger.warning("Encryption enabled but cryptography module missing.")
            return

        now = datetime.utcnow()
        def is_valid_key_b64(s: str) -> bool:
            try:
                b = base64.urlsafe_b64decode((s or "").encode())
                return len(b) == 32
            except Exception:
                return False

        if self.config.encryption_keys:
            if not self.config.active_key_id:
                self.config.active_key_id = str(self.config.encryption_keys[-1].get("id") or "")
                self.save_config()
                return

            active = next((k for k in self.config.encryption_keys if str(k.get("id")) == str(self.config.active_key_id)), None)
            if not active or not is_valid_key_b64(str(active.get("key") or "")):
                key_id = secrets.token_hex(8)
                key_b64 = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
                self.config.encryption_keys.append({"id": key_id, "created_at": now.isoformat(), "key": key_b64})
                self.config.active_key_id = key_id
                self.config.encryption_key = key_b64
                self.save_config()
                return
            created_at = None
            if active and active.get("created_at"):
                try:
                    created_at = datetime.fromisoformat(str(active["created_at"]))
                except Exception:
                    created_at = None
            if created_at and (now - created_at).days >= int(self.config.key_rotation_days or 90):
                key_id = secrets.token_hex(8)
                key_b64 = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
                self.config.encryption_keys.append({"id": key_id, "created_at": now.isoformat(), "key": key_b64})
                self.config.active_key_id = key_id
                self.save_config()
            return

        if self.config.encryption_key:
            key_id = secrets.token_hex(8)
            key_b64 = self.config.encryption_key if is_valid_key_b64(self.config.encryption_key) else base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
            self.config.encryption_keys = [{"id": key_id, "created_at": now.isoformat(), "key": key_b64}]
            self.config.active_key_id = key_id
            self.config.encryption_key = key_b64
            self.save_config()
            return

        key_id = secrets.token_hex(8)
        key_b64 = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
        self.config.encryption_keys = [{"id": key_id, "created_at": now.isoformat(), "key": key_b64}]
        self.config.active_key_id = key_id
        self.config.encryption_key = key_b64
        self.save_config()

    def rotate_encryption_key_now(self) -> Dict:
        if not self.config.encrypt:
            return {"success": False, "message": "Encryption is disabled."}
        if Cipher is None:
            return {"success": False, "message": "cryptography module missing."}

        now = datetime.utcnow()
        key_id = secrets.token_hex(8)
        key_b64 = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()

        self.config.encryption_keys = list(self.config.encryption_keys or [])
        self.config.encryption_keys.append({"id": key_id, "created_at": now.isoformat(), "key": key_b64})
        self.config.active_key_id = key_id
        self.config.encryption_key = key_b64
        self.save_config()
        return {"success": True, "message": "Encryption key rotated.", "active_key_id": key_id}

    def get_encryption_status(self) -> Dict:
        active = str(getattr(self.config, "active_key_id", "") or "")
        keys = list(getattr(self.config, "encryption_keys", None) or [])
        created_at = ""
        for k in keys:
            if str(k.get("id") or "") == active:
                created_at = str(k.get("created_at") or "")
                break
        return {
            "encrypt": bool(getattr(self.config, "encrypt", False)),
            "active_key_id": active,
            "active_key_created_at": created_at,
            "key_rotation_days": int(getattr(self.config, "key_rotation_days", 90) or 90),
            "key_count": len(keys),
        }

    def _derive_key_from_passphrase(self, passphrase: str, salt: bytes, iterations: int) -> bytes:
        if PBKDF2HMAC is None or hashes is None or default_backend is None:
            raise ValueError("cryptography module missing.")
        if not passphrase:
            raise ValueError("Passphrase is required.")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=int(iterations),
            backend=default_backend(),
        )
        return kdf.derive(passphrase.encode("utf-8"))

    def export_encryption_keys(self, export_path: str, passphrase: str) -> Dict:
        if Cipher is None or hmac is None or hashes is None or default_backend is None:
            return {"success": False, "message": "cryptography module missing."}

        self._ensure_key()
        keys = list(getattr(self.config, "encryption_keys", None) or [])
        active = str(getattr(self.config, "active_key_id", "") or "")
        if not keys or not active:
            return {"success": False, "message": "No encryption keys are configured to export."}

        payload = {
            "schema": "fbr_backup_keybundle_v1",
            "exported_at": datetime.utcnow().isoformat(),
            "active_key_id": active,
            "encryption_keys": keys,
        }
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        salt = secrets.token_bytes(16)
        iv = secrets.token_bytes(16)
        iterations = 200_000
        key = self._derive_key_from_passphrase(passphrase, salt=salt, iterations=iterations)

        cipher = Cipher(algorithms.AES(key), modes.CTR(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        ct = encryptor.update(raw) + encryptor.finalize()

        mac = hmac.HMAC(key, hashes.SHA256(), backend=default_backend())
        header = b"FBRKEY01" + bytes([1]) + salt + iv + int(iterations).to_bytes(4, "big")
        mac.update(header)
        mac.update(ct)
        tag = mac.finalize()

        out_path = Path(export_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(header)
            f.write(ct)
            f.write(tag)

        return {"success": True, "message": "Key bundle exported successfully.", "path": str(out_path)}

    def import_encryption_keys(self, import_path: str, passphrase: str) -> Dict:
        if Cipher is None or hmac is None or hashes is None or default_backend is None:
            return {"success": False, "message": "cryptography module missing."}

        p = Path(import_path)
        if not p.exists():
            return {"success": False, "message": "Key bundle file not found."}

        data = p.read_bytes()
        if len(data) < 8 + 1 + 16 + 16 + 4 + 32:
            return {"success": False, "message": "Invalid key bundle file."}

        magic = data[:8]
        if magic != b"FBRKEY01":
            return {"success": False, "message": "Invalid key bundle format."}
        ver = data[8]
        if ver != 1:
            return {"success": False, "message": "Unsupported key bundle version."}

        salt = data[9:25]
        iv = data[25:41]
        iterations = int.from_bytes(data[41:45], "big")
        tag = data[-32:]
        ct = data[45:-32]

        key = self._derive_key_from_passphrase(passphrase, salt=salt, iterations=iterations)

        mac = hmac.HMAC(key, hashes.SHA256(), backend=default_backend())
        header = b"FBRKEY01" + bytes([1]) + salt + iv + int(iterations).to_bytes(4, "big")
        mac.update(header)
        mac.update(ct)
        try:
            mac.verify(tag)
        except Exception:
            return {"success": False, "message": "Invalid passphrase or key bundle file is corrupted."}

        cipher = Cipher(algorithms.AES(key), modes.CTR(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        raw = decryptor.update(ct) + decryptor.finalize()

        try:
            payload = json.loads(raw.decode("utf-8")) or {}
        except Exception:
            return {"success": False, "message": "Key bundle payload is invalid."}

        if payload.get("schema") != "fbr_backup_keybundle_v1":
            return {"success": False, "message": "Unsupported key bundle schema."}

        imported_keys = payload.get("encryption_keys") or []
        imported_active = str(payload.get("active_key_id") or "")
        if not isinstance(imported_keys, list) or not imported_keys:
            return {"success": False, "message": "No keys found in the bundle."}

        existing = list(getattr(self.config, "encryption_keys", None) or [])
        existing_ids = {str(k.get("id") or "") for k in existing if isinstance(k, dict)}

        added = 0
        for k in imported_keys:
            if not isinstance(k, dict):
                continue
            kid = str(k.get("id") or "")
            kval = str(k.get("key") or "")
            if not kid or not kval:
                continue
            if kid in existing_ids:
                continue
            existing.append(k)
            existing_ids.add(kid)
            added += 1

        self.config.encryption_keys = existing
        if not str(getattr(self.config, "active_key_id", "") or "") and imported_active:
            self.config.active_key_id = imported_active
        if imported_active:
            self.config.active_key_id = str(self.config.active_key_id or imported_active)
        if self.config.active_key_id:
            active_obj = next((x for x in existing if str(x.get("id") or "") == str(self.config.active_key_id)), None)
            if active_obj and active_obj.get("key"):
                self.config.encryption_key = str(active_obj.get("key"))

        self.save_config()
        return {"success": True, "message": f"Keys imported successfully. Added {added} key(s).", "added": added}

    def get_db_path(self) -> Optional[Path]:
        """Extracts DB path from settings, handling both absolute and relative SQLite paths."""
        db_url = settings.DB_URL
        if not db_url:
            logger.error("DB_URL is empty in settings.")
            return None

        if "mysql" in db_url.lower():
            logger.info("MySQL detected. No physical file path for database.")
            return None

        if "sqlite" in db_url.lower():
            # Format usually: sqlite:///C:/path/to/db or sqlite:////C:/path/to/db
            # Remove protocol prefix
            path_str = db_url.split(":///")[-1]
            
            # 1. Clean leading slashes for Windows (e.g. /C:/ -> C:/)
            if sys.platform == "win32" and len(path_str) > 2:
                if path_str[0] == "/" and path_str[2] == ":":
                    path_str = path_str[1:]
                elif path_str[0] == "/" and path_str[1] == "/": # Handle cases like ////
                    path_str = path_str.lstrip("/")
            
            # Normalize slashes
            path_str = path_str.replace("/", os.sep).replace("\\", os.sep)
            db_path = Path(path_str)
            
            # 2. Return absolute path if it exists
            if db_path.is_absolute():
                return db_path.resolve()
                
            # 3. Fallback: resolve relative to project root
            # Find project root relative to this file (app/services/backup_service.py)
            project_root = Path(__file__).resolve().parent.parent.parent
            return (project_root / path_str).resolve()
            
        logger.warning(f"Unsupported database protocol in URL: {db_url}")
        return None

    def _get_mysql_config(self) -> Dict:
        """Parses MySQL URL to get connection details."""
        # Format: mysql+pymysql://user:pass@host:port/dbname
        url = urllib.parse.urlparse(settings.DB_URL)
        return {
            "user": urllib.parse.unquote(url.username or "root"),
            "password": urllib.parse.unquote(url.password or ""),
            "host": url.hostname or "localhost",
            "port": url.port or 3306,
            "database": url.path.lstrip('/')
        }
    
    def _find_mysql_tool(self, tool_name: str) -> Optional[str]:
        """Finds mysqldump or mysql executable."""
        # 1. Check PATH
        path_tool = shutil.which(tool_name)
        if path_tool:
            return path_tool
            
        # 2. Dynamic Search for Laragon in parent directories
        current_path = Path.cwd()
        # Search up to root
        for parent in [current_path] + list(current_path.parents):
            if parent.name.lower() == "laragon":
                # Found Laragon root
                mysql_bin = parent / "bin" / "mysql"
                if mysql_bin.exists():
                    # Find latest version
                    versions = sorted(mysql_bin.glob("mysql-*"), reverse=True)
                    for v in versions:
                        tool_path = v / "bin" / f"{tool_name}.exe"
                        if tool_path.exists():
                            return str(tool_path)

        # 3. Check common Laragon paths (Hardcoded fallbacks)
        common_drives = ["C:", "D:", "E:", "F:", "G:"]
        for drive in common_drives:
             laragon_path = Path(f"{drive}/laragon/bin/mysql")
             if laragon_path.exists():
                versions = sorted(laragon_path.glob("mysql-*"), reverse=True)
                for v in versions:
                    tool_path = v / "bin" / f"{tool_name}.exe"
                    if tool_path.exists():
                        return str(tool_path)
        
        return None

    def _backup_mysql(self, backup_dir: Path, backup_name: str) -> Optional[Path]:
        """Performs professional MySQL dump with robust security and logging."""
        config = self._get_mysql_config()
        mysqldump = self._find_mysql_tool("mysqldump")
        
        if not mysqldump:
            raise Exception("mysqldump not found. Please ensure MySQL is installed and accessible.")
            
        sql_file = backup_dir / f"{backup_name}.sql"
        
        # Professional Command Setup
        cmd = [
            mysqldump,
            "-h", config["host"],
            "-P", str(config["port"]),
            "-u", config["user"],
            "--skip-add-locks", # Avoid hanging on locked tables
            "--single-transaction", # Consistent backup without locking tables
            config["database"]
        ]
        
        # Secure password handling via environment variable
        env = os.environ.copy()
        if config["password"]:
            env["MYSQL_PWD"] = config["password"]
        
        try:
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0 # SW_HIDE

            logger.info(f"Executing mysqldump for database: {config['database']}")
            with open(sql_file, "wb") as f:
                result = subprocess.run(
                    cmd, 
                    stdout=f, 
                    stderr=subprocess.PIPE,
                    check=True, 
                    startupinfo=startupinfo, 
                    timeout=600,
                    env=env
                )
            return sql_file
        except subprocess.TimeoutExpired:
            logger.error("MySQL Dump timed out after 10 minutes.")
            if sql_file.exists(): os.remove(sql_file)
            raise Exception("MySQL backup timed out. The database might be too large or the server is unresponsive.")
        except subprocess.CalledProcessError as e:
            error_output = e.stderr.decode(errors='replace') if e.stderr else "No error details provided by mysqldump."
            logger.error(f"MySQL Dump failed with error: {error_output}")
            if sql_file.exists(): os.remove(sql_file)
            raise Exception(f"MySQL backup failed: {error_output}")

    def _restore_mysql(self, sql_file: Path):
        """Restores MySQL dump using professional streaming and security standards."""
        config = self._get_mysql_config()
        mysql = self._find_mysql_tool("mysql")
        
        if not mysql:
             raise Exception("mysql client not found.")
             
        # Professional Command Setup
        cmd = [
            mysql,
            "-h", config["host"],
            "-P", str(config["port"]),
            "-u", config["user"],
            "--batch", # Non-interactive mode
            "--force", # Continue on errors
            "--connect-timeout=30", # Fail fast if connection cannot be established
            config["database"]
        ]
        
        # Secure password handling
        env = os.environ.copy()
        if config["password"]:
            env["MYSQL_PWD"] = config["password"]
        
        try:
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0 # SW_HIDE

            logger.info(f"Executing mysql restore for database: {config['database']}")
            with open(sql_file, "rb") as f:
                result = subprocess.run(
                    cmd, 
                    stdin=f, 
                    stderr=subprocess.PIPE,
                    check=True, 
                    startupinfo=startupinfo, 
                    timeout=600,
                    env=env
                )
            logger.info("MySQL restore command completed successfully.")
        except subprocess.TimeoutExpired:
             logger.error("MySQL Restore timed out after 10 minutes.")
             raise Exception("MySQL restore timed out. The database might be too large or the server is unresponsive.")
        except subprocess.CalledProcessError as e:
             error_output = e.stderr.decode(errors='replace') if e.stderr else "No error details provided by mysql client."
             logger.error(f"MySQL restore failed with error: {error_output}")
             raise Exception(f"MySQL restore failed: {error_output}")

    def _get_free_space(self, path: Path) -> int:
        """Returns free space in bytes at the given path."""
        if sys.platform == "win32":
            import ctypes
            free_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(str(path), None, None, ctypes.byref(free_bytes))
            return free_bytes.value
        else:
            st = os.statvfs(path)
            return st.f_bavail * st.f_frsize

    def create_backup(self, is_manual: bool = False, output_format: Optional[str] = None) -> Dict:
        """Creates a professional backup of the database with integrity verification and encryption."""
        # Use a timeout for the operation lock to avoid indefinite hangs
        if not self._operation_lock.acquire(timeout=30):
             logger.error("Failed to acquire backup operation lock (Timeout: 30s).")
             return {"success": False, "message": "Another backup or restore is currently in progress. Please try again in a few moments."}
        
        # Track temporary files for cleanup
        temp_files = []
        
        try:
            fmt = (output_format or "").strip().lower()
            if fmt in ("zip", ".zip"):
                effective_encrypt = False
            elif fmt in ("enc", ".enc"):
                effective_encrypt = True
            else:
                effective_encrypt = bool(self.config.encrypt) and (Cipher is not None)

            if bool(self.config.encrypt) and (Cipher is None) and fmt not in ("enc", ".enc"):
                logger.warning("Backup encryption is enabled but cryptography is missing. Proceeding with unencrypted backup.")
            if fmt in ("enc", ".enc") and Cipher is None:
                return {"success": False, "message": "Encrypted backup (.enc) requires cryptography. Please install cryptography or choose .zip."}

            # 0. Professional Integrity Check
            logger.info("Starting database integrity check before backup...")
            if not self.verify_db_integrity():
                 logger.error("Database integrity check failed. Aborting backup.")
                 return {"success": False, "message": "Database integrity check failed. Backup aborted to prevent corruption propagation."}

            # 0.1 Ensure Encryption Key exists if encryption is enabled
            if effective_encrypt:
                self._ensure_key()
                if not self.config.encryption_keys or not self.config.active_key_id:
                    logger.error("Encryption enabled but no active key available.")
                    if fmt in ("enc", ".enc"):
                        return {"success": False, "message": "Encrypted backup (.enc) cannot be created because encryption keys are not initialized."}
                    logger.warning("Proceeding with unencrypted backup because encryption keys could not be initialized.")
                    effective_encrypt = False

            # Determine DB Type
            is_mysql = "mysql" in settings.DB_URL
            
            # Setup Paths
            backup_dir = Path(self.config.local_path)
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{timestamp}"
            if is_manual:
                backup_name += "_manual"

            zip_path = backup_dir / f"{backup_name}.zip"
            enc_path = backup_dir / f"{backup_name}.enc"
            
            source_file = None
            original_filename = ""
            
            # 1. Resource Check: Disk Space (Professional Safety)
            if is_mysql:
                # For MySQL, we don't know the size easily before dump, 
                # but we can check if there's at least 100MB as a baseline safety
                if self._get_free_space(backup_dir) < 100 * 1024 * 1024:
                    return {"success": False, "message": "Insufficient disk space for MySQL backup (minimum 100MB required)."}
                
                logger.info("Performing MySQL dump...")
                source_file = self._backup_mysql(backup_dir, backup_name)
                temp_files.append(source_file)
                original_filename = "dump.sql"
            else:
                db_path = self.get_db_path()
                if not db_path or not db_path.exists():
                    logger.error(f"Database file not found at: {db_path}")
                    return {"success": False, "message": "Database file not found."}
                
                db_size = db_path.stat().st_size
                # Require at least 3x the DB size free (1x for zip, 1x for enc, 1x for safety)
                free_space = self._get_free_space(backup_dir)
                if free_space < db_size * 3:
                    logger.error(f"Insufficient disk space. Required: {db_size*3} bytes, Available: {free_space} bytes")
                    return {"success": False, "message": f"Insufficient disk space for backup. Available: {round(free_space/(1024*1024), 2)} MB"}
                
                source_file = db_path
                original_filename = db_path.name

            protected_source = source_file if not is_mysql else None

            chunk_size = 4 * 1024 * 1024
            requested_type = str(getattr(self.config, "backup_mode", "full") or "full").strip().lower()
            if requested_type not in ("full", "incremental", "differential"):
                requested_type = "full"

            db_type = "mysql" if is_mysql else "sqlite"
            if is_mysql and requested_type != "full":
                requested_type = "full"
            base_manifest = None
            parent_manifest = None

            if requested_type in ("incremental", "differential"):
                base_manifest = self._find_latest_full_backup_metadata_in_dir(backup_dir)
                if requested_type == "incremental":
                    parent_manifest = self._find_latest_backup_metadata_in_dir(backup_dir)
                if not base_manifest:
                    requested_type = "full"
                    parent_manifest = None
                elif requested_type == "incremental" and not parent_manifest:
                    requested_type = "full"

            logger.info(f"Creating backup archive ({requested_type}): {zip_path}")
            temp_files.append(zip_path)
            if requested_type == "full":
                metadata = self._build_full_zip(
                    zip_path=zip_path,
                    source_file=source_file,
                    original_filename=original_filename,
                    db_type=db_type,
                    is_manual=is_manual,
                    chunk_size=chunk_size,
                )
            else:
                metadata = self._build_delta_zip(
                    zip_path=zip_path,
                    source_file=source_file,
                    original_filename=original_filename,
                    db_type=db_type,
                    is_manual=is_manual,
                    chunk_size=chunk_size,
                    backup_type=requested_type,
                    base_manifest=base_manifest or {},
                    parent_manifest=parent_manifest,
                )

            final_path = zip_path
            
            # 3. Encrypt if enabled (Professional Standard - Optimized with Chunked Streaming)
            if effective_encrypt:
                logger.info("Encrypting backup file...")
                if Cipher is None:
                    return {"success": False, "message": "Encryption failed: cryptography module missing."}
                try:
                    public_meta = {
                        "backup_type": metadata.get("backup_type"),
                        "db_type": metadata.get("db_type"),
                        "created_at": metadata.get("timestamp"),
                        "original_filename": metadata.get("original_filename"),
                        "base_backup_filename": metadata.get("base_backup_filename"),
                        "parent_backup_filename": metadata.get("parent_backup_filename"),
                        "is_manual": metadata.get("is_manual"),
                    }
                    self._encrypt_file_aes256(zip_path, enc_path, public_meta=public_meta)
                    final_path = enc_path
                except Exception as e:
                    logger.error(f"Encryption failed: {e}", exc_info=True)
                    return {"success": False, "message": f"Encryption failed: {e}"}

            destinations = self._get_filesystem_destinations()
            for dest_root in destinations:
                try:
                    if not dest_root.exists():
                        continue
                    if dest_root.resolve() == backup_dir.resolve():
                        continue
                    if self._get_free_space(dest_root) <= final_path.stat().st_size:
                        continue
                    dst_backup = dest_root / final_path.name
                    self._heal_destination_copy(final_path, dst_backup, attempts=2)
                except Exception as e:
                    logger.warning(f"Destination copy failed for {dest_root}: {e}")

            if bool(getattr(self.config, "retention_policy_enabled", False)) is True:
                self._apply_tiered_retention(backup_dir, protected_names={final_path.name})
            else:
                self._cleanup_old_backups()

            # Remove temporary files if successful (like the unencrypted zip if encrypted, or mysql dump)
            for temp_f in temp_files:
                if temp_f != final_path and temp_f.exists() and temp_f != protected_source:
                    try:
                        os.remove(temp_f)
                    except Exception as e:
                        logger.warning(f"Failed to cleanup temp file {temp_f}: {e}")

            logger.info(f"Backup completed successfully: {final_path.name}")
            if not final_path.exists():
                return {"success": False, "message": "Backup creation failed: output file was not created."}

            msg = f"Backup created: {final_path.name}"
            if bool(self.config.encrypt) and not effective_encrypt:
                msg += " (unencrypted fallback)"
            return {"success": True, "message": msg, "path": str(final_path)}

        except Exception as e:
            logger.error(f"CRITICAL: Backup process failed: {e}", exc_info=True)
            # Cleanup partially created files
            if 'zip_path' in locals() and zip_path.exists(): os.remove(zip_path)
            if 'enc_path' in locals() and enc_path.exists(): os.remove(enc_path)
            return {"success": False, "message": f"Backup failed: {str(e)}"}
        finally:
            for temp_f in temp_files:
                try:
                    if isinstance(temp_f, Path) and temp_f.exists() and temp_f.name.endswith(".temp"):
                        os.remove(temp_f)
                    elif isinstance(temp_f, Path) and temp_f.exists() and temp_f.name.startswith("restore_work_"):
                        os.remove(temp_f)
                except Exception:
                    pass
            self._operation_lock.release()

    def restore_backup(self, backup_path_str: str) -> Dict:
        """Restores the database from a professional backup file with integrity and compatibility checks."""
        # Use a timeout for the operation lock to avoid indefinite hangs
        if not self._operation_lock.acquire(timeout=30):
             logger.error("Failed to acquire restore operation lock (Timeout: 30s).")
             return {"success": False, "message": "Another backup or restore is currently in progress. Please try again in a few moments."}

        # Track temporary files for cleanup
        temp_files = []
        
        try:
            backup_path = Path(backup_path_str)
            if not backup_path.exists():
                logger.error(f"Restore failed: Backup file not found at {backup_path_str}")
                return {"success": False, "message": "Backup file not found."}

            is_mysql = "mysql" in settings.DB_URL
            db_path = None
            
            if not is_mysql:
                db_path = self.get_db_path()
                if not db_path:
                     logger.error("Restore failed: Could not determine target database path.")
                     return {"success": False, "message": "Target database path not found."}

            try:
                backup_dir = backup_path.parent
                selected_meta = self._read_backup_metadata(backup_path, temp_files=temp_files)
                backup_type = str(selected_meta.get("backup_type") or "full").lower()
                db_type = str(selected_meta.get("db_type") or "sqlite").lower()

                if is_mysql and db_type != "mysql":
                    return {"success": False, "message": "Backup type mismatch."}
                if (not is_mysql) and db_type != "sqlite":
                    return {"success": False, "message": "Backup type mismatch."}

                if is_mysql and backup_type != "full":
                    return {"success": False, "message": "Incremental/differential restore is not supported for MySQL backups."}

                if (not is_mysql) and backup_type in ("incremental", "differential") and str(selected_meta.get("version") or "").startswith("2"):
                    chain_files: List[Path] = []
                    cur_path = backup_path
                    seen: set[str] = set()

                    while True:
                        if cur_path.name in seen:
                            return {"success": False, "message": "Invalid backup chain: cycle detected."}
                        seen.add(cur_path.name)
                        chain_files.append(cur_path)

                        cur_meta = self._read_backup_metadata(cur_path, temp_files=temp_files)
                        cur_type = str(cur_meta.get("backup_type") or "").lower()
                        if cur_type == "full":
                            break
                        if cur_type == "incremental":
                            dep_name = str(cur_meta.get("parent_backup_filename") or "")
                        elif cur_type == "differential":
                            dep_name = str(cur_meta.get("base_backup_filename") or "")
                        else:
                            return {"success": False, "message": f"Unsupported backup type: {cur_type}"}

                        if not dep_name:
                            return {"success": False, "message": "Invalid backup chain: missing dependency reference."}

                        dep_path = backup_dir / dep_name
                        if not dep_path.exists():
                            return {"success": False, "message": f"Missing dependency backup file: {dep_name}"}
                        cur_path = dep_path

                    chain_files = list(reversed(chain_files))
                    chunk_size = int(selected_meta.get("chunk_size") or 4 * 1024 * 1024)

                    if db_path.exists():
                        safety_backup = db_path.with_suffix(".bak.safety")
                        try:
                            shutil.copy2(db_path, safety_backup)
                        except Exception:
                            pass

                    temp_restore_file = backup_dir / f"restore_work_{secrets.token_hex(6)}.db"
                    temp_files.append(temp_restore_file)

                    for idx, fp in enumerate(chain_files):
                        step_zip = fp
                        if fp.suffix.lower() == ".enc":
                            temp_zip = fp.with_suffix(f".{secrets.token_hex(4)}.zip.temp")
                            temp_files.append(temp_zip)
                            if Cipher is None:
                                return {"success": False, "message": "Decryption failed: cryptography module missing."}
                            self._decrypt_file_aes256(fp, temp_zip)
                            step_zip = temp_zip

                        if idx == 0:
                            self._extract_full_to_path(step_zip, temp_restore_file)
                        else:
                            self._apply_delta_zip_to_file(step_zip, temp_restore_file, chunk_size=chunk_size)

                    expected = str(selected_meta.get("file_sha256") or "")
                    if expected:
                        actual = self._calculate_file_hash(temp_restore_file)
                        if actual != expected:
                            if db_path.with_suffix(".bak.safety").exists():
                                shutil.copy2(db_path.with_suffix(".bak.safety"), db_path)
                            return {"success": False, "message": "Integrity verification failed for restored database. Rollback performed."}

                    max_retries = 10
                    retry_delay = 1.0
                    for attempt in range(max_retries):
                        try:
                            shutil.copy2(temp_restore_file, db_path)
                            break
                        except (PermissionError, OSError) as e:
                            if attempt < max_retries - 1:
                                time.sleep(retry_delay)
                            else:
                                raise Exception(f"Database file is locked by another process. Error: {e}")

                    return {"success": True, "message": "Restore successful."}

                source_zip = backup_path
                if backup_path.suffix == ".enc":
                    temp_zip = backup_path.with_suffix(".zip.temp")
                    temp_files.append(temp_zip)
                    if Cipher is None:
                        return {"success": False, "message": "Decryption failed: cryptography module missing."}
                    self._decrypt_file_aes256(backup_path, temp_zip)
                    source_zip = temp_zip

                with zipfile.ZipFile(source_zip, "r") as zipf:
                    if "metadata.json" not in zipf.namelist():
                        return {"success": False, "message": "Invalid backup: Missing metadata."}
                    metadata = json.loads(zipf.read("metadata.json").decode())
                    backup_db_type = metadata.get("db_type", "sqlite")
                    current_db_type = "mysql" if is_mysql else "sqlite"
                    if backup_db_type != current_db_type:
                        return {"success": False, "message": f"Backup type mismatch. Backup is {backup_db_type}, but current DB is {current_db_type}."}

                    original_filename = metadata.get("original_filename", "dump.sql" if is_mysql else db_path.name)
                    if is_mysql:
                        temp_dir = backup_dir / "restore_temp"
                        temp_dir.mkdir(exist_ok=True)
                        zipf.extract(original_filename, path=temp_dir)
                        sql_file = temp_dir / original_filename
                        try:
                            self._restore_mysql(sql_file)
                        finally:
                            try:
                                shutil.rmtree(temp_dir, ignore_errors=True)
                            except Exception:
                                pass
                        return {"success": True, "message": "Restore successful."}

                    if db_path.exists():
                        safety_backup = db_path.with_suffix(".bak.safety")
                        try:
                            shutil.copy2(db_path, safety_backup)
                        except Exception:
                            pass

                    temp_dir = backup_dir / f"restore_temp_{secrets.token_hex(6)}"
                    temp_dir.mkdir(exist_ok=True)
                    try:
                        zipf.extract(original_filename, path=temp_dir)
                        extracted = temp_dir / original_filename
                        expected = metadata.get("file_sha256") or metadata.get("checksum") or ""
                        if expected and self._calculate_file_hash(extracted) != expected:
                            if db_path.with_suffix(".bak.safety").exists():
                                shutil.copy2(db_path.with_suffix(".bak.safety"), db_path)
                            return {"success": False, "message": "Integrity verification failed. Rollback performed."}
                        shutil.copy2(extracted, db_path)
                    finally:
                        try:
                            shutil.rmtree(temp_dir, ignore_errors=True)
                        except Exception:
                            pass
                    return {"success": True, "message": "Restore successful."}

            except Exception as e:
                logger.error(f"CRITICAL: Restore process failed: {e}", exc_info=True)
                msg = str(e).strip()
                if not msg:
                    msg = e.__class__.__name__
                return {"success": False, "message": msg}
        finally:
            self._operation_lock.release()

    def _calculate_file_hash(self, filepath: Path) -> str:
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _manifest_path_for_backup(self, backup_path: Path) -> Path:
        return backup_path.with_suffix(backup_path.suffix + ".manifest.json")

    def _write_json(self, path: Path, payload: Dict) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def _read_json(self, path: Path) -> Dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}

    def _iter_file_chunks(self, path: Path, chunk_size: int) -> tuple[int, bytes]:
        idx = 0
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield idx, chunk
                idx += 1

    def _chunk_hashes(self, path: Path, chunk_size: int) -> List[str]:
        hashes_out: List[str] = []
        for _i, chunk in self._iter_file_chunks(path, chunk_size):
            h = hashlib.sha256()
            h.update(chunk)
            hashes_out.append(h.hexdigest())
        return hashes_out

    def _list_local_manifests(self, backup_dir: Path) -> List[Path]:
        return sorted(backup_dir.glob("backup_*.manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    def _load_manifest_for_backup_path(self, backup_path: Path) -> Optional[Dict]:
        mf = self._manifest_path_for_backup(backup_path)
        if mf.exists():
            try:
                return self._read_json(mf)
            except Exception:
                return None
        return None

    def _load_manifest_path(self, manifest_path: Path) -> Optional[Dict]:
        if not manifest_path.exists():
            return None
        try:
            return self._read_json(manifest_path)
        except Exception:
            return None

    def _find_latest_manifest(self, backup_dir: Path) -> Optional[Dict]:
        for mf_path in self._list_local_manifests(backup_dir):
            mf = self._load_manifest_path(mf_path)
            if mf and mf.get("success") is True:
                return mf
        return None

    def _find_latest_full_manifest(self, backup_dir: Path) -> Optional[Dict]:
        for mf_path in self._list_local_manifests(backup_dir):
            mf = self._load_manifest_path(mf_path)
            if mf and mf.get("success") is True and (mf.get("backup_type") or "").lower() == "full":
                return mf
        return None

    def _backup_path_from_manifest(self, backup_dir: Path, mf: Dict) -> Optional[Path]:
        name = str(mf.get("backup_filename") or "")
        if not name:
            return None
        p = backup_dir / name
        if p.exists():
            return p
        return None

    def _build_full_zip(self, zip_path: Path, source_file: Path, original_filename: str, db_type: str, is_manual: bool, chunk_size: int) -> Dict:
        file_hash = self._calculate_file_hash(source_file)
        chunk_hashes = self._chunk_hashes(source_file, chunk_size)
        metadata = {
            "timestamp": datetime.now().isoformat(),
            "version": "2.0",
            "backup_type": "full",
            "db_type": db_type,
            "original_filename": original_filename,
            "is_manual": bool(is_manual),
            "file_sha256": file_hash,
            "chunk_size": int(chunk_size),
            "chunk_hashes": chunk_hashes,
            "file_size": int(source_file.stat().st_size),
        }
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zipf:
            zipf.write(source_file, arcname=original_filename)
            zipf.writestr("metadata.json", json.dumps(metadata))
        return metadata

    def _build_delta_zip(
        self,
        zip_path: Path,
        source_file: Path,
        original_filename: str,
        db_type: str,
        is_manual: bool,
        chunk_size: int,
        backup_type: str,
        base_manifest: Dict,
        parent_manifest: Optional[Dict],
    ) -> Dict:
        current_hash = self._calculate_file_hash(source_file)
        current_chunk_hashes = self._chunk_hashes(source_file, chunk_size)
        compare_hashes = base_manifest.get("chunk_hashes") or []
        if backup_type == "incremental" and parent_manifest:
            compare_hashes = parent_manifest.get("chunk_hashes") or compare_hashes

        changed: List[int] = []
        max_len = max(len(current_chunk_hashes), len(compare_hashes))
        for i in range(max_len):
            a = current_chunk_hashes[i] if i < len(current_chunk_hashes) else ""
            b = compare_hashes[i] if i < len(compare_hashes) else ""
            if a != b:
                changed.append(i)

        metadata = {
            "timestamp": datetime.now().isoformat(),
            "version": "2.0",
            "backup_type": backup_type,
            "db_type": db_type,
            "original_filename": original_filename,
            "is_manual": bool(is_manual),
            "file_sha256": current_hash,
            "chunk_size": int(chunk_size),
            "chunk_hashes": current_chunk_hashes,
            "file_size": int(source_file.stat().st_size),
            "base_backup_filename": base_manifest.get("backup_filename"),
            "parent_backup_filename": (parent_manifest or {}).get("backup_filename") if parent_manifest else None,
            "changed_chunks": changed,
        }

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zipf:
            zipf.writestr("metadata.json", json.dumps(metadata))
            for idx, chunk in self._iter_file_chunks(source_file, chunk_size):
                if idx in changed:
                    zipf.writestr(f"chunks/{idx}.bin", chunk)
        return metadata

    def _extract_full_to_path(self, zip_path: Path, dest_path: Path) -> Dict:
        with zipfile.ZipFile(zip_path, "r") as zipf:
            if "metadata.json" not in zipf.namelist():
                raise ValueError("Invalid backup: Missing metadata.json.")
            metadata = json.loads(zipf.read("metadata.json").decode())
            original_filename = metadata.get("original_filename")
            if not original_filename:
                raise ValueError("Invalid backup: Missing original filename.")
            tmp_dir = dest_path.parent / f"restore_tmp_{secrets.token_hex(6)}"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            try:
                zipf.extract(original_filename, path=tmp_dir)
                extracted = tmp_dir / original_filename
                shutil.copy2(extracted, dest_path)
            finally:
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    pass
        return metadata

    def _apply_delta_zip_to_file(self, zip_path: Path, dest_path: Path, chunk_size: int) -> Dict:
        with zipfile.ZipFile(zip_path, "r") as zipf:
            if "metadata.json" not in zipf.namelist():
                raise ValueError("Invalid delta backup: Missing metadata.json.")
            metadata = json.loads(zipf.read("metadata.json").decode())
            changed = metadata.get("changed_chunks") or []
            if not isinstance(changed, list):
                raise ValueError("Invalid delta backup: changed_chunks format.")

            with open(dest_path, "r+b") as f:
                for idx in changed:
                    data = zipf.read(f"chunks/{idx}.bin")
                    f.seek(int(idx) * int(chunk_size))
                    f.write(data)
                f.truncate(int(metadata.get("file_size") or dest_path.stat().st_size))
        return metadata

    def _collect_dependency_filenames(self, mf: Dict) -> List[str]:
        deps: List[str] = []
        base = mf.get("base_backup_filename")
        parent = mf.get("parent_backup_filename")
        if base:
            deps.append(str(base))
        if parent:
            deps.append(str(parent))
        return deps

    def _compute_bucket_key(self, ts: datetime, tier: str) -> str:
        tier = (tier or "").lower()
        if tier == "hourly":
            return ts.strftime("%Y-%m-%d %H")
        if tier == "daily":
            return ts.strftime("%Y-%m-%d")
        if tier == "weekly":
            y, w, _ = ts.isocalendar()
            return f"{y}-W{w:02d}"
        if tier == "monthly":
            return ts.strftime("%Y-%m")
        if tier == "yearly":
            return ts.strftime("%Y")
        return ts.strftime("%Y-%m-%d")

    def _apply_tiered_retention(self, backup_dir: Path, protected_names: Optional[set[str]] = None) -> None:
        policy = getattr(self.config, "retention_policy", None) or {}
        keep_map: Dict[str, int] = {}
        for k in ["hourly", "daily", "weekly", "monthly", "yearly"]:
            try:
                keep_map[k] = int(((policy.get(k) or {}).get("keep") or 0))
            except Exception:
                keep_map[k] = 0
        if max(keep_map.values() or [0]) <= 0:
            logger.warning("Tiered retention is enabled but all keep values are 0. Skipping tiered retention to avoid deleting backups.")
            return

        backup_files: List[Path] = []
        for ext in ["*.zip", "*.enc"]:
            backup_files.extend(list(backup_dir.glob(f"backup_{ext}")))
        if not backup_files:
            return

        infos: List[Dict] = []
        info_by_name: Dict[str, Dict] = {}
        for fp in backup_files:
            try:
                created_at = None
                btype = "full"
                base_name = ""
                parent_name = ""
                db_type = ""
                meta = {}
                if fp.suffix.lower() == ".enc":
                    meta = self._read_encrypted_public_meta(fp)
                if fp.suffix.lower() == ".zip":
                    try:
                        with zipfile.ZipFile(fp, "r") as zf:
                            if "metadata.json" in zf.namelist():
                                meta = json.loads(zf.read("metadata.json").decode()) or {}
                    except Exception:
                        meta = {}

                btype = str(meta.get("backup_type") or "full").lower()
                base_name = str(meta.get("base_backup_filename") or "")
                parent_name = str(meta.get("parent_backup_filename") or "")
                db_type = str(meta.get("db_type") or "")
                try:
                    created_at = datetime.fromisoformat(str(meta.get("timestamp") or meta.get("created_at") or ""))
                except Exception:
                    created_at = datetime.fromtimestamp(fp.stat().st_mtime)

                info = {
                    "name": fp.name,
                    "path": fp,
                    "created_at": created_at,
                    "backup_type": btype,
                    "base_backup_filename": base_name,
                    "parent_backup_filename": parent_name,
                    "db_type": db_type,
                }
                infos.append(info)
                info_by_name[fp.name] = info
            except Exception:
                continue

        if not infos:
            return

        keep_filenames: set[str] = set()
        for tier, keep_n in keep_map.items():
            if keep_n <= 0:
                continue
            buckets: Dict[str, Dict] = {}
            for info in sorted(infos, key=lambda x: x["created_at"], reverse=True):
                b = self._compute_bucket_key(info["created_at"], tier)
                if b not in buckets:
                    buckets[b] = info
            for info in list(buckets.values())[:keep_n]:
                keep_filenames.add(str(info["name"]))
        if not keep_filenames:
            logger.warning("Tiered retention produced an empty keep set. Skipping deletion to avoid deleting all backups.")
            return

        if protected_names:
            for n in protected_names:
                if n:
                    keep_filenames.add(str(n))

        changed = True
        while changed:
            changed = False
            for name in list(keep_filenames):
                info = info_by_name.get(name)
                if not info:
                    continue
                for dep in [str(info.get("base_backup_filename") or ""), str(info.get("parent_backup_filename") or "")]:
                    if dep and dep not in keep_filenames:
                        keep_filenames.add(dep)
                        changed = True

        for info in infos:
            name = str(info.get("name") or "")
            if not name or name in keep_filenames:
                continue
            fp = info.get("path")
            try:
                if isinstance(fp, Path) and fp.exists():
                    os.remove(fp)
            except Exception as e:
                logger.warning(f"Retention deletion failed for {name}: {e}")

    def _get_filesystem_destinations(self) -> List[Path]:
        out: List[Path] = []
        dests = getattr(self.config, "destinations", None) or []
        for d in dests:
            try:
                if not isinstance(d, dict):
                    continue
                if str(d.get("type") or "local").lower() not in ("local", "network_share", "filesystem"):
                    continue
                if d.get("enabled") is False:
                    continue
                p = Path(str(d.get("path") or "").strip())
                if str(p) and p not in out:
                    out.append(p)
            except Exception:
                continue
        if getattr(self.config, "cloud_path", ""):
            try:
                p = Path(str(self.config.cloud_path).strip())
                if str(p) and p not in out:
                    out.append(p)
            except Exception:
                pass
        return out

    def _copy_with_integrity(self, src: Path, dst: Path) -> Dict:
        result: Dict = {"path": str(dst), "success": False, "error": None}
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            src_hash = self._calculate_file_hash(src)
            dst_hash = self._calculate_file_hash(dst)
            if src_hash != dst_hash:
                result["error"] = "Checksum mismatch after copy."
                try:
                    os.remove(dst)
                except Exception:
                    pass
                return result
            result["success"] = True
            result["sha256"] = dst_hash
            result["bytes"] = int(dst.stat().st_size)
            return result
        except Exception as e:
            result["error"] = str(e)
            return result

    def _heal_destination_copy(self, src: Path, dst: Path, attempts: int = 2) -> Dict:
        last = {"path": str(dst), "success": False, "error": "Unknown error"}
        for _ in range(max(1, int(attempts))):
            last = self._copy_with_integrity(src, dst)
            if last.get("success") is True:
                return last
            time.sleep(0.5)
        return last

    def verify_and_heal_backup(self, backup_path_str: str) -> Dict:
        if not self._operation_lock.acquire(timeout=30):
            return {"success": False, "message": "Another backup or restore is currently in progress."}

        try:
            backup_path = Path(backup_path_str)
            if not backup_path.exists():
                return {"success": False, "message": "Backup file not found."}

            backup_dir = backup_path.parent
            def is_healthy(p: Path) -> bool:
                if not p.exists():
                    return False
                try:
                    if p.suffix.lower() == ".enc":
                        return self._verify_encrypted_integrity(p)
                    if p.suffix.lower() == ".zip":
                        with zipfile.ZipFile(p, "r") as zf:
                            if "metadata.json" not in zf.namelist():
                                return False
                            bad = zf.testzip()
                            return bad is None
                    return False
                except Exception:
                    return False

            configured_dests = self._get_filesystem_destinations()
            candidates: List[Path] = [backup_path]
            for dest_root in configured_dests:
                try:
                    if not dest_root.exists():
                        continue
                    if dest_root.resolve() == backup_dir.resolve():
                        continue
                    candidates.append(dest_root / backup_path.name)
                except Exception:
                    continue

            source: Optional[Path] = None
            if is_healthy(backup_path):
                source = backup_path
            else:
                for c in candidates[1:]:
                    if is_healthy(c):
                        source = c
                        break

            if not source:
                return {"success": False, "message": "No healthy copy found across all configured destinations."}

            results: Dict[str, Dict] = {}
            if source != backup_path:
                try:
                    self._heal_destination_copy(source, backup_path, attempts=2)
                    results["local"] = {"path": str(backup_path), "success": True, "source": str(source)}
                except Exception as e:
                    results["local"] = {"path": str(backup_path), "success": False, "error": str(e)}
            else:
                results["local"] = {"path": str(backup_path), "success": True}

            for dest_root in configured_dests:
                try:
                    if not dest_root.exists():
                        continue
                    if dest_root.resolve() == backup_dir.resolve():
                        continue
                    dst_backup = dest_root / backup_path.name
                    if is_healthy(dst_backup):
                        results[str(dest_root)] = {"path": str(dst_backup), "success": True}
                        continue
                    copy_res = self._heal_destination_copy(backup_path, dst_backup, attempts=2)
                    results[str(dest_root)] = copy_res
                except Exception as e:
                    results[str(dest_root)] = {"path": str(dest_root), "success": False, "error": str(e)}

            return {"success": True, "message": "Verification completed.", "results": results}
        finally:
            self._operation_lock.release()

    def verify_and_heal_recent(self, limit: int = 25) -> Dict:
        backups = self.list_backups()[: int(limit or 25)]
        ok = 0
        failed = 0
        results: List[Dict] = []
        for b in backups:
            p = str(b.get("path") or "")
            if not p:
                continue
            res = self.verify_and_heal_backup(p)
            results.append(res)
            if res.get("success") is True:
                ok += 1
            else:
                failed += 1
        return {"success": failed == 0, "checked": ok + failed, "ok": ok, "failed": failed, "results": results}

    def _get_key_material(self, key_id: str) -> bytes:
        for k in self.config.encryption_keys or []:
            if str(k.get("id") or "") == str(key_id or ""):
                raw = str(k.get("key") or "").encode()
                return base64.urlsafe_b64decode(raw)
        raise ValueError(
            f"Encryption key not found for the requested key id '{key_id}'. "
            "This backup was likely created on another computer. "
            "Import the encryption keys from the source computer (Backup Settings -> Export Keys/Import Keys) "
            "or restore from an unencrypted .zip backup."
        )

    def _get_active_key(self) -> tuple[str, bytes]:
        self._ensure_key()
        if not self.config.encryption_keys or not self.config.active_key_id:
            raise ValueError("No active encryption key configured.")
        return str(self.config.active_key_id), self._get_key_material(str(self.config.active_key_id))

    def _encrypt_file_aes256(self, src_path: Path, dst_path: Path, public_meta: Optional[Dict] = None) -> None:
        key_id, key = self._get_active_key()
        if len(key) != 32:
            raise ValueError("Invalid key size for AES-256.")
        iv = secrets.token_bytes(16)

        cipher = Cipher(algorithms.AES(key), modes.CTR(iv), backend=default_backend())
        encryptor = cipher.encryptor()

        mac = hmac.HMAC(key, hashes.SHA256(), backend=default_backend())

        key_id_bytes = key_id.encode("utf-8")
        if len(key_id_bytes) > 255:
            raise ValueError("Key id too long.")

        meta_payload = json.dumps(public_meta or {}, ensure_ascii=False).encode("utf-8")
        if len(meta_payload) > 1024 * 1024:
            raise ValueError("Public metadata too large.")
        header = (
            b"FBRBK01"
            + bytes([2])
            + bytes([len(key_id_bytes)])
            + key_id_bytes
            + iv
            + len(meta_payload).to_bytes(4, "big")
            + meta_payload
        )

        with open(src_path, "rb") as f_in, open(dst_path, "wb") as f_out:
            f_out.write(header)
            mac.update(header)
            while True:
                chunk = f_in.read(1024 * 1024)
                if not chunk:
                    break
                ct = encryptor.update(chunk)
                mac.update(ct)
                f_out.write(ct)
            final_ct = encryptor.finalize()
            if final_ct:
                mac.update(final_ct)
                f_out.write(final_ct)
            f_out.write(mac.finalize())

    def _decrypt_file_aes256(self, src_path: Path, dst_path: Path) -> None:
        file_size = src_path.stat().st_size
        if file_size < 7 + 1 + 1 + 16 + 32:
            raise ValueError("Invalid encrypted backup format.")

        with open(src_path, "rb") as f_in:
            magic = f_in.read(7)
            if magic != b"FBRBK01":
                raise ValueError("Invalid encrypted backup magic header.")
            ver = int.from_bytes(f_in.read(1), "big")
            if ver not in (1, 2):
                raise ValueError("Unsupported encrypted backup version.")
            key_id_len = int.from_bytes(f_in.read(1), "big")
            key_id = f_in.read(key_id_len).decode("utf-8")
            iv = f_in.read(16)
            meta_len = 0
            meta_payload = b""
            if ver == 2:
                meta_len = int.from_bytes(f_in.read(4), "big")
                if meta_len < 0 or meta_len > 1024 * 1024:
                    raise ValueError("Invalid encrypted backup metadata length.")
                meta_payload = f_in.read(meta_len)

            key = self._get_key_material(key_id)
            if len(key) != 32:
                raise ValueError("Invalid key size for AES-256.")

            cipher = Cipher(algorithms.AES(key), modes.CTR(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            mac = hmac.HMAC(key, hashes.SHA256(), backend=default_backend())

            header_len = 7 + 1 + 1 + key_id_len + 16 + (4 + meta_len if ver == 2 else 0)
            expected_mac_len = 32
            remaining = file_size - header_len
            if remaining <= expected_mac_len:
                raise ValueError("Invalid encrypted backup length.")

            f_in.seek(file_size - expected_mac_len)
            expected_mac = f_in.read(expected_mac_len)
            f_in.seek(header_len)

            to_read = file_size - header_len - expected_mac_len
            with open(dst_path, "wb") as f_out:
                if ver == 2:
                    header = (
                        b"FBRBK01"
                        + bytes([2])
                        + bytes([key_id_len])
                        + key_id.encode("utf-8")
                        + iv
                        + meta_len.to_bytes(4, "big")
                        + meta_payload
                    )
                    mac.update(header)
                while to_read > 0:
                    chunk = f_in.read(min(1024 * 1024, to_read))
                    if not chunk:
                        break
                    to_read -= len(chunk)
                    mac.update(chunk)
                    pt = decryptor.update(chunk)
                    f_out.write(pt)
                final_pt = decryptor.finalize()
                if final_pt:
                    f_out.write(final_pt)

            try:
                mac.verify(expected_mac)
            except Exception as e:
                if InvalidSignature is not None and isinstance(e, InvalidSignature):
                    raise ValueError(
                        f"Decryption failed: wrong encryption key for key id '{key_id}' or backup file is corrupted."
                    )
                raise

    def _read_encrypted_public_meta(self, src_path: Path) -> Dict:
        try:
            with open(src_path, "rb") as f:
                magic = f.read(7)
                if magic != b"FBRBK01":
                    return {}
                ver = int.from_bytes(f.read(1), "big")
                if ver != 2:
                    return {}
                key_id_len = int.from_bytes(f.read(1), "big")
                _key_id = f.read(key_id_len)
                _iv = f.read(16)
                meta_len = int.from_bytes(f.read(4), "big")
                if meta_len < 0 or meta_len > 1024 * 1024:
                    return {}
                meta_payload = f.read(meta_len)
            return json.loads(meta_payload.decode("utf-8")) or {}
        except Exception:
            return {}

    def _verify_encrypted_integrity(self, src_path: Path) -> bool:
        try:
            file_size = src_path.stat().st_size
            if file_size < 7 + 1 + 1 + 16 + 32:
                return False

            with open(src_path, "rb") as f:
                magic = f.read(7)
                if magic != b"FBRBK01":
                    return False
                ver = int.from_bytes(f.read(1), "big")
                if ver not in (1, 2):
                    return False
                key_id_len = int.from_bytes(f.read(1), "big")
                key_id = f.read(key_id_len).decode("utf-8")
                iv = f.read(16)
                meta_len = 0
                meta_payload = b""
                if ver == 2:
                    meta_len = int.from_bytes(f.read(4), "big")
                    if meta_len < 0 or meta_len > 1024 * 1024:
                        return False
                    meta_payload = f.read(meta_len)

                key = self._get_key_material(key_id)
                mac = hmac.HMAC(key, hashes.SHA256(), backend=default_backend())

                header_len = 7 + 1 + 1 + key_id_len + 16 + (4 + meta_len if ver == 2 else 0)
                expected_mac_len = 32
                if file_size <= header_len + expected_mac_len:
                    return False

                f.seek(file_size - expected_mac_len)
                expected_mac = f.read(expected_mac_len)

                f.seek(0)
                if ver == 2:
                    header = (
                        b"FBRBK01"
                        + bytes([2])
                        + bytes([key_id_len])
                        + key_id.encode("utf-8")
                        + iv
                        + meta_len.to_bytes(4, "big")
                        + meta_payload
                    )
                    f.seek(len(header))
                    mac.update(header)
                else:
                    f.seek(header_len)

                to_read = file_size - header_len - expected_mac_len
                while to_read > 0:
                    chunk = f.read(min(1024 * 1024, to_read))
                    if not chunk:
                        break
                    to_read -= len(chunk)
                    mac.update(chunk)

                mac.verify(expected_mac)
            return True
        except Exception:
            return False

    def _read_backup_metadata(self, backup_path: Path, temp_files: Optional[List[Path]] = None) -> Dict:
        meta: Dict = {}
        if backup_path.suffix.lower() == ".zip":
            with zipfile.ZipFile(backup_path, "r") as zf:
                if "metadata.json" not in zf.namelist():
                    raise ValueError("Invalid backup: Missing metadata.json.")
                meta = json.loads(zf.read("metadata.json").decode()) or {}
            meta["backup_filename"] = backup_path.name
            return meta

        if backup_path.suffix.lower() == ".enc":
            temp_zip = backup_path.with_suffix(f".{secrets.token_hex(4)}.zip.temp")
            if temp_files is not None:
                temp_files.append(temp_zip)
            self._decrypt_file_aes256(backup_path, temp_zip)
            with zipfile.ZipFile(temp_zip, "r") as zf:
                if "metadata.json" not in zf.namelist():
                    raise ValueError("Invalid backup: Missing metadata.json.")
                meta = json.loads(zf.read("metadata.json").decode()) or {}
            meta["backup_filename"] = backup_path.name
            return meta

        raise ValueError("Unsupported backup file type.")

    def get_backup_public_info(self, backup_path_str: str) -> Dict:
        p = Path(str(backup_path_str))
        if not p.exists():
            return {}

        if p.suffix.lower() == ".enc":
            meta = self._read_encrypted_public_meta(p)
            if meta:
                return {
                    "backup_filename": p.name,
                    "backup_type": str(meta.get("backup_type") or ""),
                    "db_type": str(meta.get("db_type") or ""),
                    "created_at": str(meta.get("created_at") or ""),
                    "base_backup_filename": str(meta.get("base_backup_filename") or ""),
                    "parent_backup_filename": str(meta.get("parent_backup_filename") or ""),
                }
            try:
                temp_files: List[Path] = []
                full = self._read_backup_metadata(p, temp_files=temp_files)
                out = {
                    "backup_filename": p.name,
                    "backup_type": str(full.get("backup_type") or ""),
                    "db_type": str(full.get("db_type") or ""),
                    "created_at": str(full.get("timestamp") or ""),
                    "base_backup_filename": str(full.get("base_backup_filename") or ""),
                    "parent_backup_filename": str(full.get("parent_backup_filename") or ""),
                }
                for t in temp_files:
                    try:
                        if t.exists():
                            os.remove(t)
                    except Exception:
                        pass
                return out
            except Exception:
                return {}

        if p.suffix.lower() == ".zip":
            try:
                full = self._read_backup_metadata(p)
                return {
                    "backup_filename": p.name,
                    "backup_type": str(full.get("backup_type") or ""),
                    "db_type": str(full.get("db_type") or ""),
                    "created_at": str(full.get("timestamp") or ""),
                    "base_backup_filename": str(full.get("base_backup_filename") or ""),
                    "parent_backup_filename": str(full.get("parent_backup_filename") or ""),
                }
            except Exception:
                return {}

        return {}

    def _list_backup_files(self, backup_dir: Path) -> List[Path]:
        files: List[Path] = []
        for ext in ["*.zip", "*.enc"]:
            files.extend(list(backup_dir.glob(f"backup_{ext}")))
        files = [p for p in files if p.is_file() and not p.name.endswith(".temp")]
        return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)

    def _find_latest_backup_metadata_in_dir(self, backup_dir: Path) -> Optional[Dict]:
        for fp in self._list_backup_files(backup_dir):
            temp: List[Path] = []
            try:
                meta = self._read_backup_metadata(fp, temp_files=temp)
                return meta
            except Exception:
                continue
            finally:
                for t in temp:
                    try:
                        if t.exists():
                            os.remove(t)
                    except Exception:
                        pass
        return None

    def _find_latest_full_backup_metadata_in_dir(self, backup_dir: Path) -> Optional[Dict]:
        for fp in self._list_backup_files(backup_dir):
            temp: List[Path] = []
            try:
                meta = self._read_backup_metadata(fp, temp_files=temp)
                if str(meta.get("backup_type") or "").lower() == "full":
                    return meta
            except Exception:
                continue
            finally:
                for t in temp:
                    try:
                        if t.exists():
                            os.remove(t)
                    except Exception:
                        pass
        return None

    def verify_db_integrity(self) -> bool:
        """Runs a PRAGMA integrity_check for SQLite or basic check for MySQL."""
        if "mysql" in settings.DB_URL:
            return True # MySQL is usually handled by the server
            
        db_path = self.get_db_path()
        if not db_path or not db_path.exists():
            return False
            
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            conn.close()
            return result[0] == "ok"
        except Exception as e:
            logger.error(f"Integrity check failed: {e}")
            return False

    def _cleanup_old_backups(self):
        """Deletes backups older than retention_days."""
        if self.config.retention_days <= 0:
            return

        backup_dir = Path(self.config.local_path)
        cutoff = datetime.now() - timedelta(days=self.config.retention_days)
        
        for file in backup_dir.glob("backup_*"):
            if file.stat().st_mtime < cutoff.timestamp():
                try:
                    os.remove(file)
                    logger.info(f"Deleted old backup: {file.name}")
                except Exception as e:
                    logger.error(f"Failed to delete old backup {file.name}: {e}")

    def list_backups(self) -> List[Dict]:
        """Lists available professional backup files (.zip and .enc)."""
        backup_dir = Path(self.config.local_path)
        if not backup_dir.exists():
            return []
            
        backups = []
        # Only look for backup_* files with supported extensions
        for ext in ["*.zip", "*.enc"]:
            for file in backup_dir.glob(f"backup_{ext}"):
                try:
                    stat = file.stat()
                    backups.append({
                        "name": file.name,
                        "path": str(file),
                        "size_mb": round(stat.st_size / (1024 * 1024), 2),
                        "date": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                    })
                except Exception:
                    pass
        
        # Sort by date desc
        return sorted(backups, key=lambda x: x["date"], reverse=True)

    # --- Scheduling ---
    def start_scheduler(self):
        if not schedule:
            logger.warning("Schedule module missing. Automatic backups disabled.")
            return

        if not self.config.enabled:
            return
            
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            return

        self.stop_event.clear()
        
        # Clear existing jobs
        schedule.clear()
        
        # Setup job
        if self.config.interval == "hourly":
            schedule.every().hour.do(self.create_backup)
        if self.config.interval == "daily":
            schedule.every().day.at(self.config.time_str).do(self.create_backup)
        elif self.config.interval == "weekly":
            schedule.every().monday.at(self.config.time_str).do(self.create_backup)
        elif self.config.interval == "monthly":
            # Schedule doesn't support monthly directly easily, stick to 30 days or logic
            schedule.every(30).days.at(self.config.time_str).do(self.create_backup)

        schedule.every(6).hours.do(lambda: self.verify_and_heal_recent(limit=25))

        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        logger.info("Backup scheduler started.")

    def stop_scheduler(self):
        self.stop_event.set()
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=1)
        logger.info("Backup scheduler stopped.")

    def _run_scheduler(self):
        if not schedule:
            return
        while not self.stop_event.is_set():
            schedule.run_pending()
            time.sleep(60)

# Singleton instance
backup_service = BackupService()
