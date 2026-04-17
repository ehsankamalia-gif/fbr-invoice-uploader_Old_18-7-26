import unittest
import os
import shutil
import json
import zipfile
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# Mock settings before importing BackupService
import sys
from unittest.mock import PropertyMock

# Create a temporary directory for testing
TEST_DIR = Path(__file__).parent / "temp_backup_test"
TEST_DB_FILE = TEST_DIR / "test_db.sqlite"
TEST_BACKUP_DIR = TEST_DIR / "backups"

class MockSettings:
    def __init__(self):
        self.DB_URL = f"sqlite:///{TEST_DB_FILE.as_posix()}"

# Mock the settings module
mock_settings = MockSettings()
with patch.dict('sys.modules', {'app.core.config': MagicMock(settings=mock_settings)}):
    from app.services.backup_service import BackupService, BackupConfig

class TestBackupService(unittest.TestCase):
    def setUp(self):
        # Setup test environment
        if TEST_DIR.exists():
            shutil.rmtree(TEST_DIR)
        TEST_DIR.mkdir(parents=True, exist_ok=True)
        TEST_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        
        # Create a dummy SQLite file
        import sqlite3
        conn = sqlite3.connect(TEST_DB_FILE)
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO test (name) VALUES ('Initial Data')")
        conn.commit()
        conn.close()
        
        # Initialize BackupService with test paths
        with patch('app.services.backup_service.platformdirs', None):
            with patch.object(BackupService, 'load_config', return_value=BackupConfig(
                enabled=True,
                local_path=str(TEST_BACKUP_DIR),
                encrypt=True,
                encryption_key="invalid_key_for_test"
            )):
                self.service = BackupService()
                # Overwrite some paths for testing
                self.service.app_data_dir = TEST_DIR
                self.service.config_file = TEST_DIR / "backup_config.json"
                self.service.config.local_path = str(TEST_BACKUP_DIR)
                # Ensure a real base64-encoded 32-byte key (Fernet key format is compatible)
                from cryptography.fernet import Fernet
                self.service.config.encryption_key = Fernet.generate_key().decode()
                self.service.config.encryption_keys = []
                self.service.config.active_key_id = ""
                self.service.save_config()

    def tearDown(self):
        if TEST_DIR.exists():
            shutil.rmtree(TEST_DIR)

    def test_create_backup_success(self):
        """Test successful backup creation with encryption."""
        result = self.service.create_backup(is_manual=True)
        self.assertTrue(result["success"])
        self.assertIn("Backup created", result["message"])
        
        # Verify file exists
        backup_path = Path(result["path"])
        self.assertTrue(backup_path.exists())
        self.assertEqual(backup_path.suffix, ".enc")

    def test_restore_backup_success(self):
        """Test successful restoration from an encrypted backup."""
        # 1. Create backup
        backup_result = self.service.create_backup(is_manual=True)
        backup_path = backup_result["path"]
        
        # 2. Modify database to simulate data loss/change
        import sqlite3
        conn = sqlite3.connect(TEST_DB_FILE)
        conn.execute("UPDATE test SET name = 'Modified Data'")
        conn.commit()
        conn.close()
        
        # 3. Restore
        restore_result = self.service.restore_backup(backup_path)
        self.assertTrue(restore_result["success"])
        
        # 4. Verify data is restored
        conn = sqlite3.connect(TEST_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM test")
        name = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(name, "Initial Data")

    def test_integrity_check(self):
        """Test that integrity check detects healthy database."""
        self.assertTrue(self.service.verify_db_integrity())

    def test_backup_retention(self):
        """Test that old backups are cleaned up according to retention policy."""
        self.service.config.retention_days = 1
        self.service.save_config()
        
        # Create an old backup file
        old_file = TEST_BACKUP_DIR / "backup_old.zip"
        old_file.touch()
        # Set modification time to 2 days ago
        two_days_ago = datetime.now() - timedelta(days=2)
        os.utime(old_file, (two_days_ago.timestamp(), two_days_ago.timestamp()))
        
        # Create a new backup to trigger cleanup
        self.service.create_backup()
        
        # Verify old file is gone
        self.assertFalse(old_file.exists())

    def test_corrupted_backup_detection(self):
        """Test that restore fails for corrupted/tampered backup files."""
        # 1. Create backup
        backup_result = self.service.create_backup()
        backup_path = Path(backup_result["path"])
        
        # 2. Tamper with the file
        with open(backup_path, "wb") as f:
            f.write(b"corrupted data")
            
        # 3. Attempt restore
        restore_result = self.service.restore_backup(str(backup_path))
        self.assertFalse(restore_result["success"])

    def test_incremental_backup_and_restore(self):
        """Test incremental backup creates smaller delta and can restore via chain."""
        full = self.service.create_backup(is_manual=True)
        self.assertTrue(full["success"])
        full_path = full["path"]

        import sqlite3
        conn = sqlite3.connect(TEST_DB_FILE)
        conn.execute("UPDATE test SET name = 'After Full'")
        conn.commit()
        conn.close()

        self.service.config.backup_mode = "incremental"
        inc = self.service.create_backup(is_manual=True)
        self.assertTrue(inc["success"])
        inc_path = inc["path"]

        conn = sqlite3.connect(TEST_DB_FILE)
        conn.execute("UPDATE test SET name = 'Corrupted Local'")
        conn.commit()
        conn.close()

        restore_result = self.service.restore_backup(inc_path)
        self.assertTrue(restore_result["success"])

        conn = sqlite3.connect(TEST_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM test")
        name = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(name, "After Full")

    def test_multi_destination_self_heal(self):
        """Test copy to a secondary filesystem destination and self-heal corrupted copy."""
        dest_dir = TEST_DIR / "dest1"
        dest_dir.mkdir(parents=True, exist_ok=True)
        self.service.config.destinations = [{"type": "network_share", "path": str(dest_dir), "enabled": True}]
        self.service.save_config()

        res = self.service.create_backup(is_manual=True)
        self.assertTrue(res["success"])
        backup_path = Path(res["path"])
        manifest_path = Path(res["manifest"])

        dst_backup = dest_dir / backup_path.name
        dst_manifest = dest_dir / manifest_path.name
        self.assertTrue(dst_backup.exists())
        self.assertTrue(dst_manifest.exists())

        with open(dst_backup, "wb") as f:
            f.write(b"tamper")

        heal = self.service.verify_and_heal_backup(str(backup_path))
        self.assertTrue(heal["success"])
        self.assertTrue(dst_backup.exists())

if __name__ == "__main__":
    unittest.main()
