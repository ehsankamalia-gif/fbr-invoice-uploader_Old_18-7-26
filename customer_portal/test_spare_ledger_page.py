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
    
    # Check if we're authenticated
    if 'Log out' in content:
        print('Authenticated successfully')
    else:
        print('Not authenticated')
        
    # Check if transactions are present
    if 'No transactions found' in content:
        print('No transactions found')
    else:
        print('Transactions found')
        
    # Print a snippet of the content to verify
    print('\n=== Page Content Snippet ===')
    print(content[:500])
