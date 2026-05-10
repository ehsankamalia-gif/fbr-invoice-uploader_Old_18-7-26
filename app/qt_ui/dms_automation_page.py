
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFrame,
    QGridLayout,
    QMessageBox,
    QSizePolicy,
    QScrollArea,
)
import os
import sys
import json
from pathlib import Path


class DMSAutomationPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #f8f9fa;")
        self._submitted_data = []
        self._init_ui()

    def _init_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        scroll_content = QWidget()
        main_layout = QVBoxLayout(scroll_content)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(30)

        header_layout = QHBoxLayout()
        header = QLabel("DMS Portal Automation")
        header.setStyleSheet("font-size: 28px; color: #2c3e50; font-weight: bold;")
        header_layout.addWidget(header)
        header_layout.addStretch(1)
        main_layout.addLayout(header_layout)

        info_frame = self._create_info_frame()
        main_layout.addWidget(info_frame)

        form_frame = self._create_form_frame()
        main_layout.addWidget(form_frame)

        status_frame = self._create_status_frame()
        main_layout.addWidget(status_frame)

        instructions_frame = self._create_instructions_frame()
        main_layout.addWidget(instructions_frame)

        main_layout.addStretch(1)
        
        scroll.setWidget(scroll_content)
        
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll)

    def _create_info_frame(self):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
                padding: 20px;
            }
        """)
        layout = QVBoxLayout(frame)
        
        title = QLabel("🤖 DMS Automation Module")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(title)
        
        desc = QLabel("This is a completely independent module for automating DMS Portal operations.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #7f8c8d; font-size: 14px; margin-bottom: 15px;")
        layout.addWidget(desc)
        
        features = QLabel("Features:\n• Run in background thread\n• Persistent browser profile\n• Auto-fill vehicle details\n• No interaction with main application")
        features.setWordWrap(True)
        features.setStyleSheet("color: #34495e; font-size: 13px;")
        layout.addWidget(features)
        
        return frame

    def _create_form_frame(self):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
                padding: 25px;
            }
        """)
        layout = QVBoxLayout(frame)
        
        title = QLabel("Vehicle Details (Both Fields Required)")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 15px;")
        layout.addWidget(title)
        
        grid = QGridLayout()
        grid.setSpacing(15)
        
        chassis_label = QLabel("Chassis Number *")
        chassis_label.setStyleSheet("font-size: 14px; color: #2c3e50; font-weight: 500;")
        grid.addWidget(chassis_label, 0, 0)
        
        self.dms_chassis_input = QLineEdit()
        self.dms_chassis_input.setPlaceholderText("Enter chassis number (required)")
        self.dms_chassis_input.setStyleSheet("padding: 10px; font-size: 14px;")
        self.dms_chassis_input.textChanged.connect(self._validate_fields)
        self.dms_chassis_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        grid.addWidget(self.dms_chassis_input, 0, 1)
        
        self.chassis_error_label = QLabel("")
        self.chassis_error_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
        self.chassis_error_label.setVisible(False)
        grid.addWidget(self.chassis_error_label, 1, 1)
        
        engine_label = QLabel("Engine Number *")
        engine_label.setStyleSheet("font-size: 14px; color: #2c3e50; font-weight: 500;")
        grid.addWidget(engine_label, 2, 0)
        
        self.dms_engine_input = QLineEdit()
        self.dms_engine_input.setPlaceholderText("Enter engine number (required)")
        self.dms_engine_input.setStyleSheet("padding: 10px; font-size: 14px;")
        self.dms_engine_input.textChanged.connect(self._validate_fields)
        self.dms_engine_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        grid.addWidget(self.dms_engine_input, 2, 1)
        
        self.engine_error_label = QLabel("")
        self.engine_error_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
        self.engine_error_label.setVisible(False)
        grid.addWidget(self.engine_error_label, 3, 1)
        
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        
        layout.addSpacing(20)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        
        self.submit_btn = QPushButton("✅ Submit Vehicle Details")
        self.submit_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px 25px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
                min-width: 220px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        self.submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit_btn.clicked.connect(self._submit_form)
        self.submit_btn.setEnabled(False)
        btn_layout.addWidget(self.submit_btn)
        
        self.clear_btn = QPushButton("🗑️ Clear Form")
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #f8f9fa;
                color: #6c757d;
                border: 1px solid #dee2e6;
                padding: 10px 25px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #e2e6ea;
            }
        """)
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear_form)
        btn_layout.addWidget(self.clear_btn)
        
        layout.addLayout(btn_layout)
        
        return frame

    def _create_status_frame(self):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
                padding: 20px;
            }
        """)
        layout = QVBoxLayout(frame)
        
        title = QLabel("📋 Submission History")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(title)
        
        self.submission_count_label = QLabel("No submissions yet")
        self.submission_count_label.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        layout.addWidget(self.submission_count_label)
        
        return frame

    def _create_instructions_frame(self):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 12px;
                padding: 20px;
            }
        """)
        layout = QVBoxLayout(frame)
        
        title = QLabel("🚀 Open DMS Automation")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; margin-bottom: 10px;")
        layout.addWidget(title)
        
        steps = QLabel("Click the button below to open the DMS automation directory where you can run the browser automation.")
        steps.setWordWrap(True)
        steps.setStyleSheet("color: #34495e; font-size: 13px; line-height: 1.6; margin-bottom: 15px;")
        layout.addWidget(steps)
        
        open_btn_layout = QHBoxLayout()
        open_btn_layout.addStretch(1)
        
        open_btn = QPushButton("📂 Open DMS Automation Directory")
        open_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px 25px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
                min-width: 280px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(self._open_dms_portal)
        open_btn_layout.addWidget(open_btn)
        
        layout.addLayout(open_btn_layout)
        
        return frame

    def _validate_fields(self):
        chassis_valid = len(self.dms_chassis_input.text().strip()) > 0
        engine_valid = len(self.dms_engine_input.text().strip()) > 0
        
        self.submit_btn.setEnabled(chassis_valid and engine_valid)
        
        if not chassis_valid and self.dms_chassis_input.text() != "":
            self.chassis_error_label.setText("Chassis number is required")
            self.chassis_error_label.setVisible(True)
        else:
            self.chassis_error_label.setVisible(False)
        
        if not engine_valid and self.dms_engine_input.text() != "":
            self.engine_error_label.setText("Engine number is required")
            self.engine_error_label.setVisible(True)
        else:
            self.engine_error_label.setVisible(False)

    def _submit_form(self):
        chassis = self.dms_chassis_input.text().strip()
        engine = self.dms_engine_input.text().strip()
        
        if not chassis or not engine:
            QMessageBox.warning(
                self,
                "Validation Error",
                "Both Chassis Number and Engine Number are required!"
            )
            return
        
        try:
            from datetime import datetime
            
            data_dir = Path(__file__).parent.parent.parent / "dms_automation" / "data"
            data_dir.mkdir(exist_ok=True)
            
            submissions_file = data_dir / "submissions.json"
            
            if submissions_file.exists():
                with open(submissions_file, 'r') as f:
                    submissions = json.load(f)
            else:
                submissions = []
            
            submission = {
                "chassis_number": chassis,
                "engine_number": engine,
                "submitted_at": datetime.now().isoformat()
            }
            
            submissions.append(submission)
            
            with open(submissions_file, 'w') as f:
                json.dump(submissions, f, indent=2)
            
            self._submitted_data.append(submission)
            self._update_submission_count()
            
            QMessageBox.information(
                self,
                "Success!",
                f"Vehicle details submitted successfully!\n\nChassis: {chassis}\nEngine: {engine}"
            )
            
            self._clear_form()
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save submission: {str(e)}"
            )

    def _clear_form(self):
        self.dms_chassis_input.clear()
        self.dms_engine_input.clear()
        self.chassis_error_label.setVisible(False)
        self.engine_error_label.setVisible(False)
        self.submit_btn.setEnabled(False)

    def _update_submission_count(self):
        count = len(self._submitted_data)
        if count == 0:
            self.submission_count_label.setText("No submissions yet")
        elif count == 1:
            self.submission_count_label.setText(f"1 submission recorded")
        else:
            self.submission_count_label.setText(f"{count} submissions recorded")

    def _open_dms_portal(self):
        dms_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "dms_automation")
        dms_dir = os.path.abspath(dms_dir)
        
        if os.path.exists(dms_dir):
            try:
                if sys.platform == "win32":
                    os.startfile(dms_dir)
                else:
                    import subprocess
                    subprocess.Popen(["explorer" if sys.platform == "win32" else "xdg-open", dms_dir])
                
                QMessageBox.information(
                    self,
                    "DMS Automation",
                    f"DMS automation directory opened!\n\nPlease follow the instructions in README.md to set up and run the automation."
                )
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Error",
                    f"Failed to open directory: {str(e)}"
                )
        else:
            QMessageBox.warning(
                self,
                "Not Found",
                f"DMS automation directory not found at:\n{dms_dir}"
            )
