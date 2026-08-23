#!/usr/bin/env python
"""
Script to create a Django superuser without interactive prompts.
"""
import os
import sys
import django
from pathlib import Path

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')
django.setup()

from django.contrib.auth.models import User

def create_superuser():
    """Create a superuser if it doesn't exist"""
    username = 'admin'
    email = 'admin@example.com'
    password = 'admin123'
    
    try:
        # Check if user exists
        user = User.objects.get(username=username)
        print(f"Superuser '{username}' already exists")
    except User.DoesNotExist:
        # Create new superuser
        user = User.objects.create_superuser(
            username=username,
            email=email,
            password=password
        )
        print(f"Superuser '{username}' created successfully!")
        print(f"  Username: {username}")
        print(f"  Password: {password}")
        print(f"  Email: {email}")

if __name__ == '__main__':
    create_superuser()
