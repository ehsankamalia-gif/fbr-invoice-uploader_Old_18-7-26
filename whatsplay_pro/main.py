import sys
import logging
from PyQt6.QtWidgets import QApplication
from whatsplay_pro.core.config import Config
from whatsplay_pro.core.logger import setup_logger
from whatsplay_pro.crm.database import init_db
from whatsplay_pro.gui.main_window import MainWindow

def main():
    """Main application entry point with proper initialization."""
    # 1. Setup Logging
    logger = setup_logger("WhatsPlayPro")
    logger.info("--- Starting WhatsPlay Pro Application ---")
    
    # 2. Ensure configuration and environment
    Config.ensure_dirs()
    
    # 3. Initialize Database
    try:
        init_db()
        logger.info("CRM Database initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
        sys.exit(1)
    
    # 4. Create PyQt Application
    app = QApplication(sys.argv)
    app.setApplicationName(Config.APP_NAME)
    app.setApplicationVersion(Config.VERSION)
    
    # 5. Launch Main Window
    try:
        window = MainWindow()
        window.show()
        logger.info("Main Window launched. Application started.")
        sys.exit(app.exec())
    except Exception as e:
        logger.critical(f"Unhandled exception during app execution: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
