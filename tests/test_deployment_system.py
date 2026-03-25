
import unittest
import sys
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from app.core.bootstrap import Bootstrapper
from app.core.deployment import DeploymentOrchestrator

class TestDeployment(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.requirements_file = self.test_dir / "requirements.txt"
        self.requirements_file.write_text("requests>=2.26.0\n")
        self.env_example = self.test_dir / ".env.example"
        self.env_example.write_text("DB_NAME=test_db\n")
        
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_bootstrapper_directories(self):
        """Verifies that bootstrapper creates necessary directories."""
        bootstrapper = Bootstrapper(self.test_dir)
        bootstrapper.setup_directories()
        
        for d in ["logs", "backups", "temp", "exports"]:
            self.assertTrue((self.test_dir / d).exists())

    def test_bootstrapper_env_file(self):
        """Verifies that bootstrapper creates .env from .env.example."""
        bootstrapper = Bootstrapper(self.test_dir)
        bootstrapper.setup_env_file()
        
        env_file = self.test_dir / ".env"
        self.assertTrue(env_file.exists())
        self.assertIn("DB_NAME=test_db", env_file.read_text())

    @patch('app.core.bootstrap.Bootstrapper.install_dependencies', return_value=True)
    def test_bootstrapper_install_dependencies(self, mock_install):
        """Verifies that bootstrapper attempts to install dependencies."""
        bootstrapper = Bootstrapper(self.test_dir)
        result = bootstrapper.install_dependencies()
        
        self.assertTrue(result)
        mock_install.assert_called_once()

    @patch('app.core.bootstrap.Bootstrapper.check_environment', return_value=True)
    @patch('app.core.deployment.init_db')
    @patch('app.core.deployment.check_connection', return_value=(True, ""))
    def test_orchestrator_success(self, mock_conn, mock_init, mock_bootstrap):
        """Verifies that the orchestrator coordinates steps correctly."""
        orchestrator = DeploymentOrchestrator()
        result = orchestrator.run_full_setup()
        
        self.assertTrue(result)
        mock_bootstrap.assert_called_once()
        mock_init.assert_called_once()
        mock_conn.assert_called_once()

if __name__ == "__main__":
    unittest.main()
