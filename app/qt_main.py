import sys
import os
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QFont, QFontDatabase, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QLabel,
    QProgressBar,
    QMessageBox,
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QDateEdit,
    QDateTimeEdit,
    QTimeEdit,
)

from app.db.session import check_connection, init_db
from app.qt_ui.copy_support import CopySupportManager
from reporting.server import start_reporting_server

from PyQt6.QtCore import QObject, QEvent

class _FontManager(QObject):
    def __init__(self, app: QApplication):
        super().__init__(app)
        self._app = app
        self._ui_font: QFont | None = None
        self._urdu_input_font: QFont | None = None

    def refresh_from_settings(self) -> None:
        try:
            from app.services.settings_service import settings_service
            cfg = settings_service.get_app_config() or {}
        except Exception:
            cfg = {}

        self._ui_font = self._build_ui_font(cfg)
        self._urdu_input_font = self._build_urdu_font(cfg)

        if self._ui_font is not None:
            self._app.setFont(self._ui_font)
        else:
            self._app.setFont(QFont())

        self.apply_existing_widgets()

    def apply_existing_widgets(self) -> None:
        for w in self._app.allWidgets():
            self._apply_to_widget(w)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.ChildAdded, QEvent.Type.Show):
            try:
                self._apply_to_widget(obj)
            except Exception:
                pass
        return super().eventFilter(obj, event)

    def _apply_to_widget(self, w) -> None:
        if w is None:
            return

        if self._ui_font is not None and hasattr(w, "setFont"):
            try:
                w.setFont(self._ui_font)
            except Exception:
                pass

        if self._urdu_input_font is None:
            return

        if isinstance(
            w,
            (
                QLineEdit,
                QTextEdit,
                QPlainTextEdit,
                QComboBox,
                QSpinBox,
                QDoubleSpinBox,
                QDateEdit,
                QDateTimeEdit,
                QTimeEdit,
            ),
        ):
            try:
                w.setFont(self._urdu_input_font)
            except Exception:
                pass
            if isinstance(w, QComboBox):
                try:
                    view = w.view()
                    if view is not None:
                        view.setFont(self._urdu_input_font)
                except Exception:
                    pass

    def _build_ui_font(self, cfg: dict) -> QFont | None:
        if not cfg.get("ui_font_enabled"):
            return None

        size = int(cfg.get("ui_font_size") or 13)
        size = max(8, min(24, size))

        family = str(cfg.get("ui_font_family") or "").strip()
        if family and family not in set(QFontDatabase.families()):
            family = ""

        if family:
            return QFont(family, size)

        default_font = self._app.font()
        default_font.setPointSize(size)
        return default_font

    def _build_urdu_font(self, cfg: dict) -> QFont | None:
        if not cfg.get("urdu_font_enabled"):
            return None

        size = int(cfg.get("urdu_font_size") or 14)
        size = max(8, min(24, size))

        family = str(cfg.get("urdu_font_family") or "").strip()
        path = str(cfg.get("urdu_font_path") or "").strip()

        if path and os.path.exists(path):
            font_id = QFontDatabase.addApplicationFont(path)
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    family = families[0]

        if not family:
            candidates = [
                "Jameel Noori Nastaleeq",
                "Noori Nastaleeq",
                "Noto Nastaliq Urdu",
            ]
            available = set(QFontDatabase.families())
            for cand in candidates:
                if cand in available:
                    family = cand
                    break

        if not family:
            return None

        return QFont(family, size)

def _apply_font_to_input_widgets(app: QApplication, font: QFont) -> None:
    for w in app.allWidgets():
        if isinstance(
            w,
            (
                QLineEdit,
                QTextEdit,
                QPlainTextEdit,
                QComboBox,
                QSpinBox,
                QDoubleSpinBox,
                QDateEdit,
                QDateTimeEdit,
                QTimeEdit,
            ),
        ):
            w.setFont(font)
            if isinstance(w, QComboBox):
                try:
                    view = w.view()
                    if view is not None:
                        view.setFont(font)
                except Exception:
                    pass

def _apply_urdu_font(app: QApplication) -> None:
    return

def _asset_path(*parts: str) -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass, *parts)
    base_dir = Path(__file__).resolve().parent.parent
    return base_dir.joinpath(*parts)

class _StartupDialog(QDialog):
    def __init__(self, app: QApplication):
        super().__init__(None)
        self._app = app

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._image_label = QLabel(self)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._image_label)

        self._status_label = QLabel("Launching…", self)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(False)
        layout.addWidget(self._progress)

        self._apply_splash_image()
        self.adjustSize()
        self._center_on_screen()

    def set_status(self, text: str) -> None:
        self._status_label.setText(text)
        self._app.processEvents()

    def _apply_splash_image(self) -> None:
        splash_path = _asset_path("assets", "splash.png")
        if splash_path.exists():
            pixmap = QPixmap(str(splash_path))
            if not pixmap.isNull():
                self._image_label.setPixmap(
                    pixmap.scaledToWidth(520, Qt.TransformationMode.SmoothTransformation)
                )

    def _center_on_screen(self) -> None:
        screen = self._app.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(geo.center())
        self.move(frame.topLeft())

def main() -> None:
    # Show splash screen as early as possible
    app = QApplication(sys.argv)
    startup = _StartupDialog(app)
    startup.show()
    app.processEvents()

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

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    
    base_dir = Path(__file__).resolve().parent.parent
    if str(base_dir) not in sys.path:
        sys.path.append(str(base_dir))

    sys_args = sys.argv
    sys_args.append("--no-sandbox")

    import PyQt6.QtWebEngineWidgets  # noqa: F401

    startup.set_status("Initializing database…")
    try:
        init_db()
        from app.services.settings_service import settings_service
        settings_service.initialize_if_connected()
    except Exception as e:
        print(f"Database initialization failed: {e}")

    startup.set_status("Starting reporting…")
    # Start server in background thread to avoid blocking splash screen
    import threading
    threading.Thread(
        target=start_reporting_server,
        daemon=True,
        name="ReportingServerStartup"
    ).start()

    startup.set_status("Loading user interface…")
    from app.qt_ui.main_window import MainWindow
    font_manager = _FontManager(app)
    copy_support_manager = CopySupportManager(app)
    app.installEventFilter(font_manager)
    app.installEventFilter(copy_support_manager)
    app._font_manager = font_manager
    app._copy_support_manager = copy_support_manager
    font_manager.refresh_from_settings()
    copy_support_manager.apply_existing_widgets()

    startup.set_status("Checking database…")
    db_success, db_status = check_connection()
    if not db_success and db_status != "DATABASE_MISSING":
        startup.close()
        QMessageBox.critical(
            None,
            "Connection Error",
            f"Database connection failed:\n{db_status}\n\nPlease check your server and restart the application.",
        )
        sys.exit(1)

    startup.set_status("Finalizing…")
    app.processEvents()
    window = MainWindow(db_status=db_status)
    startup.close()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
