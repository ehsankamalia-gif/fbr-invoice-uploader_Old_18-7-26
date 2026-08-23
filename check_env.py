import sys
import os

print("Python executable:", sys.executable)
print("sys.path:", sys.path)
print("PATH environment variable:", os.environ.get("PATH", ""))

try:
    import django
    print("Django installed:", django.get_version())
except ImportError as e:
    print("Django not installed:", e)

try:
    import pip
    print("Pip list:")
    print(pip.__version__)
except ImportError as e:
    print("Pip not available:", e)