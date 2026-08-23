#!/usr/bin/env python
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print('=== Desktop Application Database Configuration ===')

from app.core.config import get_database_url, settings

print(f"DB URL from settings: {settings.DB_URL}")
print(f"DB URL from function: {get_database_url()}")

# Check if the database file exists
if "sqlite" in settings.DB_URL:
    db_path = settings.DB_URL.replace("sqlite:///", "")
    print(f"\nDB File: {db_path}")
    print(f"File exists: {os.path.exists(db_path)}")
    
    if os.path.exists(db_path):
        print(f"File size: {os.path.getsize(db_path)} bytes")
        
        # Check what tables are in the database
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cursor.fetchall()
        
        print(f"\nTables in database ({len(tables)}):")
        for table in tables:
            table_name = table[0]
            # Get row count for each table
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            
            if table_name == 'spare_ledger_transactions':
                print(f"  - {table_name} ({count} rows)")
                
                # Get columns for spare_ledger_transactions
                cursor.execute("PRAGMA table_info(spare_ledger_transactions)")
                columns = cursor.fetchall()
                col_names = [col[1] for col in columns]
                print(f"    Columns: {', '.join(col_names)}")
                
                # Get some data
                if count > 0:
                    cursor.execute("SELECT id, timestamp, trans_type, amount, cash_type FROM spare_ledger_transactions ORDER BY id DESC LIMIT 10")
                    transactions = cursor.fetchall()
                    print(f"    Latest transactions:")
                    for tx in transactions:
                        print(f"      - {tx[1]} - {tx[2]} - {tx[3]} - {tx[4]}")
                        
            else:
                print(f"  - {table_name} ({count} rows)")
                
        conn.close()
