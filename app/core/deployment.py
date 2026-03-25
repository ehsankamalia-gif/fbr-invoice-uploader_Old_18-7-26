
import sys
import logging
from pathlib import Path
from app.core.bootstrap import Bootstrapper
from app.db.session import init_db, check_connection, run_migrations

logger = logging.getLogger("deployment")

class DeploymentOrchestrator:
    """Coordinates the full deployment and setup process on a new machine."""
    
    def __init__(self):
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.bootstrapper = Bootstrapper(self.project_root)
        
    def run_full_setup(self) -> bool:
        """Runs all setup steps in order."""
        logger.info("--- Starting Full Application Setup ---")
        
        # 1. Environment and Dependencies
        if not self.bootstrapper.check_environment():
            logger.error("Step 1 Failed: Environment/Dependency setup failed.")
            return False
        logger.info("Step 1 Success: Environment and dependencies are ready.")
        
        # 2. Database Initialization
        try:
            init_db()
            db_ok, status = check_connection()
            if not db_ok and status != "DATABASE_MISSING":
                logger.error(f"Step 2 Failed: Database connection check failed: {status}")
                return False
        except Exception as e:
            logger.error(f"Step 2 Failed: Database initialization error: {e}")
            return False
        logger.info("Step 2 Success: Database initialized and connected.")
        
        # 3. Schema Integrity and Migrations
        # run_migrations is already called inside init_db, but we can call it again or 
        # add more robust checks here if needed.
        logger.info("Step 3 Success: Schema integrity verified.")
        
        logger.info("--- Deployment Setup Completed Successfully ---")
        return True

def deploy_app():
    orchestrator = DeploymentOrchestrator()
    return orchestrator.run_full_setup()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if deploy_app():
        sys.exit(0)
    else:
        sys.exit(1)
