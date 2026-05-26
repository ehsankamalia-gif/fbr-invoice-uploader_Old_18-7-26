
from portal.models import CustomerPortalAuth
from django.contrib.auth.hashers import make_password

print("Fixing CustomerPortalAuth passwords...")

auths = CustomerPortalAuth.objects.all()
for auth in auths:
    print(f"Processing: {auth.customer.name} (ID: {auth.id})")
    print(f"  Current phone: {auth.phone_number}")
    
    # Ensure phone number is set from customer
    if not auth.phone_number or auth.phone_number.strip() == '':
        auth.phone_number = auth.customer.phone or ''
        print(f"  Updated phone to: {auth.phone_number}")
    
    # Ensure password is hashed correctly
    auth.password_hash = make_password('123456789')
    print(f"  Set password to: 123456789 (hashed)")
    
    auth.save()
    print("  Saved!")

print("\nDone! All portal accounts updated!")
