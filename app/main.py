import sys
from pathlib import Path

# 1. Environment Bootstrap (Runs before any other imports)
def bootstrap():
    project_root = Path(__file__).resolve().parent.parent
    bootstrap_script = project_root / "app" / "core" / "bootstrap.py"
    
    if bootstrap_script.exists():
        # Add project root to sys.path so bootstrap can find its own modules if needed
        if str(project_root) not in sys.path:
            sys.path.append(str(project_root))
            
        try:
            from app.core.bootstrap import run_bootstrap
            if not run_bootstrap():
                print("CRITICAL: Environment setup failed. Please check logs.")
                sys.exit(1)
        except Exception as e:
            print(f"CRITICAL: Failed to initialize bootstrapper: {e}")
            sys.exit(1)

if __name__ == "__main__":
    bootstrap()
    
    # Now safe to import and run the app
    from app.qt_main import main as qt_main
    qt_main()
