
"""
Credit Portal Credential Viewer - Qt UI Page
Completely separate - integrates with main app without modification
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from pathlib import Path
import os
import sys

project_root = Path(__file__).parent.parent


class CreditPortalCredentialViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customer Portal - Credential Manager")
        self.creds_dir = project_root / "credit_portal_integration" / "generated_credentials"
        self.creds_dir.mkdir(exist_ok=True)
        
        self.init_ui()
        self.refresh_credentials()
        
        # Auto-refresh every 10 seconds
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_credentials)
        self.refresh_timer.start(10000)
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("🤖 Customer Portal - Credential Manager")
        header.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        header.setStyleSheet("color: #2c3e50; padding: 10px 0;")
        layout.addWidget(header)
        
        # Info Label
        info_label = QLabel(
            "View and manage auto-generated portal credentials for customers/dealers"
        )
        info_label.setStyleSheet("color: #7f8c8d; padding-bottom: 15px;")
        layout.addWidget(info_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("🔄 Refresh Credentials")
        self.refresh_btn.clicked.connect(self.refresh_credentials)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        button_layout.addWidget(self.refresh_btn)
        
        self.open_dir_btn = QPushButton("📂 Open Credentials Folder")
        self.open_dir_btn.clicked.connect(self.open_credentials_folder)
        self.open_dir_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        button_layout.addWidget(self.open_dir_btn)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Credentials Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Generated At", "Customer Name", "Phone (Login)", "Password", "Sale ID"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                gridline-color: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 5px;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background-color: #34495e;
                color: white;
                padding: 10px;
                border: none;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.table)
        
        # Footer
        footer = QLabel(
            "💡 Credentials are auto-generated when a new credit sale is created"
        )
        footer.setStyleSheet("color: #95a5a6; padding-top: 10px; font-style: italic;")
        layout.addWidget(footer)
    
    def refresh_credentials(self):
        """Refresh the credentials table"""
        self.table.setRowCount(0)
        
        try:
            if not self.creds_dir.exists():
                return
            
            cred_files = sorted(self.creds_dir.glob("credentials_*.txt"), reverse=True)
            
            for file_path in cred_files[:50]:  # Show last 50
                try:
                    self.add_credential_to_table(file_path)
                except Exception as e:
                    continue
        
        except Exception as e:
            pass
    
    def add_credential_to_table(self, file_path):
        """Parse a credential file and add to table"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            data = {}
            for line in lines:
                line = line.strip()
                if line.startswith("Generated:"):
                    data['generated'] = line.split(":", 1)[1].strip()
                elif line.startswith("Sale ID:"):
                    data['sale_id'] = line.split(":", 1)[1].strip()
                elif line.startswith("Customer Name:"):
                    data['name'] = line.split(":", 1)[1].strip()
                elif line.startswith("Phone Number:"):
                    data['phone'] = line.split(":", 1)[1].strip()
                elif line.startswith("Password:"):
                    data['password'] = line.split(":", 1)[1].strip()
            
            if all(k in data for k in ['generated', 'name', 'phone', 'password']):
                row = self.table.rowCount()
                self.table.insertRow(row)
                
                self.table.setItem(row, 0, QTableWidgetItem(data['generated']))
                self.table.setItem(row, 1, QTableWidgetItem(data['name']))
                self.table.setItem(row, 2, QTableWidgetItem(data['phone']))
                self.table.setItem(row, 3, QTableWidgetItem(data['password']))
                self.table.setItem(row, 4, QTableWidgetItem(data.get('sale_id', '-')))
        
        except Exception:
            pass
    
    def open_credentials_folder(self):
        """Open the credentials folder in File Explorer"""
        try:
            os.startfile(str(self.creds_dir))
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error",
                f"Could not open folder: {e}"
            )
