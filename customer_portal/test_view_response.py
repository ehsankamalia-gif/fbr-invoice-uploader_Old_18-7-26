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

# Create superuser if it doesn't exist
try:
    user = User.objects.get(username='admin')
    print('Admin user exists')
except User.DoesNotExist:
    user = User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print('Admin user created')

# Login as admin
login_success = client.login(username='admin', password='admin123')
print(f'Login successful: {login_success}')

# Test the spare parts ledger transactions page
response = client.get('/custom-admin/spare-ledger-transactions/')
print(f'\nPage status code: {response.status_code}')

if response.status_code == 200:
    content = response.content.decode('utf-8')
    
    print('\n=== Page Content Analysis ===')
    
    # Check if summary cards have data
    if '0.00' in content and 'Total Credits' in content:
        print('Total Credits is showing 0.00')
    else:
        print('Total Credits is showing a positive value')
        
    if '0.00' in content and 'Spare Part Order' in content:
        print('Total Debits is showing 0.00')
    else:
        print('Total Debits is showing a positive value')
        
    if '0.00' in content and 'Current Balance' in content:
        print('Current Balance is showing 0.00')
    else:
        print('Current Balance is showing a positive value')
        
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
        
    # Check if table structure is present
    if 'Date/Time' in content and 'Source' in content and 'Reference' in content and 'Description' in content and 'Credit (In)' in content and 'SP Order' in content and 'Balance' in content and 'Month' in content:
        print('Table structure is complete')

    print(f'\nPage content length: {len(content)} characters')
    
else:
    print(f'❌ Error accessing page: Status code {response.status_code}')
    print(response.content.decode('utf-8')[:500])
