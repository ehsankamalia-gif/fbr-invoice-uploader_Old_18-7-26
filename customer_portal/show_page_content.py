#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()

from django.test import Client

# Create test client
client = Client()

# Login as admin
login_success = client.login(username='admin', password='admin123')
print('Login successful:', login_success)

# Test the spare parts ledger transactions page
response = client.get('/custom-admin/spare-ledger-transactions/')
print('Page status code:', response.status_code)

if response.status_code == 200:
    content = response.content.decode('utf-8')
    
    print('\n=== Page Content ===')
    print(content)
else:
    print('Error accessing page:', response.status_code)
    print(response.content.decode('utf-8'))
