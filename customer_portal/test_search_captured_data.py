#!/usr/bin/env python
"""Test search functionality for captured data"""

import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()

from portal.models import CapturedData
from django.test import Client

client = Client()
client.login(username='admin', password='admin123')

# Test search functionality
search_term = 'TAIMOOR'  # From first captured record
response = client.get(f'/custom-admin/captured-data/?search={search_term}')

print(f'Search response status: {response.status_code}')

if response.status_code == 200:
    content = response.content.decode('utf-8')
    print(f'Search for "{search_term}" in page content: "{search_term}" found' if search_term in content else f'Search for "{search_term}" failed')
    
    # Check if we see fewer records (since we're filtering)
    original_count = CapturedData.objects.filter(is_deleted=False).count()
    print(f'Total records: {original_count}')
    
    search_count = CapturedData.objects.filter(
        is_deleted=False,
        name__icontains=search_term
    ).count()
    print(f'Search results count: {search_count}')
