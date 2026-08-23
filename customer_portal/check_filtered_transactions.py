#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()

from portal.models import SpareLedgerTransaction
from django.db.models import Q

print("=== Filtered Spare Ledger Transactions ===")
transactions = SpareLedgerTransaction.objects.filter(
    Q(description__isnull=True) | ~Q(description__startswith='Advance Booking -')
).order_by('timestamp')
print(f"Total transactions after filter: {transactions.count()}")
print()

for tx in transactions:
    print(f"ID: {tx.id}")
    print(f"Timestamp: {tx.timestamp}")
    print(f"Trans Type: {tx.trans_type}")
    print(f"Amount: {tx.amount}")
    print(f"Description: {tx.description}")
    print(f"Month Key: {tx.month_key}")
    print("-" * 50)
