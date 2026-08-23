#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()

from portal.models import SpareLedgerTransaction

# Test the context calculation logic directly
def test_context_calculation():
    # Get all transactions
    transactions = SpareLedgerTransaction.objects.all().order_by('timestamp')
    
    print('=== Transactions ===')
    for tx in transactions:
        print(f'{tx.id}: {tx.trans_type} ${tx.amount:.2f}')
    
    # Calculate totals
    total_credits = 0.0
    total_debits = 0.0
    
    for tx in transactions:
        amount = float(tx.amount or 0)
        if tx.trans_type == "CREDIT":
            total_credits += amount
        else:
            total_debits += amount
    
    closing_balance = total_credits - total_debits
    
    print(f'\n=== Calculated Totals ===')
    print(f'Total Credits: {total_credits:.2f}')
    print(f'Total Debits: {total_debits:.2f}')
    print(f'Closing Balance: {closing_balance:.2f}')
    
    # Calculate running balance
    transactions_with_balance = []
    running_balance = 0.0
    
    for tx in transactions:
        amount = float(tx.amount or 0)
        if tx.trans_type == "CREDIT":
            running_balance += amount
        else:
            running_balance -= amount
            
        transactions_with_balance.append({
            'transaction': tx,
            'balance': running_balance
        })
    
    print(f'\n=== Transactions with Running Balance ===')
    for item in transactions_with_balance:
        tx = item['transaction']
        print(f'{tx.id}: {tx.trans_type} ${tx.amount:.2f} - Balance: ${item["balance"]:.2f}')

test_context_calculation()
