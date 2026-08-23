#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()

from django.test import Client
from portal.models import SpareLedgerTransaction

# Test the page
client = Client()
client.login(username='admin', password='admin123')
response = client.get('/custom-admin/spare-ledger-transactions/')
content = response.content.decode('utf-8')

print("=== Page Totals ===")

# Extract total credits
if 'Total Credits (In)' in content:
    start = content.find('Total Credits (In)')
    end = content.find('</p>', start)
    credits_text = content[start:end]
    start = credits_text.find('text-green-600">')
    credits = credits_text[start+len('text-green-600">'):].strip()
    print(f"Total Credits: {credits}")

# Extract total debits
if 'Spare Part Order' in content:
    start = content.find('Spare Part Order')
    end = content.find('</p>', start)
    debits_text = content[start:end]
    start = debits_text.find('text-red-600">')
    debits = debits_text[start+len('text-red-600">'):].strip()
    print(f"Total Debits: {debits}")

# Extract closing balance
if 'Current Balance' in content:
    start = content.find('Current Balance')
    end = content.find('</p>', start)
    balance_text = content[start:end]
    start = balance_text.find('text-blue-600">')
    balance = balance_text[start+len('text-blue-600">'):].strip()
    print(f"Closing Balance: {balance}")

print()

# Verify with database
print("=== Database Totals ===")
transactions = SpareLedgerTransaction.objects.all()
total_credits = 0
total_debits = 0
for tx in transactions:
    if tx.trans_type == 'CREDIT':
        total_credits += tx.amount
    elif tx.trans_type == 'DEBIT':
        total_debits += tx.amount

closing_balance = total_credits - total_debits

print(f"Total Credits: {total_credits:.2f}")
print(f"Total Debits: {total_debits:.2f}")
print(f"Closing Balance: {closing_balance:.2f}")
