#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()

from django.test import Client
from portal.models import SpareLedgerTransaction

print("=== Total Transactions in Database ===")
print(f"{SpareLedgerTransaction.objects.count()} transactions")
print()

# Test the page
print("=== Transactions on Page ===")
client = Client()
client.login(username='admin', password='admin123')
response = client.get('/custom-admin/spare-ledger-transactions/')
content = response.content.decode('utf-8')

# Count transaction rows
transaction_count = content.count('<tr class="border-b border-gray-100')
print(f"{transaction_count} transactions on page")

# Check if 25000.00 is present
if '25000.00' in content:
    print("✅ 25000.00 transaction found")

# Check if other amounts are present
if '109900.00' in content:
    print("✅ 109900.00 transactions found")
if '159900.00' in content:
    print("✅ 159900.00 transaction found")
if '50000.00' in content:
    print("✅ 50000.00 transactions found")
