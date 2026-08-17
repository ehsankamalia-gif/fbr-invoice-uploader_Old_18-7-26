
import sys
from pathlib import Path
import os

# Fix import path
sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import QTimer
import sys
import os

def test_upload_status():
    # Import main window after path fixing
    from app.qt_ui.main_window import MainWindow
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    
    print("Application started!")
    print(f"Upload status widget exists: {hasattr(window, 'invoice_upload_status_label')}")
    
    if hasattr(window, 'invoice_upload_status_label'):
        print(f"Current status text: '{window.invoice_upload_status_label.text()}'")
        print(f"Widget is visible: {window.invoice_upload_status_label.isVisible()}")
        
        # Test updating status
        window._update_invoice_upload_status()
        print(f"After update: '{window.invoice_upload_status_label.text()}'")
    
    # Exit after 3 seconds
    QTimer.singleShot(3000, app.quit)
    return app.exec()

if __name__ == "__main__":
    sys.exit(test_upload_status())
