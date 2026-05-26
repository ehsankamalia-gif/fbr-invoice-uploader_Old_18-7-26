
from portal.forms import LoginForm
from portal.models import CustomerPortalAuth
from django.contrib.auth.hashers import check_password

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
print(f"Password hash: {auth.password_hash}")
print(f"Check password '{test_password}': {check_password(test_password, auth.password_hash)}")

# Write to file
with open('login_test_shell_output.txt', 'w', encoding='utf-8') as f:
    f.write("=== Testing LoginForm ===\n")
    f.write(f"Testing with Phone: {test_phone}, Password: {test_password}\n")
    if form.is_valid():
        f.write("SUCCESS: Form is valid!\n")
        f.write(f"  Customer: {form.cleaned_data['customer'].name}\n")
        f.write(f"  Auth ID: {form.cleaned_data['auth'].id}\n")
    else:
        f.write("ERROR: Form is invalid!\n")
        f.write(f"  Errors: {form.errors}\n")
        f.write(f"  Non-field errors: {form.non_field_errors()}\n")
    f.write("\n=== Checking Password Hash Directly ===\n")
    f.write(f"Password hash: {auth.password_hash}\n")
    f.write(f"Check password '{test_password}': {check_password(test_password, auth.password_hash)}\n")
