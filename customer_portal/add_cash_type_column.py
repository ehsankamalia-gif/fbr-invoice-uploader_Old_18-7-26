#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()

print('=== Adding cash_type column to spare_ledger_transactions ===')

from django.db import connection

with connection.cursor() as cursor:
    try:
        # Check if cash_type column exists
        cursor.execute("PRAGMA table_info(spare_ledger_transactions)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'cash_type' not in columns:
            print("Adding cash_type column...")
            cursor.execute(
                "ALTER TABLE spare_ledger_transactions ADD COLUMN cash_type VARCHAR(20) DEFAULT 'HARD_CASH'"
            )
            print("Column added successfully")
        else:
            print("cash_type column already exists")
            
    except Exception as e:
        print(f"Error: {e}")

# Verify the column was added
print("\n=== Verifying column exists ===\n")
with connection.cursor() as cursor:
    cursor.execute("PRAGMA table_info(spare_ledger_transactions)")
    for col in cursor.fetchall():
        print(f"{col[1]} - {col[2]}")
