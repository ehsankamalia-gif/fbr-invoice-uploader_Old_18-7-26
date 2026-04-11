import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMessageBox

from app.db.session import check_connection, init_db
from reporting.server import start_reporting_server

def main() -> None:
    # --- Fix for QWebEngine GPU Crash on some Windows machines ---
    # Force software rendering if needed
    os.environ["QT_QUICK_BACKEND"] = "software"
    os.environ["QTWEBENGINE_DISABLE_GPU"] = "1"
    os.environ["QT_OPENGL"] = "software"
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        "--ignore-gpu-blocklist "
        "--disable-gpu "
        "--disable-gpu-compositing "
        "--disable-d3d11 "
        "--disable-features=VizDisplayCompositor "
        "--log-level=3 "
        "--no-sandbox"
    )
    
    base_dir = Path(__file__).resolve().parent.parent
    if str(base_dir) not in sys.path:
        sys.path.append(str(base_dir))

    # Initialize database and run migrations FIRST
    # This ensures that when services are imported later (via MainWindow),
    # SessionLocal is already configured to the real DB.
    try:
        init_db()
        # Initialize default settings if DB is ready
        from app.services.settings_service import settings_service
        settings_service.initialize_if_connected()
    except Exception as e:
        print(f"Database initialization failed: {e}")
    
    start_reporting_server()

    # NOW import MainWindow
    from app.qt_ui.main_window import MainWindow

    # Add Chromium flags to further ensure stability
    sys_args = sys.argv
    sys_args.append("--no-sandbox")
    
    app = QApplication(sys_args)

    db_success, db_status = check_connection()
    if not db_success and db_status != "DATABASE_MISSING":
        QMessageBox.critical(
            None,
            "Connection Error",
            f"Database connection failed:\n{db_status}\n\nPlease check your server and restart the application.",
        )
        sys.exit(1)

    window = MainWindow(db_status=db_status)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
