#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()

from django.db import connection
from portal.models import SpareLedgerTransaction

print("=== Database Connection Configuration ===")
print(f"Engine: {connection.vendor}")
print(f"Host: {connection.settings_dict['HOST']}")
print(f"Port: {connection.settings_dict['PORT']}")
print(f"Database: {connection.settings_dict['NAME']}")
print(f"User: {connection.settings_dict['USER']}")
print()

print("=== Spare Ledger Transactions ===")
try:
    transactions = SpareLedgerTransaction.objects.all()
    print(f"Total transactions: {len(transactions)}")
    
    if transactions:
        print("Last 5 transactions:")
        for tx in transactions[:5]:
            print(f"- {tx.timestamp} | {tx.trans_type} | {tx.amount} | {tx.cash_type}")
except Exception as e:
    print(f"Error: {e}")
