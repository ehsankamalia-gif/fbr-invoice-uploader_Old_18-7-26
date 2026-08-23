#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()

from django.db import connection

print('=== Checking if tables exist ===')
with connection.cursor() as cursor:
    cursor.execute("SHOW TABLES LIKE 'spare_ledger_%'")
    tables = cursor.fetchall()
    print(f'Spare ledger tables: {[table[0] for table in tables]}')
    
    if tables:
        print('\n=== Spare Ledger Transactions ===')
        cursor.execute('SELECT COUNT(*) FROM spare_ledger_transactions')
        count = cursor.fetchone()[0]
        print(f'Total transactions: {count}')
        
        if count > 0:
            cursor.execute('SELECT id, timestamp, trans_type, amount, cash_type FROM spare_ledger_transactions ORDER BY timestamp DESC LIMIT 10')
            rows = cursor.fetchall()
            for row in rows:
                print(f'{row[0]} - {row[1]} - {row[2]} - {row[3]} - {row[4]}')
