#!/usr/bin/env python
import os
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
import django
django.setup()

from portal.models import SpareLedgerTransaction
from django.db import connection

print('=== Database Connection ===')
print(f'Engine: {connection.vendor}')
print(f'Name: {connection.settings_dict.get("NAME")}')
print(f'Host: {connection.settings_dict.get("HOST")}')
print(f'Port: {connection.settings_dict.get("PORT")}')
print()

print('=== SpareLedgerTransaction Records ===')
try:
    count = SpareLedgerTransaction.objects.count()
    print(f'Total records: {count}')
    
    if count > 0:
        records = SpareLedgerTransaction.objects.all().order_by('-id')[:5]
        print('Latest 5 records:')
        for record in records:
            print(f'  ID: {record.id}, Type: {record.trans_type}, Amount: {record.amount}, Description: {record.description}')
    else:
        print('No records found in SpareLedgerTransaction')
        
except Exception as e:
    print(f'Error accessing SpareLedgerTransaction: {e}')

print()
print('=== Database Tables ===')
with connection.cursor() as cursor:
    cursor.execute('SHOW TABLES')
    tables = cursor.fetchall()
    print('Tables in database:')
    for table in tables:
        print(f'  {table[0]}')
