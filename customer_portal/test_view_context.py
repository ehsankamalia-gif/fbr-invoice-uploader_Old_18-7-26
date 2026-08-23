#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()

from portal.views import custom_admin_spare_ledger_transactions_view
from django.test import RequestFactory
from django.contrib.auth.models import User

# Create a test request
factory = RequestFactory()
request = factory.get('/custom-admin/spare-ledger-transactions/')

# Create and login a test user
user = User.objects.create_superuser('testuser', 'test@example.com', 'testpassword')
request.user = user

# Call the view directly
response = custom_admin_spare_ledger_transactions_view(request)

print('=== View Response Status ===')
print(f'Status Code: {response.status_code}')

print('\n=== Context Data ===')
for key, value in response.context_data.items():
    if key in ['total_credits', 'total_debits', 'closing_balance']:
        print(f'{key}: {value:.2f}')
    elif key == 'transactions_with_balance':
        print(f'{key}: {len(value)} transactions')
    elif key == 'unique_months':
        print(f'{key}: {len(value)} months')
    else:
        print(f'{key}: {value}')

print('\n=== Transactions with Balance ===')
for item in response.context_data['transactions_with_balance']:
    tx = item['transaction']
    print(f'{tx.id}: {tx.trans_type} {tx.amount:.2f} - Balance: {item["balance"]:.2f}')
