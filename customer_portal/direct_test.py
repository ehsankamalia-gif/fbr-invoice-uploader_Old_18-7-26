
import sys
import os

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')

import django
django.setup()

from portal.models import CustomerPortalAuth
from django.contrib.auth.hashers import check_password, make_password

print("Direct test script starting...")
output = []
output.append("=== Direct Test ===")

auths = CustomerPortalAuth.objects.all()
for auth in auths:
    output.append(f"Auth ID: {auth.id}")
    output.append(f"Customer: {auth.customer.name}")
    output.append(f"Phone: '{auth.phone_number}'")
    output.append(f"Password hash: {auth.password_hash[:50]}...")
    output.append(f"Is Active: {auth.is_active}")
    
    # Test password
    test_pass = '123456789'
    is_valid = check_password(test_pass, auth.password_hash)
    output.append(f"Check password '{test_pass}': {is_valid}")
    
    if not is_valid:
        output.append("Re-hashing password to 123456789...")
        auth.password_hash = make_password(test_pass)
        auth.save()
        output.append("Password re-hashed!")
    output.append("---")

# Write output to file
with open(r'C:\temp\direct_test_output.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output))

print("Output written to C:\\temp\\direct_test_output.txt")
