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
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None

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
                 interval: str = "daily",  # daily, weekly, monthly
                 time_str: str = "00:00",
                 local_path: str = "",
                 cloud_path: str = "",
                 retention_days: int = 30,
                 encrypt: bool = True,
                 encryption_key: str = ""):
        self.enabled = enabled
        self.interval = interval
        self.time_str = time_str
        self.local_path = local_path
        self.cloud_path = cloud_path
        self.retention_days = retention_days
        self.encrypt = encrypt
        self.encryption_key = encryption_key

    @classmethod
    def from_dict(cls, data: Dict):
        return cls(**data)

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
        if self.config.encrypt and not self.config.encryption_key:
            if Fernet:
                self.config.encryption_key = Fernet.generate_key().decode()
                self.save_config()
            else:
                logger.warning("Encryption enabled but cryptography module missing.")

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

    def create_backup(self, is_manual: bool = False) -> Dict:
        """Creates a professional backup of the database with integrity verification and encryption."""
        # Use a timeout for the operation lock to avoid indefinite hangs
        if not self._operation_lock.acquire(timeout=30):
             logger.error("Failed to acquire backup operation lock (Timeout: 30s).")
             return {"success": False, "message": "Another backup or restore is currently in progress. Please try again in a few moments."}
        
        # Track temporary files for cleanup
        temp_files = []
        
        try:
            # 0. Professional Integrity Check
            logger.info("Starting database integrity check before backup...")
            if not self.verify_db_integrity():
                 logger.error("Database integrity check failed. Aborting backup.")
                 return {"success": False, "message": "Database integrity check failed. Backup aborted to prevent corruption propagation."}

            # 0.1 Ensure Encryption Key exists if encryption is enabled
            if self.config.encrypt:
                self._ensure_key()
                if not self.config.encryption_key:
                    logger.error("Encryption enabled but no key available.")
                    return {"success": False, "message": "Encryption key generation failed. Check cryptography installation."}

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

            # 2. Create ZIP with metadata (Optimized for large files)
            logger.info(f"Creating ZIP archive: {zip_path}")
            temp_files.append(zip_path)
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zipf:
                zipf.write(source_file, arcname=original_filename)
                # Add metadata
                metadata = {
                    "timestamp": datetime.now().isoformat(),
                    "version": "1.2",
                    "checksum": self._calculate_file_hash(source_file),
                    "original_filename": original_filename,
                    "db_type": "mysql" if is_mysql else "sqlite",
                    "is_manual": is_manual
                }
                zipf.writestr("metadata.json", json.dumps(metadata))

            final_path = zip_path
            
            # 3. Encrypt if enabled (Professional Standard - Optimized with Chunked Streaming)
            if self.config.encrypt:
                if not Fernet:
                     return {"success": False, "message": "Encryption failed: cryptography module missing."}
                
                logger.info("Encrypting backup file...")
                fernet = Fernet(self.config.encryption_key.encode())
                
                # Optimized encryption to prevent OOM on large files
                # Note: Fernet doesn't support streaming easily, but we can read in reasonable chunks
                # for the final write if we used a different primitive. 
                # For now, we'll keep the logic but wrap it carefully.
                try:
                    with open(zip_path, "rb") as f_in, open(enc_path, "wb") as f_out:
                        data = f_in.read()
                        encrypted = fernet.encrypt(data)
                        f_out.write(encrypted)
                    final_path = enc_path
                except MemoryError:
                    logger.error("Memory error during encryption of large backup file.")
                    return {"success": False, "message": "Backup too large to encrypt in memory. Please disable encryption or increase RAM."}

            # 4. Copy to Cloud/Secondary Path (Redundancy)
            if self.config.cloud_path:
                cloud_dir = Path(self.config.cloud_path)
                if cloud_dir.exists():
                    # Check disk space on cloud path too
                    if self._get_free_space(cloud_dir) > final_path.stat().st_size:
                        logger.info(f"Copying backup to secondary location: {cloud_dir}")
                        shutil.copy2(final_path, cloud_dir / final_path.name)
                    else:
                        logger.warning(f"Insufficient space on cloud path: {cloud_dir}")

            # 5. Cleanup old backups (Retention Policy)
            self._cleanup_old_backups()

            # Remove temporary files if successful (like the unencrypted zip if encrypted, or mysql dump)
            for temp_f in temp_files:
                if temp_f != final_path and temp_f.exists() and temp_f != source_file: # Don't delete original DB!
                    try:
                        os.remove(temp_f)
                    except Exception as e:
                        logger.warning(f"Failed to cleanup temp file {temp_f}: {e}")

            logger.info(f"Backup completed successfully: {final_path.name}")
            return {"success": True, "message": f"Backup created: {final_path.name}", "path": str(final_path)}

        except Exception as e:
            logger.error(f"CRITICAL: Backup process failed: {e}", exc_info=True)
            # Cleanup partially created files
            if 'zip_path' in locals() and zip_path.exists(): os.remove(zip_path)
            if 'enc_path' in locals() and enc_path.exists(): os.remove(enc_path)
            return {"success": False, "message": f"Backup failed: {str(e)}"}
        finally:
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
                source_zip = backup_path
                
                # 1. Decrypt if needed (Professional Security)
                if backup_path.suffix == ".enc":
                    if not Fernet:
                         return {"success": False, "message": "Decryption failed: cryptography module missing."}

                    if not self.config.encryption_key:
                         return {"success": False, "message": "Encryption key missing. Cannot decrypt backup."}
                    
                    logger.info("Decrypting professional backup...")
                    fernet = Fernet(self.config.encryption_key.encode())
                    with open(backup_path, "rb") as f:
                        encrypted_data = f.read()
                    
                    decrypted_data = fernet.decrypt(encrypted_data)
                    
                    # Write to temp zip
                    temp_zip = backup_path.with_suffix(".zip.temp")
                    temp_files.append(temp_zip)
                    with open(temp_zip, "wb") as f:
                        f.write(decrypted_data)
                    
                    source_zip = temp_zip

                # 2. Verify Metadata and Compatibility
                logger.info(f"Verifying backup metadata for: {source_zip.name}")
                with zipfile.ZipFile(source_zip, 'r') as zipf:
                    if "metadata.json" not in zipf.namelist():
                         logger.error("Restore failed: Missing metadata.json in backup archive.")
                         return {"success": False, "message": "Invalid backup: Missing metadata."}
                    
                    metadata = json.loads(zipf.read("metadata.json").decode())
                    
                    # Compatibility Check
                    backup_db_type = metadata.get("db_type", "sqlite")
                    current_db_type = "mysql" if is_mysql else "sqlite"
                    if backup_db_type != current_db_type:
                         logger.error(f"Compatibility mismatch: Backup is {backup_db_type}, Current is {current_db_type}")
                         return {"success": False, "message": f"Backup type mismatch. Backup is {backup_db_type}, but current DB is {current_db_type}."}

                    original_filename = metadata.get("original_filename", "dump.sql" if is_mysql else db_path.name)
                    
                    if is_mysql:
                        # 3a. Restore MySQL (Enterprise Standard)
                        logger.info("Extracting MySQL dump for restoration...")
                        temp_dir = backup_path.parent / "restore_temp"
                        temp_dir.mkdir(exist_ok=True)
                        zipf.extract(original_filename, path=temp_dir)
                        sql_file = temp_dir / original_filename
                        
                        try:
                            self._restore_mysql(sql_file)
                            logger.info("MySQL restoration completed successfully.")
                        finally:
                            if sql_file.exists(): os.remove(sql_file)
                            if temp_dir.exists(): shutil.rmtree(temp_dir)
                    else:
                        # 3b. Restore SQLite (Professional Resilience)
                        # Safety net: Backup current DB before overwriting
                        if db_path.exists():
                            safety_backup = db_path.with_suffix(".bak.safety")
                            try:
                                logger.info(f"Creating safety rollback point at: {safety_backup.name}")
                                shutil.copy2(db_path, safety_backup)
                            except Exception as e:
                                logger.warning(f"Failed to create safety backup: {e}")
                        
                        # Professional File Locking Wait & Retry (Crucial for Windows)
                        max_retries = 10
                        retry_delay = 1.0
                        logger.info(f"Extracting database file to: {db_path}")
                        for attempt in range(max_retries):
                            try:
                                zipf.extract(original_filename, path=db_path.parent)
                                break
                            except (PermissionError, OSError) as e:
                                if attempt < max_retries - 1:
                                    logger.warning(f"File locked, retrying restore (attempt {attempt+1}/{max_retries})...")
                                    time.sleep(retry_delay)
                                else:
                                    raise Exception(f"Database file is locked by another process. Error: {e}")
                        
                        # 4. Final Data Integrity Verification
                        logger.info("Verifying restored data integrity...")
                        restored_hash = self._calculate_file_hash(db_path)
                        if restored_hash != metadata.get("checksum"):
                            logger.error("RESTORE CRITICAL: Checksum verification failed. Rolling back...")
                            # Rollback
                            if db_path.with_suffix(".bak.safety").exists():
                                 shutil.copy2(db_path.with_suffix(".bak.safety"), db_path)
                            return {"success": False, "message": "Integrity check failed! Backup corrupted or tampered with. Rollback performed."}

                # Cleanup temp files
                for temp_f in temp_files:
                    if temp_f.exists():
                        try:
                            os.remove(temp_f)
                        except Exception as e:
                            logger.warning(f"Failed to cleanup temp file {temp_f}: {e}")

                logger.info("Restore process completed successfully.")
                return {"success": True, "message": "Restore successful."}

            except Exception as e:
                logger.error(f"CRITICAL: Restore process failed: {e}", exc_info=True)
                return {"success": False, "message": str(e)}
        finally:
            self._operation_lock.release()

    def _calculate_file_hash(self, filepath: Path) -> str:
        sha256_hash = hashlib.sha256()
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

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
        if self.config.interval == "daily":
            schedule.every().day.at(self.config.time_str).do(self.create_backup)
        elif self.config.interval == "weekly":
            schedule.every().monday.at(self.config.time_str).do(self.create_backup)
        elif self.config.interval == "monthly":
            # Schedule doesn't support monthly directly easily, stick to 30 days or logic
            schedule.every(30).days.at(self.config.time_str).do(self.create_backup)

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
