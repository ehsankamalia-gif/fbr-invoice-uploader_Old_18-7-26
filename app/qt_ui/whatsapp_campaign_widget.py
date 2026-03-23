from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QLineEdit, QTextEdit, QFrame, 
                             QFileDialog, QTableWidget, QTableWidgetItem, 
                             QHeaderView, QProgressBar, QTabWidget, QMessageBox, QMenu)
from PyQt6.QtCore import Qt, pyqtSlot, QSize, QPoint
from app.services.whatsapp_service import whatsapp_service
from app.db.session import SessionLocal
from app.db.models import SMSCampaign, SMSQueue
import logging
import os

logger = logging.getLogger(__name__)

class WhatsAppCampaignWidget(QWidget):
    """
    Complete WhatsApp Module for bulk messaging and campaign management.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file_path = None
        self.setup_ui()
        self.load_campaign_history()

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        # Header
        header = QLabel("WhatsApp Marketing Module")
        header.setStyleSheet("font-size: 24px; font-weight: bold; color: #2c3e50;")
        self.main_layout.addWidget(header)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self.create_new_campaign_tab(), "🚀 New Campaign")
        self.tabs.addTab(self.create_history_tab(), "📋 Campaign History")
        self.main_layout.addWidget(self.tabs)

    def create_new_campaign_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        
        # Left Side: Configuration
        config_panel = QFrame()
        config_panel.setFixedWidth(350)
        config_panel.setStyleSheet("background-color: #f8f9fa; border-radius: 8px; border: 1px solid #dee2e6;")
        config_layout = QVBoxLayout(config_panel)
        
        config_layout.addWidget(QLabel("<b>Campaign Name</b>"))
        self.campaign_name_input = QLineEdit()
        self.campaign_name_input.setPlaceholderText("e.g. Eid Mubarak Promotion")
        config_layout.addWidget(self.campaign_name_input)

        config_layout.addSpacing(10)
        config_layout.addWidget(QLabel("<b>Excel Data Source</b>"))
        file_btn = QPushButton("📁 Browse Excel File")
        file_btn.clicked.connect(self.browse_file)
        config_layout.addWidget(file_btn)
        self.file_label = QLabel("No file selected")
        self.file_label.setStyleSheet("color: #6c757d; font-size: 11px;")
        config_layout.addWidget(self.file_label)

        config_layout.addSpacing(10)
        config_layout.addWidget(QLabel("<b>Message Template</b>"))
        self.template_input = QTextEdit()
        self.template_input.setPlaceholderText("Dear {name}, thank you for choosing us!")
        config_layout.addWidget(self.template_input)
        
        tip_lbl = QLabel("Tip: Use placeholders like {name}, {phone} matching Excel headers.")
        tip_lbl.setStyleSheet("color: #7f8c8d; font-size: 10px; font-style: italic;")
        config_layout.addWidget(tip_lbl)

        config_layout.addStretch()
        
        self.start_btn = QPushButton("🚀 Create & Start Campaign")
        self.start_btn.setStyleSheet("""
            QPushButton { background-color: #3498db; color: white; font-weight: bold; padding: 12px; border: none; border-radius: 4px; }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.start_btn.clicked.connect(self.start_campaign)
        config_layout.addWidget(self.start_btn)
        
        layout.addWidget(config_panel)

        # Right Side: Preview & Progress
        preview_panel = QFrame()
        preview_layout = QVBoxLayout(preview_panel)
        
        preview_layout.addWidget(QLabel("<b>Recipient Preview</b>"))
        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(3)
        self.preview_table.setHorizontalHeaderLabels(["Name", "Phone", "Status"])
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        preview_layout.addWidget(self.preview_table)

        # Progress Area
        self.progress_group = QFrame()
        self.progress_group.setVisible(False)
        self.progress_group.setStyleSheet("background-color: #e3f2fd; border-radius: 8px; padding: 15px;")
        progress_layout = QVBoxLayout(self.progress_group)
        
        self.progress_title = QLabel("Campaign Running...")
        self.progress_title.setStyleSheet("font-weight: bold; color: #1976d2;")
        progress_layout.addWidget(self.progress_title)
        
        self.progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_bar)
        
        self.stats_label = QLabel("Sent: 0 | Failed: 0 | Total: 0")
        progress_layout.addWidget(self.stats_label)
        
        preview_layout.addWidget(self.progress_group)
        
        layout.addWidget(preview_panel)
        return tab

    def create_history_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(7)
        self.history_table.setHorizontalHeaderLabels(["ID", "Date", "Campaign Name", "Total", "Sent", "Failed", "Status"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.history_table.customContextMenuRequested.connect(self.show_history_context_menu)
        layout.addWidget(self.history_table)
        
        refresh_btn = QPushButton("🔄 Refresh History")
        refresh_btn.clicked.connect(self.load_campaign_history)
        layout.addWidget(refresh_btn)
        
        return tab

    def show_history_context_menu(self, pos: QPoint):
        item = self.history_table.itemAt(pos)
        if not item: return
        
        row = item.row()
        campaign_id = int(self.history_table.item(row, 0).text())
        status = self.history_table.item(row, 6).text()
        
        menu = QMenu()
        
        view_action = menu.addAction("👁️ View Details")
        
        # Start/Resume Action
        if status in ["PENDING", "PAUSED", "CANCELLED", "FAILED"]:
            start_action = menu.addAction("🚀 Start/Resume Campaign")
        else:
            start_action = None

        # Pause Action
        if status == "RUNNING":
            pause_action = menu.addAction("⏸️ Pause Campaign")
        else:
            pause_action = None
        
        retry_action = menu.addAction("🔄 Retry Failed Messages")
        retry_action.setEnabled(status in ["COMPLETED", "CANCELLED", "FAILED"])
        
        delete_action = menu.addAction("🗑️ Delete Campaign (Soft Delete)")
        
        action = menu.exec(self.history_table.viewport().mapToGlobal(pos))
        
        if action == view_action:
            self.on_view_details(campaign_id)
        elif start_action and action == start_action:
            self.on_start_campaign(campaign_id)
        elif pause_action and action == pause_action:
            self.on_pause_campaign(campaign_id)
        elif action == retry_action:
            self.on_retry_campaign(campaign_id)
        elif action == delete_action:
            self.on_delete_campaign(campaign_id)

    def on_start_campaign(self, campaign_id: int):
        success, message = whatsapp_service.start_campaign(campaign_id)
        if success:
            QMessageBox.information(self, "Success", message)
            self.load_campaign_history()
            # If we're on the new campaign tab, update that too
            if not whatsapp_service.worker:
                whatsapp_service.start_monitoring()
            try: whatsapp_service.worker.campaign_progress.disconnect(self.update_progress)
            except: pass
            whatsapp_service.worker.campaign_progress.connect(self.update_progress)
        else:
            QMessageBox.critical(self, "Error", f"Failed to start campaign: {message}")

    def on_pause_campaign(self, campaign_id: int):
        success, message = whatsapp_service.pause_campaign(campaign_id)
        if success:
            QMessageBox.information(self, "Success", message)
            self.load_campaign_history()
        else:
            QMessageBox.critical(self, "Error", f"Failed to pause campaign: {message}")

    def on_view_details(self, campaign_id: int):
        from app.qt_ui.campaign_details_dialog import CampaignDetailsDialog
        db = SessionLocal()
        try:
            campaign = db.query(SMSCampaign).filter(SMSCampaign.id == campaign_id).first()
            if not campaign: return
            
            messages = db.query(SMSQueue).filter(SMSQueue.campaign_id == campaign_id).all()
            
            details = {
                'campaign': campaign,
                'messages': messages
            }
            
            dialog = CampaignDetailsDialog(details, self)
            dialog.retry_requested.connect(self.on_retry_campaign)
            dialog.exec()
        finally:
            db.close()

    def on_retry_campaign(self, campaign_id):
        confirm = QMessageBox.question(self, "Confirm Retry", "Are you sure you want to retry all failed messages for this campaign?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.Yes:
            if whatsapp_service.retry_failed_messages(campaign_id):
                QMessageBox.information(self, "Success", "Retry process started.")
                self.load_campaign_history()
            else:
                QMessageBox.critical(self, "Error", "Failed to start retry process.")

    def on_delete_campaign(self, campaign_id):
        confirm = QMessageBox.question(self, "Confirm Delete", "Are you sure you want to delete this campaign? This action will cancel any pending messages and hide the campaign from history.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if confirm == QMessageBox.StandardButton.Yes:
            if whatsapp_service.soft_delete_campaign(campaign_id):
                QMessageBox.information(self, "Success", "Campaign deleted successfully.")
                self.load_campaign_history()
            else:
                QMessageBox.critical(self, "Error", "Failed to delete campaign.")

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Excel File", "", "Excel Files (*.xlsx *.xls)")
        if file_path:
            self.current_file_path = file_path
            self.file_label.setText(os.path.basename(file_path))
            self.load_preview(file_path)

    def load_preview(self, file_path):
        try:
            from app.services import excel_service
            data, columns = excel_service.parse_recipients(file_path)
            
            self.preview_table.setRowCount(len(data))
            for i, row in enumerate(data[:100]): # Preview first 100
                name = str(row.get("name", "N/A"))
                phone_col = next((c for c in columns if any(k in c.lower() for k in ["phone", "mobile", "number", "contact"])), columns[0])
                phone = str(row.get(phone_col, "N/A")).split(".")[0]
                
                self.preview_table.setItem(i, 0, QTableWidgetItem(name))
                self.preview_table.setItem(i, 1, QTableWidgetItem(phone))
                self.preview_table.setItem(i, 2, QTableWidgetItem("Ready"))
                
            if len(data) > 100:
                QMessageBox.information(self, "Preview", f"Loaded {len(data)} recipients. Showing first 100 in preview.")
        except Exception as e:
            QMessageBox.critical(self, "Excel Error", f"Failed to load Excel: {e}")

    def start_campaign(self):
        name = self.campaign_name_input.text().strip()
        template = self.template_input.toPlainText().strip()
        
        if not name or not template or not self.current_file_path:
            QMessageBox.warning(self, "Missing Info", "Please provide campaign name, template, and Excel file.")
            return

        try:
            campaign_id = whatsapp_service.create_campaign_from_excel(name, template, self.current_file_path)
            
            # Start monitoring progress
            if not whatsapp_service.worker:
                whatsapp_service.start_monitoring()
            
            # Ensure we're only connected once
            try: whatsapp_service.worker.campaign_progress.disconnect(self.update_progress)
            except: pass
            
            whatsapp_service.worker.campaign_progress.connect(self.update_progress)
            success, message = whatsapp_service.start_campaign(campaign_id)
            
            if success:
                self.progress_group.setVisible(True)
                self.start_btn.setEnabled(False)
                self.start_btn.setText("Campaign in Progress...")
            else:
                QMessageBox.critical(self, "Error", f"Failed to start campaign: {message}")
            
        except Exception as e:
            QMessageBox.critical(self, "Campaign Error", f"Failed to start campaign: {e}")

    @pyqtSlot(int, int, int)
    def update_progress(self, sent, failed, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(sent + failed)
        self.stats_label.setText(f"Sent: {sent} | Failed: {failed} | Total: {total}")
        
        if (sent + failed) >= total:
            self.progress_title.setText("Campaign Completed! ✅")
            self.start_btn.setEnabled(True)
            self.start_btn.setText("🚀 Create & Start Campaign")
            self.load_campaign_history()

    def load_campaign_history(self):
        db = SessionLocal()
        try:
            campaigns = db.query(SMSCampaign).filter(
                SMSCampaign.channel == "WHATSAPP",
                SMSCampaign.is_deleted == False
            ).order_by(SMSCampaign.created_at.desc()).all()
            
            self.history_table.setRowCount(len(campaigns))
            for i, c in enumerate(campaigns):
                self.history_table.setItem(i, 0, QTableWidgetItem(str(c.id)))
                self.history_table.setItem(i, 1, QTableWidgetItem(c.created_at.strftime("%Y-%m-%d %H:%M")))
                self.history_table.setItem(i, 2, QTableWidgetItem(c.name))
                self.history_table.setItem(i, 3, QTableWidgetItem(str(c.total_recipients)))
                self.history_table.setItem(i, 4, QTableWidgetItem(str(c.sent_count)))
                self.history_table.setItem(i, 5, QTableWidgetItem(str(c.failed_count)))
                self.history_table.setItem(i, 6, QTableWidgetItem(c.status))
        except Exception as e:
            logger.error(f"Failed to load campaign history: {e}")
        finally:
            db.close()
