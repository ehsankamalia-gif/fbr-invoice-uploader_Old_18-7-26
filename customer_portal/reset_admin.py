
#!/usr/bin/env python
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')

import django
django.setup()

from django.contrib.auth.models import User

print("=" * 50)
print("   ADMIN ACCOUNT RESET TOOL")
print("=" * 50)
print()

# Check if admin user exists
admin_user = User.objects.filter(username='admin').first()

if admin_user:
    print(f"Found existing admin user: {admin_user.username}")
    print("Resetting password to: admin123")
    admin_user.set_password('admin123')
    admin_user.is_staff = True
    admin_user.is_superuser = True
    admin_user.save()
    print("✓ Password reset successfully!")
else:
    print("No admin user found - creating new one!")
    admin_user = User.objects.create_superuser(
        username='admin',
        email='admin@example.com',
        password='admin123'
    )
    print("✓ Admin user created successfully!")

print()
print("=" * 50)
print("   ADMIN CREDENTIALS:")
print("=" * 50)
print(f"  Username: admin")
print(f"  Password: admin123")
print("=" * 50)
print()
print("Now go to: http://127.0.0.1:8000/admin")
print()
input("Press Enter to exit...")
