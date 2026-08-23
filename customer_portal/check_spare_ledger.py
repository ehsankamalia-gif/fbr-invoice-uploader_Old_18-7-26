#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()
from portal.models import SpareLedgerTransaction, SpareLedgerMonthlyClose

print('=== Spare Ledger Transactions ===')
print(f'Total transactions: {SpareLedgerTransaction.objects.count()}')
transactions = SpareLedgerTransaction.objects.all()
for tx in transactions[:10]:
    print(f'{tx.id} - {tx.timestamp} - {tx.trans_type} - {tx.amount} - {tx.cash_type}')

print('\n=== Spare Ledger Monthly Closes ===')
print(f'Total monthly closes: {SpareLedgerMonthlyClose.objects.count()}')
closes = SpareLedgerMonthlyClose.objects.all()
for close in closes[:10]:
    print(f'{close.id} - {close.month_key} - {close.balance}')

print('\n=== Database Connection ===')
from django.db import connection
print(f'Connection to {connection.settings_dict["NAME"]}')
