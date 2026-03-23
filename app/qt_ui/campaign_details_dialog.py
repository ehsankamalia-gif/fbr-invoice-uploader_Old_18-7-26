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
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Phone Number", "Message", "Status", "Retries", "Error"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self.show_retry_history)
        layout.addWidget(self.table)
        
        help_label = QLabel("<i>Tip: Double-click a row to see detailed retry history.</i>")
        help_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        layout.addWidget(help_label)

        self.messages = details['messages']
        self.populate_table(self.messages)

        # Actions
        self.retry_button = QPushButton("Retry Failed Messages")
        self.retry_button.setEnabled(details['campaign'].failed_count > 0)
        self.retry_button.clicked.connect(self.on_retry_clicked)
        layout.addWidget(self.retry_button)

    def show_retry_history(self, item):
        row = item.row()
        msg = self.messages[row]
        history = msg.retry_history or []
        
        if not history:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Retry History", "No retry attempts recorded for this message.")
            return
            
        history_text = "<b>Retry History for " + msg.phone_number + ":</b><br><br>"
        for attempt in history:
            ts = attempt.get('timestamp', 'N/A')
            err = attempt.get('error', 'No error recorded')
            att = attempt.get('attempt', '?')
            temp = " (Temporary)" if attempt.get('is_temporary') else ""
            history_text += f"• Attempt {att}{temp}: {ts}<br>   Error: {err}<br><br>"
            
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Retry History", history_text)

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
            self.table.setItem(i, 3, QTableWidgetItem(str(msg.retry_count)))
            self.table.setItem(i, 4, QTableWidgetItem(msg.error_message or ""))
