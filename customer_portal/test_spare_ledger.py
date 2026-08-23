#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()
from django.test import Client
from django.contrib.auth.models import User
from portal.models import SpareLedgerTransaction

print('=== Checking Spare Ledger Transactions ===')
print(f'Total transactions in DB: {SpareLedgerTransaction.objects.count()}')

print('\n=== Transactions ===')
transactions = SpareLedgerTransaction.objects.all()
for tx in transactions:
    print(f'{tx.timestamp} - {tx.trans_type} - {tx.amount} - {tx.cash_type}')

print('\n=== Database Connection ===')
from django.db import connection
print(f'DB Engine: {connection.vendor}')
print(f'DB Name: {connection.settings_dict["NAME"]}')
