#!/usr/bin/env python
"""Test script to verify captured data functionality"""

import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()

from portal.models import CapturedData
from django.test import Client
from django.contrib.auth.models import User

# Test database connection
try:
    count = CapturedData.objects.count()
    print(f"CapturedData records in database: {count}")
    
    if count > 0:
        print("\nFirst 5 captured records:")
        for record in CapturedData.objects.all().order_by('-created_at')[:5]:
            print(f"- {record.name or 'Unknown'} ({record.chassis_number or 'No chassis'})")
except Exception as e:
    print(f"Error accessing CapturedData: {e}")
    print("\nChecking if table exists in database...")
    
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("SHOW TABLES LIKE 'captured_data'")
        if cursor.fetchone():
            print("✓ captured_data table exists")
            
            cursor.execute("DESCRIBE captured_data")
            print("Table columns:")
            for row in cursor.fetchall():
                print(f"  {row[0]} - {row[1]}")
        else:
            print("✗ captured_data table does NOT exist")

# Test the view
print("\n=== Testing Captured Data View ===")
client = Client()

# Create a test user if not exists
try:
    user = User.objects.get(username='admin')
    print("Using existing admin user")
except User.DoesNotExist:
    user = User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print("Created new admin user")

# Login
login_success = client.login(username='admin', password='admin123')
if login_success:
    print("Login successful")
    
    # Test the view
    response = client.get('/custom-admin/captured-data/')
    print(f"View response status: {response.status_code}")
    
    if response.status_code == 200:
        print("View accessible")
        
        # Check if we can search
        search_response = client.get('/custom-admin/captured-data/?search=test')
        print(f"Search view response: {search_response.status_code}")
        
        # Check for content
        content = response.content.decode('utf-8')
        if 'Captured Data' in content:
            print("Page contains captured data section")
        else:
            print("Page does NOT contain captured data section")
            
        print(f"\nPage content snippet:")
        lines = content.split('\n')
        for i, line in enumerate(lines[:20]):
            print(f"{i+1:02d}: {line.strip()[:100]}...")
            
else:
    print("✗ Login failed")

print("\n=== Test completed ===")
