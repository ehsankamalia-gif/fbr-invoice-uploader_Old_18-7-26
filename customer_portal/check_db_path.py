#!/usr/bin/env python
import os
import sys
from pathlib import Path

print('=== Checking SQLite Database Path ===')

if sys.platform == "win32":
    app_data = os.getenv("APPDATA")
    if app_data:
        db_dir = Path(app_data) / "EhsanTraderFBR"
        print(f"DB directory: {db_dir}")
        print(f"Directory exists: {db_dir.exists()}")
        
        db_path = db_dir / "fbr_invoices.db"
        print(f"DB file: {db_path}")
        print(f"File exists: {db_path.exists()}")
        
        if db_path.exists():
            print(f"File size: {db_path.stat().st_size} bytes")
