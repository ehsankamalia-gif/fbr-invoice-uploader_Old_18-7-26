import sys
import os
import subprocess

print("=== Virtual Environment Verification ===")
print()

print("1. Current directory:", os.getcwd())
print()

print("2. Python executable path:", sys.executable)
print()

# Check if venv directory exists
venv_dir = os.path.join(os.getcwd(), "venv")
print("3. venv directory exists:", os.path.exists(venv_dir))
if os.path.exists(venv_dir):
    print("   venv directory contents:", os.listdir(venv_dir))
    print()

# Check if pip is available in venv
venv_pip_path = os.path.join(venv_dir, "Scripts", "pip.exe")
print("4. venv pip path exists:", os.path.exists(venv_pip_path))
if os.path.exists(venv_pip_path):
    try:
        result = subprocess.run([venv_pip_path, "list"], capture_output=True, text=True, timeout=60)
        print("   venv pip list:", result.stdout if result.returncode == 0 else result.stderr)
        print()
    except Exception as e:
        print("   venv pip list failed:", str(e))
        print()

# Check if Python is available in venv
venv_python_path = os.path.join(venv_dir, "Scripts", "python.exe")
print("5. venv python path exists:", os.path.exists(venv_python_path))
if os.path.exists(venv_python_path):
    try:
        result = subprocess.run([venv_python_path, "-c", "import sys; print('Successfully imported sys'); print('sys.path:', sys.path)"], 
                              capture_output=True, text=True, timeout=30)
        print("   venv python test:", result.stdout if result.returncode == 0 else result.stderr)
        print()
        
        result = subprocess.run([venv_python_path, "-c", "import django; print('Django version:', django.get_version())"], 
                              capture_output=True, text=True, timeout=30)
        print("   venv django test:", result.stdout if result.returncode == 0 else result.stderr)
    except Exception as e:
        print("   venv python test failed:", str(e))