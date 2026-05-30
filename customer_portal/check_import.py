
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'customer_portal.settings')

import django
django.setup()

print("Django setup complete!")

try:
    from portal.views import *
    print("All views imported successfully!")
except Exception as e:
    print(f"Error importing views: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
