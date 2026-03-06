import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMessageBox

from app.qt_ui.main_window import MainWindow
from app.db.session import check_connection, init_db


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    if str(base_dir) not in sys.path:
        sys.path.append(str(base_dir))

    # Initialize database and run migrations
    try:
        init_db()
    except Exception as e:
        print(f"Database initialization failed: {e}")

    app = QApplication(sys.argv)

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
