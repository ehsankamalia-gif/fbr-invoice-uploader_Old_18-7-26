import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMessageBox

from app.qt_ui.main_window import MainWindow
from app.db.session import check_connection, init_db


def main() -> None:
    # --- Fix for QWebEngine GPU Crash on some Windows machines ---
    # Force software rendering if needed
    os.environ["QT_QUICK_BACKEND"] = "software"
    os.environ["QTWEBENGINE_DISABLE_GPU"] = "1"
    os.environ["QT_ANGLE_PLATFORM"] = "d3d9" # Sometimes d3d9 works better than d3d11 when gpu is failing
    
    base_dir = Path(__file__).resolve().parent.parent
    if str(base_dir) not in sys.path:
        sys.path.append(str(base_dir))

    # Initialize database and run migrations
    try:
        init_db()
    except Exception as e:
        print(f"Database initialization failed: {e}")

    # Add Chromium flags to further ensure stability
    sys_args = sys.argv
    sys_args.append("--disable-gpu")
    sys_args.append("--no-sandbox")
    sys_args.append("--disable-software-rasterizer")
    
    app = QApplication(sys_args)

    if not check_connection():
        QMessageBox.critical(
            None,
            "Connection Error",
            "Database connection failed.\nPlease update your connection settings and restart the application.",
        )
        sys.exit(1)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
