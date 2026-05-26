
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
django.setup()

from portal.forms import LoginForm
from portal.models import CustomerPortalAuth

with open('login_test_output.txt', 'w', encoding='utf-8') as f:
    f.write("=== Testing LoginForm ===\n")

    # Test with existing customer
    test_phone = '03437780080'
    test_password = '123456789'

    f.write(f"Testing with Phone: {test_phone}, Password: {test_password}\n")

    form_data = {
        'phone_number': test_phone,
        'password': test_password
    }

    form = LoginForm(form_data)

    if form.is_valid():
        f.write("SUCCESS: Form is valid!\n")
        f.write(f"  Customer: {form.cleaned_data['customer'].name}\n")
        f.write(f"  Auth ID: {form.cleaned_data['auth'].id}\n")
    else:
        f.write("ERROR: Form is invalid!\n")
        f.write(f"  Errors: {form.errors}\n")
        f.write(f"  Non-field errors: {form.non_field_errors()}\n")

    # Also check the password hash directly
    f.write("\n=== Checking Password Hash Directly ===\n")
    auth = CustomerPortalAuth.objects.get(phone_number=test_phone)
    from django.contrib.auth.hashers import check_password
    f.write(f"Password hash: {auth.password_hash}\n")
    f.write(f"Check password '{test_password}': {check_password(test_password, auth.password_hash)}\n")

print("Output written to login_test_output.txt")
