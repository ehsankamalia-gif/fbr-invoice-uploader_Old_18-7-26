
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
django.setup()

from portal.forms import LoginForm
from portal.models import CustomerPortalAuth

print("=== Testing LoginForm ===")

# Test with existing customer
test_phone = '03437780080'
test_password = '123456789'

print(f"Testing with Phone: {test_phone}, Password: {test_password}")

form_data = {
    'phone_number': test_phone,
    'password': test_password
}

form = LoginForm(form_data)

if form.is_valid():
    print("SUCCESS: Form is valid!")
    print(f"  Customer: {form.cleaned_data['customer'].name}")
    print(f"  Auth ID: {form.cleaned_data['auth'].id}")
else:
    print("ERROR: Form is invalid!")
    print("  Errors:", form.errors)
    print("  Non-field errors:", form.non_field_errors())

# Also check the password hash directly
print("\n=== Checking Password Hash Directly ===")
auth = CustomerPortalAuth.objects.get(phone_number=test_phone)
from django.contrib.auth.hashers import check_password
print(f"Password hash: {auth.password_hash}")
print(f"Check password '{test_password}': {check_password(test_password, auth.password_hash)}")
