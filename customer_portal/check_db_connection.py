#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()
from django.db import connection

print('=== Database Connection ===')
print(f'DB Engine: {connection.vendor}')
print(f'DB Name: {connection.settings_dict["NAME"]}')
