#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()

print('=== Getting Spare Ledger Transactions Table Columns ===')

# Get table columns using Django's connection
from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("PRAGMA table_info(spare_ledger_transactions)")
    columns = cursor.fetchall()
    for column in columns:
        print(f"{column[1]} - {column[2]}")

# Try to get transactions without cash_type column
print("\n=== Getting Transactions (without cash_type) ===")
from portal.models import SpareLedgerTransaction

try:
    # Use only fields that exist in the database
    transactions = SpareLedgerTransaction.objects.values('id', 'timestamp', 'trans_type', 'amount')
    print(f"Found {len(transactions)} transactions")
    for tx in transactions:
        print(f"{tx['timestamp']} - {tx['trans_type']} - {tx['amount']}")
except Exception as e:
    print(f"Error: {e}")

print("\n=== DB Path =====")
print(connection.settings_dict["NAME"])
