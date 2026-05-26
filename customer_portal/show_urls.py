
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "customer_portal.settings")

import django
from django.urls import get_resolver

django.setup()

print("All registered URL patterns:")
print("-" * 60)

resolver = get_resolver()
for pattern in resolver.url_patterns:
    print(f"  {pattern.pattern}")
