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
    
    print('\n=== Checking page content ===')
    
    # Check if transactions are present
    if '25000.00' in content:
        print('Transaction with amount 25000.00 found')
    else:
        print('Transaction with amount 25000.00 NOT found')
        
    # Check if filters are present
    if 'All Months' in content:
        print('Month filter found')
    else:
        print('Month filter NOT found')
        
    if 'All Types' in content:
        print('Transaction type filter found')
    else:
        print('Transaction type filter NOT found')
        
    # Check if no transactions message is present
    if 'No transactions found' in content:
        print('"No transactions found" message is present')
    else:
        print('"No transactions found" message is NOT present')
        
    # Check if summary cards are showing data
    if '25,000.00' in content:
        print('Total credits card is showing correct amount')
    else:
        print('Total credits card is NOT showing correct amount')
else:
    print(f'❌ Error accessing page: Status code {response.status_code}')
    print(response.content.decode('utf-8')[:500])
