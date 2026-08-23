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

# Get the page content
response = client.get('/custom-admin/spare-ledger-transactions/')
content = response.content.decode('utf-8')

# Find the summary cards
print('=== Summary Cards ===')
try:
    cards_start = content.index('<!-- Summary Cards -->')
    cards_end = content.index('<!-- Filters -->', cards_start)
    print(content[cards_start:cards_end])
except Exception as e:
    print(f'Error finding summary cards: {e}')
