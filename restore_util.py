import os
import sys
import shutil
import zipfile
import json
import time
import subprocess
from pathlib import Path

def restore_standalone(backup_path_str, db_path_str, encryption_key=None):
    """Standalone restore function to be run in a separate process."""
    print(f"Starting professional restore process...")
    print(f"Backup: {backup_path_str}")
    print(f"Target: {db_path_str}")
    
    backup_path = Path(backup_path_str)
    db_path = Path(db_path_str)
    
    # 1. Wait for main process to exit
    print("Waiting for main application to close...")
    time.sleep(2) 
    
    try:
        source_zip = backup_path
        temp_zip = None
        
        # 2. Handle Encryption if needed
        if backup_path.suffix == ".enc":
            print("Decrypting backup...")
            from cryptography.fernet import Fernet
            if not encryption_key:
                print("Error: Encryption key missing.")
                return False
                
            fernet = Fernet(encryption_key.encode())
            with open(backup_path, "rb") as f:
                encrypted_data = f.read()
            
            decrypted_data = fernet.decrypt(encrypted_data)
            temp_zip = backup_path.with_suffix(".zip.restore_temp")
            with open(temp_zip, "wb") as f:
                f.write(decrypted_data)
            source_zip = temp_zip

        # 3. Extract and Overwrite
        print("Extracting files...")
        with zipfile.ZipFile(source_zip, 'r') as zipf:
            if "metadata.json" not in zipf.namelist():
                print("Error: Invalid backup (missing metadata).")
                return False
            
            metadata = json.loads(zipf.read("metadata.json").decode())
            original_filename = metadata.get("original_filename", db_path.name)
            
            # Backup current DB as final safety
            if db_path.exists():
                shutil.copy2(db_path, db_path.with_suffix(".bak.pre_restore"))
            
            # Extract with retries for Windows locks
            max_retries = 10
            for i in range(max_retries):
                try:
                    zipf.extract(original_filename, path=db_path.parent)
                    print("Extraction successful.")
                    break
                except Exception as e:
                    if i < max_retries - 1:
                        print(f"File locked, retrying ({i+1}/{max_retries})...")
                        time.sleep(1)
                    else:
                        raise e

        # 4. Cleanup
        if temp_zip and temp_zip.exists():
            os.remove(temp_zip)
            
        print("Restore completed successfully!")
        return True

    except Exception as e:
        print(f"CRITICAL ERROR DURING RESTORE: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: restore_util.py <backup_path> <db_path> [encryption_key] [app_executable]")
        sys.exit(1)
        
    backup_path = sys.argv[1]
    db_path = sys.argv[2]
    key = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "None" else None
    app_exe = sys.argv[4] if len(sys.argv) > 4 else None
    
    success = restore_standalone(backup_path, db_path, key)
    
    if success and app_exe:
        print(f"Restarting application: {app_exe}")
        if app_exe.endswith(".exe"):
            os.startfile(app_exe)
        elif "app.main" in app_exe or "app/main" in app_exe:
            # If running as script, use module-based launch to avoid ModuleNotFoundError
            # The root directory is the parent of where restore_util.py is
            project_root = Path(__file__).resolve().parent
            subprocess.Popen([sys.executable, "-m", "app.main"], cwd=str(project_root))
        else:
            subprocess.Popen([sys.executable, app_exe])
    
    print("Restore utility exiting in 3 seconds...")
    time.sleep(3)
    sys.exit(0 if success else 1)
