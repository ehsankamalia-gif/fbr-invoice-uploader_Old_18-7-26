#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()

from django.test import Client
from django.contrib.auth.models import User

# Create test client
client = Client()

# Login as admin
login_success = client.login(username='admin', password='admin123')
print(f'Login successful: {login_success}')

# Test the spare parts ledger transactions page
response = client.get('/custom-admin/spare-ledger-transactions/')
print(f'\nPage status code: {response.status_code}')

if response.status_code == 200:
    content = response.content.decode('utf-8')
    
    print('\n=== Page Content Analysis ===')
    
    # Find the summary cards section and check values
    try:
        cards_start = content.index('<!-- Summary Cards -->')
        cards_end = content.index('<!-- Filters -->', cards_start)
        cards_content = content[cards_start:cards_end]
        
        if '944300.00' in cards_content:
            print('Total Credits is correct')
        if '549500.00' in cards_content:
            print('Total Debits is correct')
        if '394800.00' in cards_content:
            print('Current Balance is correct')
            
    except Exception as e:
        print(f'Error finding summary cards: {e}')
        
    # Check if transactions are being displayed
    if 'No transactions found' in content:
        print('No transactions message is displayed')
    else:
        transaction_count = content.count('border-b border-gray-100')
        print(f'Transactions found: {transaction_count}')
        
    # Check if actual transaction data is present
    if '25000.00' in content:
        print('Transaction with amount 25000.00 found')
    if '109900.00' in content:
        print('Transaction with amount 109900.00 found')
        
    print(f'\nPage content length: {len(content)} characters')
    
else:
    print(f'❌ Error accessing page: Status code {response.status_code}')
    print(response.content.decode('utf-8')[:500])
