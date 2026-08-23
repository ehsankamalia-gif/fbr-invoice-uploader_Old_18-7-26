#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()

from portal.models import SpareLedgerTransaction
from django.db.models import Q

# Test the view logic
def test_view_logic():
    selected_month = None
    selected_trans_type = None
    
    transactions = SpareLedgerTransaction.objects.filter(
        Q(description__isnull=True) | ~Q(description__startswith='Advance Booking -')
    ).order_by('timestamp')
    
    print("Transactions after initial filter:", transactions.count())
    
    if selected_month:
        transactions = transactions.filter(month_key=selected_month)
    if selected_trans_type:
        transactions = transactions.filter(trans_type=selected_trans_type)
    
    print("Transactions after apply filters:", transactions.count())
    
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
    
    print(f"Total Credits: {total_credits}")
    print(f"Total Debits: {total_debits}")
    print(f"Closing Balance: {closing_balance}")
    
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
    
    print("Transactions with balance:", len(transactions_with_balance))
    for item in transactions_with_balance:
        print(f"- {item['transaction'].id}: {item['transaction'].trans_type} {item['transaction'].amount} - Balance: {item['balance']}")

test_view_logic()
