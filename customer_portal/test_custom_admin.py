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

# Get admin user (should exist from previous setup)
try:
    user = User.objects.get(username='admin')
    print('Admin user found:', user.username)
except User.DoesNotExist:
    print('Admin user not found!')
    sys.exit(1)

# Login as admin
login_success = client.login(username='admin', password='admin123')
print('Login successful:', login_success)

# Test custom admin URLs
print('\nTesting custom admin URLs:')
url_tests = [
    '/custom-admin/',
    '/custom-admin/customers/',
    '/custom-admin/sales/',
    '/custom-admin/payments/',
    '/custom-admin/inventory/',
    '/custom-admin/transactions/',
    '/custom-admin/portal-auths/',
    '/admin/credit-customers/',
]

for url in url_tests:
    response = client.get(url)
    print(f'{response.status_code} - {url}')
    if response.status_code == 200:
        print(f'  Success! Page returned {len(response.content)} bytes')
    elif response.status_code == 302:
        print(f'  Redirected to: {response.url}')
    elif response.status_code == 404:
        print(f'  ERROR: Page not found')
    else:
        print(f'  ERROR: Status code {response.status_code}')
