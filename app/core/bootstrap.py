
import sys
import subprocess
import os
import platform
import logging
from pathlib import Path

# Setup simple logging for bootstrapping before the main logger is ready
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - BOOTSTRAP - %(levelname)s - %(message)s'
)
logger = logging.getLogger("bootstrap")

class Bootstrapper:
    """Manages application environment setup and dependency verification."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.requirements_file = project_root / "requirements.txt"
        self.venv_dir = project_root / "venv"
        self.os_type = platform.system()
        
    def check_environment(self) -> bool:
        """Runs the complete environment setup process."""
        logger.info(f"Starting environment check on {self.os_type}...")
        
        try:
            # 1. Verify and install dependencies
            if not self.verify_dependencies():
                logger.warning("Dependencies missing. Attempting automatic installation...")
                if not self.install_dependencies():
                    logger.error("Failed to install dependencies automatically.")
                    return False
            
            # 2. Setup necessary directories
            self.setup_directories()
            
            # 3. Environment Variables (.env)
            self.setup_env_file()
            
            logger.info("Environment check completed successfully.")
            return True
        except Exception as e:
            logger.error(f"Critical error during bootstrap: {e}")
            return False

    def verify_dependencies(self) -> bool:
        """Checks if critical required packages are importable."""
        critical_packages = [
            "fastapi", "sqlalchemy", "pydantic", "requests", "PyQt6", 
            "cryptography", "pymysql", "openpyxl", "android_sms_gateway"
        ]
        
        for pkg in critical_packages:
            try:
                __import__(pkg)
            except ImportError:
                logger.warning(f"Critical package missing: {pkg}")
                return False
        return True

    def install_dependencies(self) -> bool:
        """Installs missing dependencies using pip."""
        logger.info("Installing dependencies from requirements.txt...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(self.requirements_file)])
            logger.info("Dependencies installed successfully.")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Pip installation failed: {e}")
            return False

    def setup_directories(self):
        """Creates required application directories if they don't exist."""
        dirs = ["logs", "backups", "temp", "exports"]
        for d in dirs:
            path = self.project_root / d
            if not path.exists():
                logger.info(f"Creating directory: {d}")
                path.mkdir(parents=True, exist_ok=True)

    def setup_env_file(self):
        """Creates a default .env file if missing."""
        env_file = self.project_root / ".env"
        env_example = self.project_root / ".env.example"
        
        if not env_file.exists():
            if env_example.exists():
                logger.info("Creating .env from .env.example")
                import shutil
                shutil.copy(str(env_example), str(env_file))
            else:
                logger.warning("Neither .env nor .env.example found. Creating empty .env")
                env_file.touch()

def run_bootstrap():
    """Entry point for the bootstrap process."""
    project_root = Path(__file__).resolve().parent.parent.parent
    bootstrapper = Bootstrapper(project_root)
    return bootstrapper.check_environment()

if __name__ == "__main__":
    if run_bootstrap():
        print("SUCCESS")
        sys.exit(0)
    else:
        print("FAILURE")
        sys.exit(1)
