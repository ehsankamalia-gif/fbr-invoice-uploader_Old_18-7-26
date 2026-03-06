from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QPushButton, QHBoxLayout, QHeaderView
from PyQt6.QtCore import Qt, pyqtSignal
from typing import List, Dict, Any

class CampaignDetailsDialog(QDialog):
    retry_requested = pyqtSignal(int)

    def __init__(self, details: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.campaign_id = details['campaign'].id
        self.setWindowTitle(f"Campaign Details: {details['campaign'].name}")
        self.setMinimumSize(800, 600)

        layout = QVBoxLayout(self)

        # Campaign Info
        info_layout = QHBoxLayout()
        info_layout.addWidget(QLabel(f"<b>Status:</b> {details['campaign'].status}"))
        info_layout.addWidget(QLabel(f"<b>Total:</b> {details['campaign'].total_recipients}"))
        info_layout.addWidget(QLabel(f"<b>Sent:</b> {details['campaign'].sent_count}"))
        info_layout.addWidget(QLabel(f"<b>Failed:</b> {details['campaign'].failed_count}"))
        layout.addLayout(info_layout)

        # Messages Table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Phone Number", "Message", "Status", "Error"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.populate_table(details['messages'])

        # Actions
        self.retry_button = QPushButton("Retry Failed Messages")
        self.retry_button.setEnabled(details['campaign'].failed_count > 0)
        self.retry_button.clicked.connect(self.on_retry_clicked)
        layout.addWidget(self.retry_button)

    def on_retry_clicked(self):
        self.retry_requested.emit(self.campaign_id)
        self.accept()

    def populate_table(self, messages: List[Any]):
        self.table.setRowCount(len(messages))
        for i, msg in enumerate(messages):
            self.table.setItem(i, 0, QTableWidgetItem(msg.phone_number))
            self.table.setItem(i, 1, QTableWidgetItem(msg.message))
            
            # Handle status whether it's an enum or a string
            status_val = msg.status
            if hasattr(status_val, 'value'):
                status_val = status_val.value
            
            self.table.setItem(i, 2, QTableWidgetItem(str(status_val)))
            self.table.setItem(i, 3, QTableWidgetItem(msg.error_message or ""))
