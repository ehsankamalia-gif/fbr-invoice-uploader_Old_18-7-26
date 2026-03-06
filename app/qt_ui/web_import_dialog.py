from __future__ import annotations

import threading
from typing import List, Dict, Optional
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QTextEdit, QCheckBox, QFrame, QGridLayout, 
    QMessageBox, QProgressBar
)
from app.services.scraper_service import HondaScraper
from app.utils.url_manager import UrlManager
from app.db.session import SessionLocal
from app.db.models import Motorcycle, ProductModel
from sqlalchemy import or_
from app.core.logger import logger
import app.core.config

class WebImportDialog(QDialog):
    scrape_complete = pyqtSignal(list)
    scrape_error = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Inventory from Web")
        self.setMinimumSize(800, 650)
        
        self.scraper = HondaScraper()
        self.scraped_data = []
        self.url_manager = UrlManager()
        
        self._init_ui()
        self._load_saved_data()
        
        # Connect signals
        self.scrape_complete.connect(self._on_scrape_complete)
        self.scrape_error.connect(self._on_scrape_error)
        self.status_update.connect(self._on_status_update)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # 1. URL and Browser Section
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("Portal URL:"))
        
        self.url_entry = QLineEdit()
        self.url_entry.setPlaceholderText("https://dealers.ahlportal.com")
        header_layout.addWidget(self.url_entry, 1)
        
        self.save_url_btn = QPushButton("💾")
        self.save_url_btn.setToolTip("Save URL")
        self.save_url_btn.setFixedWidth(40)
        self.save_url_btn.clicked.connect(self._save_url)
        header_layout.addWidget(self.save_url_btn)
        
        self.launch_btn = QPushButton("1. Launch Browser")
        self.launch_btn.setObjectName("primaryButton")
        self.launch_btn.clicked.connect(self._launch_browser)
        header_layout.addWidget(self.launch_btn)
        
        layout.addLayout(header_layout)

        # 2. Credentials Section
        cred_group = QFrame()
        cred_group.setStyleSheet("QFrame { background-color: #f1f3f5; border-radius: 8px; }")
        cred_layout = QHBoxLayout(cred_group)
        
        cred_layout.addWidget(QLabel("Username:"))
        self.username_entry = QLineEdit()
        cred_layout.addWidget(self.username_entry)
        
        cred_layout.addWidget(QLabel("Password:"))
        self.password_entry = QLineEdit()
        self.password_entry.setEchoMode(QLineEdit.EchoMode.Password)
        cred_layout.addWidget(self.password_entry)
        
        self.show_pass_check = QCheckBox("Show")
        self.show_pass_check.toggled.connect(self._toggle_password)
        cred_layout.addWidget(self.show_pass_check)
        
        self.save_creds_btn = QPushButton("💾 Save")
        self.save_creds_btn.clicked.connect(self._save_credentials)
        cred_layout.addWidget(self.save_creds_btn)
        
        layout.addWidget(cred_group)

        # 3. Instructions and Defaults
        info_label = QLabel(
            "Step 1: Click 'Launch Browser' and log in to the Atlas Honda Portal.\n"
            "Step 2: Navigate to the Stock/Inventory page.\n"
            "Step 3: Click 'Scrape Page' below to extract data."
        )
        info_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        layout.addWidget(info_label)

        defaults_group = QFrame()
        defaults_layout = QHBoxLayout(defaults_group)
        defaults_layout.setContentsMargins(0, 0, 0, 0)
        
        defaults_layout.addWidget(QLabel("Default Year:"))
        self.year_entry = QLineEdit("2025")
        self.year_entry.setFixedWidth(60)
        defaults_layout.addWidget(self.year_entry)
        
        defaults_layout.addWidget(QLabel("Cost Price:"))
        self.cost_entry = QLineEdit("0")
        self.cost_entry.setFixedWidth(100)
        defaults_layout.addWidget(self.cost_entry)
        
        defaults_layout.addWidget(QLabel("Sale Price:"))
        self.sale_entry = QLineEdit("0")
        self.sale_entry.setFixedWidth(100)
        defaults_layout.addWidget(self.sale_entry)
        
        defaults_layout.addStretch(1)
        layout.addWidget(defaults_group)

        # 4. Scrape Action
        scrape_bar = QHBoxLayout()
        self.pagination_check = QCheckBox("Scrape All Pages (Max 1000)")
        self.pagination_check.setChecked(True)
        scrape_bar.addWidget(self.pagination_check)
        
        self.scrape_btn = QPushButton("2. Scrape Page")
        self.scrape_btn.setObjectName("primaryButton")
        self.scrape_btn.setEnabled(False)
        self.scrape_btn.clicked.connect(self._start_scrape)
        scrape_bar.addWidget(self.scrape_btn, 1)
        
        layout.addLayout(scrape_bar)

        # 5. Results Preview
        self.preview_box = QTextEdit()
        self.preview_box.setReadOnly(True)
        self.preview_box.setPlaceholderText("Scraped data will appear here...")
        layout.addWidget(self.preview_box, 1)

        # 6. Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 7. Import Action
        self.import_btn = QPushButton("3. Import to Database")
        self.import_btn.setEnabled(False)
        self.import_btn.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 12px;")
        self.import_btn.clicked.connect(self._import_data)
        layout.addWidget(self.import_btn)

        # Global Styles
        self.setStyleSheet("""
            QPushButton#primaryButton { background-color: #3498db; color: white; font-weight: bold; padding: 8px 16px; border-radius: 4px; }
            QPushButton#primaryButton:hover { background-color: #2980b9; }
            QPushButton#primaryButton:disabled { background-color: #bdc3c7; }
            QLineEdit { padding: 8px; border: 1px solid #ced4da; border-radius: 4px; background-color: white; }
        """)

    def _load_saved_data(self):
        saved_url = self.url_manager.get_default_url()
        if saved_url == "https://portal.atlashonda.com.pk":
            saved_url = "https://dealers.ahlportal.com"
        self.url_entry.setText(saved_url or "https://dealers.ahlportal.com")
        
        app.core.config.reload_settings()
        settings = app.core.config.settings
        if settings.HONDA_PORTAL_USERNAME:
            self.username_entry.setText(settings.HONDA_PORTAL_USERNAME)
        if settings.HONDA_PORTAL_PASSWORD:
            self.password_entry.setText(settings.HONDA_PORTAL_PASSWORD)
            
        if self.scraper.capture_service.is_running:
            self.launch_btn.setText("1. Connect & Login")
            self.launch_btn.setStyleSheet("background-color: #2980B9; color: white;")
            self.scrape_btn.setEnabled(True)

    def _toggle_password(self, checked):
        self.password_entry.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)

    def _save_url(self):
        url = self.url_entry.text().strip()
        if url:
            self.url_manager.save_url(url, "Atlas Honda Portal")
            QMessageBox.information(self, "Success", "Portal URL saved successfully.")

    def _save_credentials(self):
        username = self.username_entry.text().strip()
        password = self.password_entry.text().strip()
        try:
            from app.services.settings_service import settings_service
            settings_service.save_honda_credentials(username, password)
            QMessageBox.information(self, "Success", "Credentials saved successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save credentials: {e}")

    def _launch_browser(self):
        url = self.url_entry.text().strip()
        username = self.username_entry.text().strip()
        password = self.password_entry.text().strip()
        
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a URL first")
            return
            
        self.launch_btn.setEnabled(False)
        self.launch_btn.setText("Launching...")
        
        def login_worker():
            try:
                self.scraper.login(url, username=username, password=password)
                self.status_update.emit("Browser ready")
            except Exception as e:
                self.scrape_error.emit(str(e))

        threading.Thread(target=login_worker, daemon=True).start()

    def _on_status_update(self, status):
        if status == "Browser ready":
            self.launch_btn.setEnabled(True)
            self.launch_btn.setText("1. Connect & Login")
            self.launch_btn.setStyleSheet("background-color: #2980B9; color: white;")
            self.scrape_btn.setEnabled(True)
        else:
            self.scrape_btn.setText(status)

    def _start_scrape(self):
        self.scrape_btn.setEnabled(False)
        self.scrape_btn.setText("Scraping...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0) # Indeterminate
        
        def scrape_worker():
            try:
                if self.pagination_check.isChecked():
                    new_data = self.scraper.scrape_all_pages(
                        max_pages=1000, 
                        status_callback=lambda msg: self.status_update.emit(msg)
                    )
                else:
                    new_data = self.scraper.scrape_current_page()
                self.scrape_complete.emit(new_data)
            except Exception as e:
                self.scrape_error.emit(str(e))

        threading.Thread(target=scrape_worker, daemon=True).start()

    def _on_scrape_complete(self, new_data):
        self.scrape_btn.setEnabled(True)
        self.scrape_btn.setText("2. Scrape Page (Append)")
        self.progress_bar.setVisible(False)
        
        # Append and avoid duplicates
        existing_sigs = set((item['chassis_number'], item['engine_number']) for item in self.scraped_data)
        added = 0
        for item in new_data:
            sig = (item['chassis_number'], item['engine_number'])
            if sig not in existing_sigs:
                self.scraped_data.append(item)
                existing_sigs.add(sig)
                added += 1
        
        if not self.scraped_data:
            self.preview_box.setText("No data found. Ensure the table is visible in the browser.")
            return

        text = f"Total Items: {len(self.scraped_data)} (Added: {added})\n\n"
        for i, item in enumerate(self.scraped_data):
            text += f"{i+1}. {item['model_code']} - {item['color_code']} (Eng: {item['engine_number']}, Chas: {item['chassis_number']})\n"
        
        self.preview_box.setText(text)
        self.import_btn.setEnabled(True)
        self.import_btn.setText(f"3. Import {len(self.scraped_data)} Items to Database")

    def _on_scrape_error(self, error):
        self.scrape_btn.setEnabled(True)
        self.scrape_btn.setText("2. Scrape Page")
        self.progress_bar.setVisible(False)
        self.launch_btn.setEnabled(True)
        self.launch_btn.setText("1. Launch Browser")
        QMessageBox.critical(self, "Scraping Error", f"Failed to scrape: {error}")

    def _import_data(self):
        if not self.scraped_data:
            return
            
        try:
            year = int(self.year_entry.text() or 2025)
            cost = float(self.cost_entry.text() or 0)
            sale = float(self.sale_entry.text() or 0)
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter valid numeric values for Year and Price.")
            return
            
        db = SessionLocal()
        imported = 0
        skipped = 0
        
        try:
            for item in self.scraped_data:
                exists = db.query(Motorcycle).filter(
                    or_(
                        Motorcycle.chassis_number == item["chassis_number"],
                        Motorcycle.engine_number == item["engine_number"]
                    )
                ).first()
                
                if exists:
                    skipped += 1
                    continue
                    
                model_name = item["model_code"]
                product_model = db.query(ProductModel).filter(ProductModel.model_name == model_name).first()
                if not product_model:
                    product_model = ProductModel(
                        model_name=model_name,
                        make="Honda",
                        engine_capacity="70cc" if "70" in model_name else "125cc"
                    )
                    db.add(product_model)
                    db.flush()
                
                new_bike = Motorcycle(
                    product_model_id=product_model.id,
                    year=year,
                    chassis_number=item["chassis_number"].upper(),
                    engine_number=item["engine_number"].upper(),
                    color=item["color_code"].upper(),
                    cost_price=cost,
                    sale_price=sale,
                    status="IN_STOCK"
                )
                db.add(new_bike)
                imported += 1
            
            db.commit()
            QMessageBox.information(self, "Import Complete", f"Successfully imported {imported} motorcycles.\nSkipped {skipped} duplicates.")
            if self.parent():
                if hasattr(self.parent(), "_reload_inventory"):
                    self.parent()._reload_inventory()
            self.accept()
            
        except Exception as e:
            db.rollback()
            QMessageBox.critical(self, "Import Error", f"Database error: {e}")
        finally:
            db.close()
