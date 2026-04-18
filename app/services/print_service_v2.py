from __future__ import annotations

import os
import base64
import datetime as dt
from typing import Dict, Any, List, Optional
from jinja2 import Environment, FileSystemLoader
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QHBoxLayout, QMessageBox, QApplication, QWidget
from PyQt6.QtCore import Qt, QUrl

from app.core.logger import logger
from app.services.settings_service import settings_service

class PrintServiceV2:
    """
    Independent print service for generating high-quality HTML-based prints
    using predefined templates (Invoice & Authority Letter).
    """
    
    def __init__(self):
        # Setup Jinja2 environment for HTML templates
        self.template_dir = os.path.join(os.getcwd(), "app", "static", "templates")
        if not os.path.exists(self.template_dir):
            os.makedirs(self.template_dir, exist_ok=True)
            
        self.jinja_env = Environment(loader=FileSystemLoader(self.template_dir))
        self.active_view: Optional[object] = None

    def _get_business_info(self) -> Dict[str, str]:
        """Fetches current business configuration for template population."""
        settings = settings_service.get_active_settings()
        return {
            "business_name": settings.get("business_name", "Ehsan Trader"),
            "business_address": settings.get("business_address", "Kamalia, Pakistan"),
            "business_phone": settings.get("business_phone", "0300-1234567"),
            "business_ntn": settings.get("business_ntn", "1234567-8")
        }

    def render_invoice(self, invoice_data: Dict[str, Any]) -> str:
        """Renders the HTML for an invoice using the template."""
        try:
            template = self.jinja_env.get_template("invoice.html")
            data = self._get_business_info()
            data.update(invoice_data)
            
            # Ensure date is formatted
            if isinstance(data.get("date"), dt.datetime):
                data["date"] = data["date"].strftime("%Y-%m-%d")
            
            return template.render(data)
        except Exception as e:
            logger.error(f"Failed to render invoice template: {e}", exc_info=True)
            raise

    def render_authority_letter(self, letter_data: Dict[str, Any]) -> str:
        """Renders the HTML for an authority letter using the template."""
        try:
            template = self.jinja_env.get_template("authority_letter.html")
            data = self._get_business_info()
            data.update(letter_data)
            
            # Add metadata
            data["year"] = dt.datetime.now().year
            if isinstance(data.get("date"), dt.datetime):
                data["date"] = data["date"].strftime("%Y-%m-%d")
            
            return template.render(data)
        except Exception as e:
            logger.error(f"Failed to render authority letter template: {e}", exc_info=True)
            raise

    def render_advance_booking_receipt(self, booking_data: Dict[str, Any]) -> str:
        data = self._get_business_info()
        data.update(booking_data or {})

        created_at = data.get("created_at")
        if isinstance(created_at, dt.datetime):
            created_at_str = created_at.strftime("%Y-%m-%d %H:%M")
        else:
            created_at_str = str(created_at or dt.datetime.now().strftime("%Y-%m-%d %H:%M"))

        def esc(v: object) -> str:
            s = str(v if v is not None else "")
            return (
                s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#39;")
            )

        booking_number = esc(data.get("booking_number", ""))
        customer_name = esc(data.get("customer_name", ""))
        motorcycle_model = esc(data.get("motorcycle_model", ""))
        color = esc(data.get("color", ""))
        total_price = esc(f"{float(data.get('total_price', 0.0)):,.0f}")
        advance_paid = esc(f"{float(data.get('advance_paid', 0.0)):,.0f}")
        balance_amount = esc(f"{float(data.get('balance_amount', 0.0)):,.0f}")

        business_name = esc(data.get("business_name", ""))
        business_address = esc(data.get("business_address", ""))
        business_phone = esc(data.get("business_phone", ""))

        def render_copy(label: str) -> str:
            return f"""
              <div class="copy-box">
                <div class="copy-title">{esc(label)}</div>
                <div class="biz-line">{business_name}</div>
                <div class="biz-line">{business_phone}</div>
                <div class="row"><span class="k">Booking #</span><span class="v mono">{booking_number}</span></div>
                <div class="row"><span class="k">Date</span><span class="v">{esc(created_at_str)}</span></div>
                <div class="row"><span class="k">Customer</span><span class="v">{customer_name}</span></div>
                <div class="row"><span class="k">Model / Color</span><span class="v">{motorcycle_model} / {color}</span></div>
                <div class="row"><span class="k">Total</span><span class="v text-end">Rs. {total_price}</span></div>
                <div class="row"><span class="k">Advance</span><span class="v text-end">Rs. {advance_paid}</span></div>
                <div class="row total"><span class="k">Balance</span><span class="v text-end">Rs. {balance_amount}</span></div>
              </div>
            """

        html = f"""
        <!doctype html>
        <html>
          <head>
            <meta charset="utf-8"/>
            <meta name="viewport" content="width=device-width, initial-scale=1"/>
            <title>Advance Booking Receipt</title>
            <style>
              @page {{
                size: Letter portrait;
                margin: 0.5in;
              }}
              * {{ box-sizing: border-box; }}
              body {{
                margin: 0;
                padding: 0;
                font-family: Arial, sans-serif;
                color: #111;
                font-size: 10px;
              }}
              .sheet {{
                width: 7.5in;
                min-height: 10in;
                margin: 0 auto;
                display: flex;
                flex-direction: column;
              }}
              .top-copies {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 0;
                width: 7.5in;
              }}
              .copy-box {{
                border: 1px solid #111;
                height: 3in;
                padding: 0.1in;
                overflow: hidden;
              }}
              .copy-title {{
                text-align: center;
                font-weight: 700;
                font-size: 10px;
                margin-bottom: 0.04in;
                text-transform: uppercase;
              }}
              .biz-line {{
                text-align: center;
                font-size: 9px;
                font-weight: 700;
                line-height: 1.1;
              }}
              .row {{
                display: flex;
                justify-content: space-between;
                align-items: baseline;
                gap: 6px;
                padding: 1px 0;
              }}
              .k {{ color: #222; }}
              .v {{ font-weight: 600; text-align: right; }}
              .mono {{ font-family: Consolas, "Courier New", monospace; }}
              .text-end {{ text-align: right; }}
              .total .k, .total .v {{ font-weight: 800; }}
              .bottom-box {{
                margin-top: auto;
                width: 7.5in;
                border: 1px solid #111;
                min-height: 1.4in;
                padding: 0.12in;
              }}
              .bottom-title {{
                font-size: 10px;
                font-weight: 700;
                margin-bottom: 0.06in;
              }}
              .note-row {{
                display: flex;
                justify-content: space-between;
                gap: 0.2in;
                margin-top: 0.22in;
              }}
              .line-block {{
                flex: 1;
              }}
              .line {{
                border-top: 1px solid #111;
                margin-bottom: 2px;
              }}
              .line-label {{
                font-size: 9px;
                color: #333;
                text-align: center;
              }}
            </style>
          </head>
          <body>
            <div class="sheet">
              <div class="top-copies">
                {render_copy("Customer Copy")}
                {render_copy("Showroom Copy")}
                </div>

              <div class="bottom-box">
                <div class="bottom-title">Terms / Delivery Notes</div>
                <div>{business_address}</div>
                <div>For queries: {business_phone}</div>
                <div class="note-row">
                  <div class="line-block">
                    <div class="line"></div>
                    <div class="line-label">Customer Signature</div>
                  </div>
                  <div class="line-block">
                    <div class="line"></div>
                    <div class="line-label">Authorized Signature / Stamp</div>
                  </div>
                </div>
              </div>
            </div>
          </body>
        </html>
        """
        return html

    def print_html(self, html_content: str, title: str = "Print Document"):
        """Displays a print preview dialog and handles the printing process."""
        try:
            dialog = PrintPreviewDialog(html_content, title)
            dialog.exec()
        except Exception as e:
            logger.error(f"Printing failed: {e}", exc_info=True)
            QMessageBox.critical(None, "Print Error", f"An error occurred while trying to print: {str(e)}")

class PrintPreviewDialog(QDialog):
    """Standalone dialog for document preview and printing."""
    
    def __init__(self, html_content: str, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1000, 800)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: #f8f9fa; border-bottom: 1px solid #dee2e6;")
        toolbar_layout = QHBoxLayout(toolbar)
        
        self.print_btn = QPushButton("🖨️ Print Now")
        self.print_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.print_btn.clicked.connect(self._handle_print)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        
        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.print_btn)
        toolbar_layout.addWidget(self.close_btn)
        toolbar_layout.addSpacing(20)
        
        layout.addWidget(toolbar)

        self._html_content = html_content
        self.web_view = None
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView

            self.web_view = QWebEngineView()
            self.web_view.setHtml(html_content)
            layout.addWidget(self.web_view)
        except Exception as e:
            msg = QWidget()
            msg_layout = QVBoxLayout(msg)
            msg_layout.setContentsMargins(20, 20, 20, 20)
            msg_layout.setSpacing(12)

            lbl = QPushButton(f"Web preview is unavailable on this system.\nOpen in browser to print.\n\nError: {e}")
            lbl.setEnabled(False)
            msg_layout.addWidget(lbl)

            open_btn = QPushButton("Open in Browser")
            open_btn.clicked.connect(self._open_in_browser)
            msg_layout.addWidget(open_btn)

            layout.addWidget(msg)

    def _handle_print(self):
        """Initiates the native print dialog."""
        if not self.web_view:
            self._open_in_browser()
            return
        self.web_view.page().printToPdf(lambda data: self._on_pdf_ready(data))
        from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        print_dialog = QPrintDialog(printer, self)
        if print_dialog.exec() == QPrintDialog.DialogCode.Accepted:
            self.web_view.page().print(printer, lambda success: logger.info(f"Print success: {success}"))

    def _on_pdf_ready(self, data):
        # This can be used to auto-save a copy if needed
        pass

    def _open_in_browser(self):
        try:
            from PyQt6.QtGui import QDesktopServices
            from tempfile import NamedTemporaryFile

            with NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as f:
                f.write(self._html_content or "")
                path = f.name
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception as e:
            logger.error(f"Open-in-browser print fallback failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Print Error", f"Unable to open browser for printing: {e}")

# Singleton instance for easy access across the app
print_service_v2 = PrintServiceV2()
