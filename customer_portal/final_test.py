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

# Get the page content
response = client.get('/custom-admin/spare-ledger-transactions/')

print(f'Page status code: {response.status_code}')
if response.status_code != 200:
    print('ERROR: Page not found')
else:
    content = response.content.decode('utf-8')
    
    # Check for transactions
    if 'No transactions found' in content:
        print('ERROR: No transactions found')
    else:
        print('Transactions found')
        
    # Check for specific transaction amounts
    if '25000.00' in content:
        print('Transaction 25000.00 found')
    if '109900.00' in content:
        print('Transaction 109900.00 found')
        
    # Check for totals
    if '944300.00' in content:
        print('Total credits correct')
    if '549500.00' in content:
        print('Total debits correct')
    if '394800.00' in content:
        print('Closing balance correct')
