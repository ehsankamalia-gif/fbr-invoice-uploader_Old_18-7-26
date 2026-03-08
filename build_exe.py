import os
import sys
import shutil
import subprocess
from pathlib import Path

def build():
    # 1. Setup paths
    project_root = Path(__file__).resolve().parent
    app_main = project_root / "app" / "qt_main.py"
    dist_dir = project_root / "dist"
    build_dir = project_root / "build"
    
    # 2. Clean previous builds
    # Proactively kill the app if it is running to avoid PermissionError
    if sys.platform == "win32":
        try:
            print("Checking for running instances of EhsanTraderFBR.exe...")
            subprocess.run(["taskkill", "/F", "/IM", "EhsanTraderFBR.exe", "/T"], 
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    try:
        if dist_dir.exists():
            print(f"Cleaning {dist_dir}...")
            shutil.rmtree(dist_dir)
        if build_dir.exists():
            print(f"Cleaning {build_dir}...")
            shutil.rmtree(build_dir)
    except PermissionError:
        print("\nERROR: Permission Denied while cleaning 'dist' or 'build' folder.")
        print("Please make sure EhsanTraderFBR.exe is not running and no folder is open in another program.")
        sys.exit(1)
        
    # 3. Define PyInstaller command
    # Using 'python -m PyInstaller' is more robust than calling 'pyinstaller' directly
    
    # Robustly find PyQt6 path without crashing the build script
    pyqt6_path = ""
    try:
        import PyQt6
        pyqt6_path = os.path.dirname(PyQt6.__file__)
        print(f"Found PyQt6 at: {pyqt6_path}")
    except ImportError:
        print("WARNING: PyQt6 not found in current Python path. Attempting to bundle using PyInstaller hooks...")

    cmd = [
        "python", "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "EhsanTraderFBR",
        "--add-data", f"version.json{os.pathsep}.",
        "--add-data", f"app/updater{os.pathsep}app/updater",
    ]

    # Only add force-data inclusion if path was found
    if pyqt6_path:
        cmd.extend(["--add-data", f"{pyqt6_path}{os.pathsep}PyQt6"])

    cmd.extend([
        "--collect-all", "PyQt6",
        "--collect-all", "customtkinter",
        "--hidden-import", "PyQt6.QtCore",
        "--hidden-import", "PyQt6.QtGui",
        "--hidden-import", "PyQt6.QtWidgets",
        "--hidden-import", "PyQt6.sip",
        "--hidden-import", "sqlite3",
        "--hidden-import", "pymysql", # Explicitly include MySQL driver
        "--hidden-import", "sqlalchemy",
        "--hidden-import", "tzdata",
        "--hidden-import", "PIL.SpiderImagePlugin",
        "--clean",
        str(app_main)
    ])
    
    print(f"Executing: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True)
        print("\nBuild successful! Executable created in 'dist/' folder.")
    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    build()
