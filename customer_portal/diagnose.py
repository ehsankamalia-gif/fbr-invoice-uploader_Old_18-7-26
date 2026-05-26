
import sys
import subprocess

print("=" * 60)
print("  Customer Portal Diagnostic Tool")
print("=" * 60)
print()

print("[1] Checking Python version...")
print(f"    Python: {sys.version}")
print()

print("[2] Checking for Django...")
try:
    import django
    print(f"    ✅ Django installed: {django.get_version()}")
    django_ok = True
except ImportError:
    print("    ❌ Django NOT installed!")
    django_ok = False
print()

print("[3] Checking other dependencies...")
for pkg in ['dotenv', 'cryptography']:
    try:
        if pkg == 'dotenv':
            import dotenv
            print(f"    ✅ python-dotenv installed")
        else:
            import cryptography
            print(f"    ✅ cryptography installed")
    except ImportError:
        print(f"    ❌ {pkg} NOT installed!")
print()

print("[4] Checking directory structure...")
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
files = os.listdir('.')
required = ['manage.py', 'customer_portal', 'portal', 'templates']
for r in required:
    if r in files:
        print(f"    ✅ {r} found")
    else:
        print(f"    ❌ {r} NOT found!")
print()

print("[5] Checking if we can run Django...")
if django_ok:
    try:
        result = subprocess.run(
            [sys.executable, 'manage.py', 'check'],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print("    ✅ Django check passed!")
        else:
            print("    ❌ Django check failed!")
            print("    Output:", result.stdout)
            print("    Errors:", result.stderr)
    except Exception as e:
        print(f"    ❌ Error: {e}")
else:
    print("    ⚠️  Skipping - Django not installed")
print()

print("=" * 60)
print("  What to do next:")
print("=" * 60)
if not django_ok:
    print("1. Install dependencies first:")
    print("   pip install -r requirements.txt")
else:
    print("1. Create admin superuser:")
    print("   python manage.py createsuperuser")
    print()
    print("2. Run the server:")
    print("   python manage.py runserver")
print("=" * 60)
