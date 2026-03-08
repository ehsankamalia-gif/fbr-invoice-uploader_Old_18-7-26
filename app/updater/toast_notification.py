from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QApplication
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QColor, QPalette

class ToastNotification(QWidget):
    """
    A professional, non-intrusive 'Toast' notification that appears 
    in the bottom-right corner of the screen.
    """
    clicked = pyqtSignal()

    def __init__(self, title: str, message: str, parent=None, duration_ms: int = 8000, 
                 show_action: bool = True, bg_color: str = "#2c3e50"):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.duration_ms = duration_ms
        self._init_ui(title, message, show_action, bg_color)
        
        # Setup fade-in animation
        self.setWindowOpacity(0.0)
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(400)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _init_ui(self, title: str, message: str, show_action: bool, bg_color: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Container frame for styling
        self.container = QWidget()
        self.container.setObjectName("toastContainer")
        self.container.setStyleSheet(f"""
            QWidget#toastContainer {{
                background-color: {bg_color};
                border: 1px solid #34495e;
                border-radius: 8px;
            }}
            QLabel#title {{
                color: #ecf0f1;
                font-weight: bold;
                font-size: 14px;
            }}
            QLabel#message {{
                color: #bdc3c7;
                font-size: 12px;
            }}
            QPushButton#actionBtn {{
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 12px;
                font-weight: bold;
                font-size: 11px;
            }}
            QPushButton#actionBtn:hover {{
                background-color: #2980b9;
            }}
            QPushButton#closeBtn {{
                color: #95a5a6;
                background: transparent;
                border: none;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton#closeBtn:hover {{
                color: white;
            }}
        """)
        
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(15, 12, 15, 15)
        container_layout.setSpacing(8)
        
        # Header row (Title + Close)
        header_layout = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("title")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        close_btn = QPushButton("×")
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide_notification)
        header_layout.addWidget(close_btn)
        
        container_layout.addLayout(header_layout)
        
        # Message row
        msg_label = QLabel(message)
        msg_label.setObjectName("message")
        msg_label.setWordWrap(True)
        container_layout.addWidget(msg_label)
        
        # Action row
        if show_action:
            action_layout = QHBoxLayout()
            action_layout.addStretch()
            
            self.action_btn = QPushButton("View Details")
            self.action_btn.setObjectName("actionBtn")
            self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.action_btn.clicked.connect(self._on_action_clicked)
            action_layout.addWidget(self.action_btn)
            
            container_layout.addLayout(action_layout)
        
        layout.addWidget(self.container)
        self.setFixedWidth(320)

    def _on_action_clicked(self):
        self.clicked.emit()
        self.hide_notification()

    def show_notification(self):
        # Position in bottom-right corner of the primary screen
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.width() - self.width() - 20
        y = screen.height() - self.height() - 20
        self.move(x, y)
        
        self.show()
        self.animation.start()
        
        # Auto-hide after duration
        if self.duration_ms > 0:
            QTimer.singleShot(self.duration_ms, self.hide_notification)

    def hide_notification(self):
        if self.animation.state() == QPropertyAnimation.State.Running:
            return
            
        self.animation.setDirection(QPropertyAnimation.Direction.Backward)
        self.animation.finished.connect(self.close)
        self.animation.start()
