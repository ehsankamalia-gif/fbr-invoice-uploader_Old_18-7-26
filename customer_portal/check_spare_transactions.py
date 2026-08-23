#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()

from portal.models import SpareLedgerTransaction

print("=== All Spare Ledger Transactions ===")
transactions = SpareLedgerTransaction.objects.all().order_by('id')
print(f"Total transactions in database: {transactions.count()}")
print()

for tx in transactions:
    print(f"ID: {tx.id}")
    print(f"Timestamp: {tx.timestamp}")
    print(f"Trans Type: {tx.trans_type}")
    print(f"Amount: {tx.amount}")
    print(f"Cash Type: {tx.cash_type}")
    print(f"Reference Number: {tx.reference_number}")
    print(f"Description: {tx.description}")
    print(f"Created By: {tx.created_by_user_id}")
    print(f"Month Key: {tx.month_key}")
    print("-" * 50)
