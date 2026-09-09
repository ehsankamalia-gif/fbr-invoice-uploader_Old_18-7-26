
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
        self.is_frozen = getattr(sys, "frozen", False)
        
    def check_environment(self) -> bool:
        """Runs the complete environment setup process."""
        logger.info(f"Starting environment check on {self.os_type}...")

        try:
            # 1. Verify and install dependencies.
            # A packaged build ships its own dependencies and has no pip or
            # requirements.txt to work with, so this step only applies to
            # source installs.
            if not self.is_frozen:
                if not self.verify_dependencies():
                    logger.warning("Dependencies missing. Attempting automatic installation...")
                    if not self.install_dependencies():
                        logger.error("Failed to install dependencies automatically.")
                        return False

            # 2. Setup necessary directories
            self.setup_directories()

            # 3. Environment Variables (.env)
            self.setup_env_file()

            # 4. Initialize Database (including migrations)
            if not self.init_database():
                logger.error("Database initialization failed.")
                return False
            
            logger.info("Environment check completed successfully.")
            return True
        except Exception as e:
            logger.error(f"Critical error during bootstrap: {e}")
            return False

    def verify_dependencies(self) -> bool:
        """Checks if critical required packages are importable."""
        critical_packages = [
            "fastapi", "uvicorn", "sqlalchemy", "pydantic", "requests", "PyQt6",
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

    def _writable_root(self) -> Path:
        """Where runtime files belong.

        Normally the configured project root. In a packaged build that root is a
        temporary extraction folder, so runtime files go to the data folder.
        """
        if not self.is_frozen:
            return self.project_root

        from app.core.paths import data_dir

        return data_dir()

    def setup_directories(self):
        """Creates required application directories if they don't exist."""
        root = self._writable_root()
        dirs = ["logs", "backups", "temp", "exports"]
        for d in dirs:
            path = root / d
            if not path.exists():
                logger.info(f"Creating directory: {d}")
                path.mkdir(parents=True, exist_ok=True)

    def setup_env_file(self):
        """Creates a default .env file if missing."""
        env_file = self._writable_root() / ".env"
        env_example = self.project_root / ".env.example"

        if self.is_frozen and not env_example.exists():
            from app.core.paths import resource_dir

            env_example = resource_dir() / ".env.example"

        if not env_file.exists():
            if env_example.exists():
                logger.info("Creating .env from .env.example")
                import shutil
                shutil.copy(str(env_example), str(env_file))
            else:
                logger.warning("Neither .env nor .env.example found. Creating empty .env")
                env_file.touch()

    def init_database(self) -> bool:
        """Initializes the database connection and runs migrations."""
        try:
            logger.info("Initializing database and running migrations...")
            from app.db.session import init_db
            init_db()
            return True
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            return False

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
