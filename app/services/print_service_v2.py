from __future__ import annotations

import os
import json
import threading
import base64
import datetime as dt
from pathlib import Path
from typing import Dict, Any, List, Optional
from jinja2 import Environment, FileSystemLoader
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QHBoxLayout, QMessageBox, QApplication, QWidget, QSizePolicy, QFileDialog
from PyQt6.QtCore import Qt, QUrl, QObject, QCoreApplication, QTimer, pyqtSlot
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from app.core.logger import logger
from app.services.settings_service import settings_service

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
try:
    import PyQt6.QtWebEngineWidgets
except Exception:
    _WEBENGINE_AVAILABLE = False
else:
    _WEBENGINE_AVAILABLE = True

_INVOICE_LAYOUT_LOCK = threading.Lock()
_AUTHORITY_LAYOUT_LOCK = threading.Lock()

def _urdu_font_style_tag() -> str:
    try:
        cfg = settings_service.get_app_config() or {}
    except Exception:
        cfg = {}

    if not cfg.get("urdu_font_enabled"):
        return ""

    family = str(cfg.get("urdu_font_family") or "").strip()
    path = str(cfg.get("urdu_font_path") or "").strip()
    size = int(cfg.get("urdu_font_size") or 14)

    if not family:
        family = "Jameel Noori Nastaleeq"

    font_face = ""
    if path and os.path.exists(path):
        try:
            ext = Path(path).suffix.lower()
            font_bytes = Path(path).read_bytes()
            b64 = base64.b64encode(font_bytes).decode("ascii")
            if ext == ".otf":
                mime = "font/otf"
                fmt = "opentype"
            elif ext == ".woff2":
                mime = "font/woff2"
                fmt = "woff2"
            elif ext == ".woff":
                mime = "font/woff"
                fmt = "woff"
            else:
                mime = "font/ttf"
                fmt = "truetype"
            font_face = (
                "@font-face {"
                f"  font-family: '{family}';"
                f"  src: url('data:{mime};base64,{b64}') format('{fmt}');"
                "  font-weight: normal;"
                "  font-style: normal;"
                "}"
            )
        except Exception as exc:
            logger.warning(f"Failed to embed Urdu font from file: {exc}")

    css = f"""
{font_face}
:root {{
  --urdu-font-family: '{family}';
  --urdu-font-size: {size}px;
}}
body, div, span, p, td, th, li, label, input, textarea, select {{
  font-family: var(--urdu-font-family), Arial, sans-serif !important;
}}
.field {{
  font-family: var(--urdu-font-family), Arial, sans-serif !important;
}}
.mono {{
  font-family: Consolas, 'Courier New', monospace !important;
}}
"""
    return f"<style id=\"urdu-font-style\">{css}</style>"

def _apply_urdu_font_to_html(html: str) -> str:
    raw = str(html or "")
    style_tag = _urdu_font_style_tag()
    if not style_tag:
        return raw
    if "urdu-font-style" in raw:
        return raw
    lower = raw.lower()
    head_close = lower.rfind("</head>")
    if head_close != -1:
        return raw[:head_close] + style_tag + raw[head_close:]
    html_open = lower.find("<html")
    if html_open != -1:
        return raw[:html_open] + style_tag + raw[html_open:]
    return style_tag + raw


def _invoice_layout_file_path() -> Path:
    root = Path(os.getcwd())
    target_dir = root / "exports" / "print_layouts"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / "invoice_layout_positions.json"


def _authority_layout_file_path() -> Path:
    root = Path(os.getcwd())
    target_dir = root / "exports" / "print_layouts"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / "authority_letter_layout_positions.json"


class _InvoiceLayoutFileBridge(QObject):
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

    @pyqtSlot(result=str)
    def load_positions(self) -> str:
        try:
            path = _invoice_layout_file_path()
            if not path.exists():
                return ""
            with _INVOICE_LAYOUT_LOCK:
                raw = path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                return ""
            return json.dumps(parsed)
        except Exception as exc:
            logger.warning(f"Failed to load invoice layout positions from file: {exc}")
            return ""

    @pyqtSlot(str, result=bool)
    def save_positions(self, positions_json: str) -> bool:
        try:
            parsed = json.loads(str(positions_json or ""))
            if not isinstance(parsed, dict):
                return False
            path = _invoice_layout_file_path()
            with _INVOICE_LAYOUT_LOCK:
                path.write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception as exc:
            logger.warning(f"Failed to save invoice layout positions to file: {exc}")
            return False

    @pyqtSlot(result=bool)
    def download_current_page_pdf(self) -> bool:
        try:
            obj = self.parent()
            while obj is not None:
                dl = getattr(obj, "_handle_download_pdf", None)
                if callable(dl):
                    try:
                        dl()
                        return True
                    except Exception as exc2:
                        logger.error(f"Bridge: Download PDF handler error: {exc2}", exc_info=True)
                        return False
                obj = obj.parent() if hasattr(obj, "parent") else None
            return False
        except Exception as exc:
            logger.error(f"Bridge: Download PDF failed: {exc}", exc_info=True)
            return False


class _AuthorityLayoutFileBridge(QObject):
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

    @pyqtSlot(result=str)
    def load_positions(self) -> str:
        try:
            path = _authority_layout_file_path()
            if not path.exists():
                return ""
            with _AUTHORITY_LAYOUT_LOCK:
                raw = path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                return ""
            return json.dumps(parsed)
        except Exception as exc:
            logger.warning(f"Failed to load authority letter layout positions from file: {exc}")
            return ""

    @pyqtSlot(str, result=bool)
    def save_positions(self, positions_json: str) -> bool:
        try:
            parsed = json.loads(str(positions_json or ""))
            if not isinstance(parsed, dict):
                return False
            path = _authority_layout_file_path()
            with _AUTHORITY_LAYOUT_LOCK:
                path.write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception as exc:
            logger.warning(f"Failed to save authority letter layout positions to file: {exc}")
            return False

class _SilentPrintJob(QObject):
    def __init__(self, html_content: str, on_done):
        super().__init__()
        self._html_content = _apply_urdu_font_to_html(html_content or "")
        self._on_done = on_done
        self._view = None
        self._printer = None

    def start(self) -> None:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtPrintSupport import QPrinter

        self._printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        self._view = QWebEngineView()
        self._view.resize(1, 1)
        self._view.loadFinished.connect(self._on_loaded)
        self._view.setHtml(self._html_content)

    def _on_loaded(self, ok: bool) -> None:
        if not ok or not self._view:
            self._fail("Unable to load print content.")
            return
        if not self._printer:
            self._fail("Printer is not available.")
            return

        view_print = getattr(self._view, "print", None)
        if not callable(view_print):
            self._fail("Silent printing is not supported by this QtWebEngine build. Please update PyQt6-WebEngine.")
            return
        try:
            view_print(self._printer, self._on_printed)
        except TypeError:
            try:
                view_print(self._printer)
                self._on_printed(True)
            except Exception as e:
                self._fail(f"Silent printing failed: {e}")
        except Exception as e:
            self._fail(f"Silent printing failed: {e}")

    def _on_printed(self, success: bool) -> None:
        logger.info(f"Silent print success: {success}")
        self._cleanup()

    def _fail(self, msg: str) -> None:
        logger.error(msg)
        QMessageBox.critical(None, "Print Error", msg)
        self._cleanup()

    def _cleanup(self) -> None:
        if self._view:
            self._view.deleteLater()
        self.deleteLater()
        try:
            self._on_done()
        except Exception:
            pass

class _DialogPrintJob(QObject):
    def __init__(self, html_content: str, parent: Optional[QWidget], on_done):
        super().__init__()
        self._html_content = _apply_urdu_font_to_html(html_content or "")
        self._parent = parent
        self._on_done = on_done
        self._view = None
        self._printer = None

    def start(self) -> None:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtPrintSupport import QPrinter

        self._printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        self._view = QWebEngineView()
        self._view.resize(1, 1)
        self._view.loadFinished.connect(self._on_loaded)
        self._view.setHtml(self._html_content)

    def _on_loaded(self, ok: bool) -> None:
        if not ok or not self._view:
            self._fail("Unable to load print content.")
            return
        if not self._printer:
            self._fail("Printer is not available.")
            return

        from PyQt6.QtPrintSupport import QPrintDialog

        dlg = QPrintDialog(self._printer, self._parent)
        if dlg.exec() != QPrintDialog.DialogCode.Accepted:
            self._cleanup()
            return

        view_print = getattr(self._view, "print", None)
        if not callable(view_print):
            self._fail("Printing is not supported by this QtWebEngine build. Please update PyQt6-WebEngine.")
            return
        try:
            view_print(self._printer, self._on_printed)
        except TypeError:
            try:
                view_print(self._printer)
                self._on_printed(True)
            except Exception as e:
                self._fail(f"Printing failed: {e}")
        except Exception as e:
            self._fail(f"Printing failed: {e}")

    def _on_printed(self, success: bool) -> None:
        logger.info(f"Dialog print success: {success}")
        self._cleanup()

    def _fail(self, msg: str) -> None:
        logger.error(msg)
        QMessageBox.critical(self._parent, "Print Error", msg)
        self._cleanup()

    def _cleanup(self) -> None:
        if self._view:
            self._view.deleteLater()
        self.deleteLater()
        try:
            self._on_done()
        except Exception:
            pass

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
            "business_phone": settings.get("business_phone", "0302-8691288"),
            "business_ntn": settings.get("business_ntn", "1234597-8")
        }

    def render_ledger_statement(self, ledger_data: Dict[str, Any]) -> str:
        """Renders the HTML for a customer ledger statement."""
        business = self._get_business_info()
        cust = ledger_data.get("customer", {})
        entries = ledger_data.get("entries", [])
        
        # Format dates and numbers
        date_range = ledger_data.get("date_range", "Full Statement")
        total_debit = sum(float(e.get("debit") or 0) for e in entries)
        total_credit = sum(float(e.get("credit") or 0) for e in entries)
        final_balance = entries[-1].get("balance") if entries else 0.0

        rows_html = ""
        for e in entries:
            rows_html += f"""
            <tr>
                <td>{e.get('date', '')}</td>
                <td>{e.get('description', '').replace('\n', '<br>')}</td>
                <td style="text-align: right;">{float(e.get('debit') or 0):,.2f}</td>
                <td style="text-align: right;">{float(e.get('credit') or 0):,.2f}</td>
                <td style="text-align: right; font-weight: bold;">{float(e.get('balance') or 0):,.2f}</td>
            </tr>
            """

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; padding: 20px; color: #333; }}
        .header {{ text-align: center; border-bottom: 2px solid #2c3e50; padding-bottom: 10px; margin-bottom: 20px; }}
        .business-name {{ font-size: 24px; font-weight: bold; color: #2c3e50; }}
        .report-title {{ font-size: 18px; margin-top: 5px; text-transform: uppercase; letter-spacing: 1px; }}
        
        .customer-info {{ width: 100%; margin-bottom: 20px; border: 1px solid #ddd; padding: 10px; border-radius: 5px; background: #f9f9f9; }}
        .customer-info td {{ padding: 5px; font-size: 14px; }}
        .info-label {{ font-weight: bold; color: #7f8c8d; width: 150px; }}
        
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th {{ background-color: #2c3e50; color: white; padding: 10px; text-align: left; font-size: 13px; }}
        td {{ border-bottom: 1px solid #ddd; padding: 8px; font-size: 12px; vertical-align: top; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
        
        .summary {{ margin-top: 20px; text-align: right; }}
        .summary-box {{ display: inline-block; border: 2px solid #2c3e50; padding: 10px; border-radius: 5px; }}
        .summary-item {{ font-size: 14px; margin: 5px 0; }}
        .final-bal {{ font-size: 18px; font-weight: bold; color: #e74c3c; border-top: 1px solid #ddd; padding-top: 5px; }}
        
        @media print {{
            body {{ padding: 0; }}
            .no-print {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="business-name">{business['business_name']}</div>
        <div>{business['business_address']} | {business['business_phone']}</div>
        <div class="report-title">Customer Ledger Statement</div>
        <div style="font-size: 12px; color: #7f8c8d;">Period: {date_range} | Generated: {dt.datetime.now().strftime('%d-%m-%Y %H:%M')}</div>
    </div>

    <div class="customer-info">
        <table style="border: none; background: none; margin: 0;">
            <tr>
                <td class="info-label">Customer Name:</td>
                <td style="font-weight: bold; font-size: 16px;">{cust.get('name', 'N/A')}</td>
                <td class="info-label">Phone Number:</td>
                <td>{cust.get('phone', 'N/A')}</td>
            </tr>
            <tr>
                <td class="info-label">Father's Name:</td>
                <td>{cust.get('father_name', 'N/A')}</td>
                <td class="info-label">CNIC:</td>
                <td>{cust.get('cnic', 'N/A')}</td>
            </tr>
            <tr>
                <td class="info-label">Address:</td>
                <td colspan="3">{cust.get('address', 'N/A')}</td>
            </tr>
        </table>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width: 100px;">Date</th>
                <th>Description</th>
                <th style="width: 100px; text-align: right;">Debit (Rs.)</th>
                <th style="width: 100px; text-align: right;">Credit (Rs.)</th>
                <th style="width: 120px; text-align: right;">Balance (Rs.)</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>

    <div class="summary">
        <div class="summary-box">
            <div class="summary-item">Total Debits: Rs. {total_debit:,.2f}</div>
            <div class="summary-item">Total Credits: Rs. {total_credit:,.2f}</div>
            <div class="summary-item final-bal">Outstanding Balance: Rs. {final_balance:,.2f}</div>
        </div>
    </div>
    
    <div style="margin-top: 50px; font-size: 10px; color: #95a5a6; text-align: center;">
        This is a computer-generated statement and does not require a signature.
    </div>
</body>
</html>
        """
        return html

    def print_custom_html(self, html_content: str, parent: Optional[QWidget] = None, on_done=None):
        """Prints custom HTML content with a print dialog."""
        if not _WEBENGINE_AVAILABLE:
            QMessageBox.critical(parent, "Print Error", "WebEngine is not available. Cannot print HTML.")
            return

        job = _DialogPrintJob(html_content, parent, on_done)
        job.start()
        # Keep reference to prevent GC
        self._last_job = job

    def render_invoice(self, invoice_data: Dict[str, Any]) -> str:
        """Renders the HTML for an invoice on a fixed (pre-printed) template."""
        data = self._get_business_info()
        data.update(invoice_data or {})

        date_val = data.get("date")
        if isinstance(date_val, dt.datetime):
            date_str = date_val.strftime("%d-%m-%Y")
        else:
            date_str = str(date_val or "")

        def esc(v: object) -> str:
            s = str(v if v is not None else "")
            return (
                s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#39;")
            )

        items = data.get("items") if isinstance(data.get("items"), list) else []
        primary = items[0] if items and isinstance(items[0], dict) else {}
        relation_prefix = str(data.get("relation_prefix") or "").strip()
        father_name = str(data.get("father_name") or "").strip()
        if relation_prefix and relation_prefix not in ("S/O", "D/O", "W/O"):
            relation_prefix = "S/O"
        if father_name and not relation_prefix:
            relation_prefix = "S/O"
        customer_name = str(data.get("customer_name") or "").strip()
        if father_name:
            customer_name_line = f"{customer_name} {relation_prefix} {father_name}".strip()
        else:
            customer_name_line = customer_name
        qr_base64 = str(data.get("qr_code_base64") or "")
        qr_img_html = ""
        if qr_base64.strip():
            qr_img_html = (
                "<img id=\"invoiceQr\" class=\"draggable\" data-pos-key=\"invoice_qr\" "
                "data-default-left=\"2.95in\" data-default-top=\"1.52in\" "
                "style=\"position:absolute; left: 2.95in; top: 1.52in; width: 1.65in; height: 1.65in;\" "
                f"src=\"data:image/png;base64,{esc(qr_base64)}\" />"
            )

        settings_logo_html = ""
        try:
            from app.services.settings_service import settings_service
            logo_cfg = settings_service.get_invoice_logo() or {}
            logo_data_url = str(logo_cfg.get("data_url") or "").strip()
            logo_name = str(logo_cfg.get("name") or "").strip()
            if logo_data_url:
                settings_logo_html = (
                    '<div id="settingsLogo1" class="draggable" '
                    'data-pos-key="custom_logo_settings_1" '
                    'data-default-left="0.25in" data-default-top="1.05in" '
                    'data-default-width="1.35in" data-default-height="auto" '
                    'draggable="false" '
                    'style="position:absolute; left: 0.25in; top: 1.05in; width: 1.35in; height: auto; '
                    'background: transparent; user-select: none; -webkit-user-select: none; '
                    '-webkit-user-drag: none; touch-action: none;">'
                    f'<img src="{esc(logo_data_url)}" alt="{esc(logo_name or "logo")}" '
                    'draggable="false" '
                    'style="pointer-events: none; display: block; width: 100%; height: auto; max-width: 100%; '
                    'user-select: none; -webkit-user-select: none;" />'
                    '</div>'
                )
        except Exception as e:
            logger.warning(f"Could not load settings invoice logo for render_invoice: {e}")
            settings_logo_html = ""

        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Invoice - {esc(data.get("invoice_number") or "")}</title>
  <style>
    @page {{ size: A4 portrait; margin: 0; }}
    html, body {{ margin: 0; padding: 0; }}
    body {{ font-family: Arial, sans-serif; color: #000; background: #ffffff; }}
    .page-wrap {{
      width: 100%;
      height: 100vh;
      overflow: auto;
      display: flex;
      justify-content: center;
      align-items: flex-start;
      padding: 0;
      box-sizing: border-box;
    }}
    .page-shell {{ position: relative; }}
    .page {{
      position: relative;
      width: 8.27in;
      height: 11.69in;
      overflow: hidden;
      transform-origin: top left;
      background: transparent;
    }}
    .field {{
      position: absolute;
      display: inline-block;
      font-size: 11pt;
      font-weight: 600;
      white-space: nowrap;
    }}
    .label {{
      position: absolute;
      display: inline-block;
      font-size: 9pt;
      font-weight: 500;
      color: #555;
      white-space: nowrap;
    }}
    .mono {{
      font-family: Consolas, 'Courier New', monospace;
      font-weight: 700;
    }}
    .draggable {{
      /* Always-on red outline removed: shows ONLY on hover, or when .selected (active edit) */
      outline: none;
      outline-offset: 2px;
      touch-action: none;
      will-change: left, top, transform;
      transition: transform 120ms ease, box-shadow 120ms ease, outline-color 120ms ease;
      user-select: none;
      -webkit-user-select: none;
      cursor: grab;
    }}
    .draggable:hover {{
      outline: 1px dashed rgba(37, 99, 235, 0.55);
      outline-offset: 2px;
    }}
    .draggable.selected {{
      outline: 1px dashed rgba(220, 53, 69, 0.85);
      outline-offset: 2px;
    }}
    .dragging {{
      outline: 2px solid rgba(220, 53, 69, 0.95) !important;
      transform: scale(1.02);
      box-shadow: 0 8px 18px rgba(0, 0, 0, 0.18);
      cursor: grabbing;
    }}
    .pos-hud {{
      position: fixed;
      left: 12px;
      bottom: 12px;
      background: rgba(0, 0, 0, 0.75);
      color: #fff;
      font: 12px/1.2 Arial, sans-serif;
      padding: 8px 10px;
      border-radius: 6px;
      z-index: 99999;
      display: none;
      white-space: nowrap;
    }}
    .hidden-field {{
      color: transparent !important;
    }}
    img.hidden-field {{
      opacity: 0.05 !important;
    }}
    .wrap-field {{
      white-space: normal !important;
      display: inline-block !important;
      max-width: 280px;
    }}
    .edit-mode {{
      user-select: text !important;
      -webkit-user-select: text !important;
      cursor: text !important;
      touch-action: auto !important;
    }}
    .sub-hidden {{
      opacity: 0.15;
      text-decoration: line-through;
    }}
    .style-toolbar {{
      position: fixed;
      top: 12px;
      right: 12px;
      z-index: 99998;
      background: rgba(30, 34, 41, 0.96);
      color: #fff;
      font: 12px/1.3 Arial, sans-serif;
      padding: 10px 12px;
      border-radius: 10px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
      display: flex;
      flex-direction: column;
      gap: 8px;
      min-width: 290px;
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }}
    .style-toolbar .st-title {{
      font-weight: 700;
      font-size: 12px;
      color: #dbeafe;
      margin-bottom: 2px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .style-toolbar .st-title .st-target {{
      font-weight: 600;
      color: #facc15;
      max-width: 170px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .style-toolbar .st-row {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .style-toolbar label.st-lbl {{
      min-width: 70px;
      color: #cbd5e1;
      font-weight: 600;
      font-size: 11px;
    }}
    .style-toolbar button {{
      background: #334155;
      border: 1px solid #475569;
      color: #fff;
      padding: 5px 9px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: background 120ms ease, transform 80ms ease, border-color 120ms ease;
      line-height: 1;
    }}
    .style-toolbar button:hover {{
      background: #475569;
      border-color: #64748b;
    }}
    .style-toolbar button:active {{
      transform: translateY(1px);
    }}
    .style-toolbar button.active {{
      background: #2563eb;
      border-color: #3b82f6;
      color: #fff;
    }}
    .style-toolbar button.danger {{
      background: #7f1d1d;
      border-color: #991b1b;
    }}
    .style-toolbar button.danger:hover {{
      background: #991b1b;
    }}
    .style-toolbar input[type="range"] {{
      flex: 1;
      min-width: 110px;
      accent-color: #3b82f6;
    }}
    .style-toolbar .st-val {{
      min-width: 38px;
      text-align: right;
      font-variant-numeric: tabular-nums;
      color: #e2e8f0;
      font-weight: 600;
    }}
    .style-toolbar select,
    .style-toolbar input[type="color"] {{
      background: #1e293b;
      color: #f1f5f9;
      border: 1px solid #475569;
      border-radius: 6px;
      padding: 4px 6px;
      font-size: 12px;
      font-weight: 600;
    }}
    .style-toolbar input[type="color"] {{
      padding: 2px;
      width: 38px;
      height: 28px;
      cursor: pointer;
    }}
    .style-toolbar .st-divider {{
      height: 1px;
      background: rgba(148, 163, 184, 0.22);
      margin: 2px 0;
    }}
    .style-toolbar .st-actions {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }}
    .style-toolbar .st-actions button {{
      font-size: 11px;
      padding: 6px 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
    }}
    .style-toolbar button.add-logo {{
      background: #065f46;
      border-color: #047857;
    }}
    .style-toolbar button.add-logo:hover {{ background: #047857; border-color: #059669; }}
    .style-toolbar button.delete-selection {{
      background: #7f1d1d;
      border-color: #991b1b;
    }}
    .style-toolbar button.delete-selection:hover {{ background: #991b1b; border-color: #b91c1c; }}
    .style-toolbar button.delete-selection:disabled,
    .style-toolbar button:disabled {{
      opacity: 0.45;
      cursor: not-allowed;
      background: #334155 !important;
      border-color: #475569 !important;
    }}
    #stSizeSliderRow label.st-lbl {{ min-width: 78px; }}
    .resize-handle {{
      position: absolute;
      z-index: 100000;
      width: 14px;
      height: 14px;
      background: #ffffff;
      border: 2px solid #2563eb;
      border-radius: 50%;
      box-shadow: 0 2px 6px rgba(0,0,0,0.25);
      box-sizing: border-box;
      touch-action: none;
      user-select: none;
      -webkit-user-select: none;
    }}
    .resize-handle:hover {{ background: #dbeafe; border-color: #1d4ed8; }}
    .resize-handle.nw {{ left: -8px; top: -8px; cursor: nwse-resize; }}
    .resize-handle.n  {{ left: calc(50% - 7px); top: -8px; cursor: ns-resize; }}
    .resize-handle.ne {{ right: -8px; top: -8px; cursor: nesw-resize; }}
    .resize-handle.e  {{ right: -8px; top: calc(50% - 7px); cursor: ew-resize; }}
    .resize-handle.se {{ right: -8px; bottom: -8px; cursor: nwse-resize; }}
    .resize-handle.s  {{ left: calc(50% - 7px); bottom: -8px; cursor: ns-resize; }}
    .resize-handle.sw {{ left: -8px; bottom: -8px; cursor: nesw-resize; }}
    .resize-handle.w  {{ left: -8px; top: calc(50% - 7px); cursor: ew-resize; }}
    @media print {{
      .resize-handle {{ display: none !important; }}
      .draggable {{ outline: none !important; box-shadow: none !important; }}
      .pos-hud {{ display: none !important; }}
      .hidden-field {{ display: none !important; }}
      .sub-hidden {{ display: none !important; }}
      .style-toolbar {{ display: none !important; }}
      body {{ background: #fff !important; }}
      .page-wrap {{ height: auto !important; overflow: visible !important; padding: 0 !important; }}
      .page-shell {{ width: auto !important; height: auto !important; }}
      .page {{ transform: none !important; }}
    }}
  </style>
</head>
<body>
  <div class="page-wrap">
    <div id="pageShell" class="page-shell">
      <div id="invoicePage" class="page">
        <div id="hondaLogo" class="draggable" data-pos-key="honda_logo" data-default-left="0.25in" data-default-top="0.18in" data-default-width="1.20in" data-default-height="0.80in" style="position:absolute; left: 0.25in; top: 0.18in; width: 1.20in; height: 0.80in; background: transparent; user-select: none; -webkit-user-select: none; -webkit-user-drag: none; touch-action: none;">
          <svg draggable="false" viewBox="0 0 240 160" xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" style="pointer-events: none; display: block; user-select: none; -webkit-user-select: none;">
            <g fill="#C20000">
              <path d="M30,132 Q20,102 38,76 Q50,58 72,50 Q94,42 118,38 Q142,36 166,40 Q190,46 208,58 L200,70 Q180,60 162,56 Q140,52 118,54 Q96,56 78,64 Q62,72 52,88 Q44,104 42,122 Z"/>
              <path d="M42,142 Q34,116 48,94 Q60,76 82,68 Q108,58 134,56 Q160,56 184,62 Q204,68 220,80 L212,92 Q194,82 178,78 Q158,72 138,72 Q116,72 96,78 Q76,84 62,98 Q52,112 48,128 Z"/>
              <path d="M54,150 Q48,126 60,108 Q72,90 94,82 Q120,74 146,74 Q172,74 194,82 Q214,88 230,102 L222,112 Q208,104 192,98 Q172,92 154,92 Q132,92 110,96 Q88,102 74,114 Q64,126 60,138 Z"/>
              <path d="M66,156 Q62,138 72,122 Q84,106 106,100 Q132,94 158,96 Q182,98 202,108 Q218,116 236,130 L230,138 Q216,130 202,124 Q184,118 166,116 Q144,114 122,116 Q102,120 86,130 Q74,140 70,150 Z"/>
            </g>
            <g fill="#C20000" font-family="Arial Black, Arial, sans-serif" font-weight="900" text-anchor="middle">
              <text x="120" y="152" font-size="44" letter-spacing="2">HONDA</text>
            </g>
          </svg>
        </div>
        <div id="fbrPosLogo" class="draggable" data-pos-key="fbr_pos_logo" data-default-left="6.70in" data-default-top="0.15in" data-default-width="1.25in" data-default-height="0.88in" style="position:absolute; left: 6.70in; top: 0.15in; width: 1.25in; height: 0.88in; background: transparent; user-select: none; -webkit-user-select: none; -webkit-user-drag: none; touch-action: none;">
          <svg draggable="false" viewBox="0 0 260 180" xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" preserveAspectRatio="xMidYMid meet" style="pointer-events: none; display: block; user-select: none; -webkit-user-select: none;">
            <defs>
              <linearGradient id="rainbowArc" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#2ca02c"/>
                <stop offset="50%" stop-color="#d4af37"/>
                <stop offset="100%" stop-color="#2ca02c"/>
              </linearGradient>
            </defs>
            <path d="M20,46 Q130,4 240,46" fill="none" stroke="url(#rainbowArc)" stroke-width="8" stroke-linecap="round"/>
            <polygon points="130,4 136,24 156,30 136,36 130,56 124,36 104,30 124,24" fill="#d4af37" stroke="#b8941f" stroke-width="1"/>
            <g font-family="Arial Black, Arial, sans-serif" font-weight="900" fill="#0047AB" text-anchor="middle">
              <text x="80" y="94" font-size="44">F</text>
              <text x="130" y="94" font-size="44">B</text>
              <text x="180" y="94" font-size="44">R</text>
            </g>
            <rect x="12" y="104" width="236" height="68" rx="14" fill="#0047AB"/>
            <g font-family="Arial Black, Arial, sans-serif" font-weight="900" fill="#FFFFFF" text-anchor="middle">
              <text x="52" y="158" font-size="60">P</text>
              <text x="130" y="158" font-size="60">O</text>
              <text x="208" y="158" font-size="60">S</text>
            </g>
            <g font-family="Arial, sans-serif" font-weight="700" fill="#E6EDF5" text-anchor="middle" letter-spacing="1.4">
              <text x="130" y="178" font-size="14">INVOICING SYSTEM</text>
            </g>
          </svg>
        </div>
        {settings_logo_html}

        <div id="businessName" class="field draggable" data-pos-key="business_name" data-default-left="2.40in" data-default-top="0.22in" style="left: 2.40in; top: 0.22in; font-size: 16pt; font-weight: 800; text-align: center; white-space: nowrap;">EHSAN TRADERS</div>
        <div id="businessAddress" class="field draggable" data-pos-key="business_address" data-default-left="1.70in" data-default-top="0.52in" style="left: 1.70in; top: 0.52in; font-size: 10pt; font-weight: 600; text-align: center; white-space: nowrap;">NEAR BUS STAND RAJANA ROAD KAMALIA</div>
        <div id="businessNtn" class="field draggable" data-pos-key="business_ntn" data-default-left="3.30in" data-default-top="0.78in" style="left: 3.30in; top: 0.78in; font-size: 10pt; font-weight: 700; text-align: center; white-space: nowrap;">NTN: 2755340</div>

        <div id="lblDate" class="label draggable" data-pos-key="lbl_date" data-default-left="0.20in" data-default-top="1.05in" style="left: 0.20in; top: 1.05in;">Date:</div>
        <div id="invoiceDate" class="field mono draggable" data-pos-key="invoice_date" data-default-left="0.95in" data-default-top="1.05in" style="left: 0.95in; top: 1.05in;">{esc(date_str)}</div>

        <div id="lblInvoiceNumber" class="label draggable" data-pos-key="lbl_invoice_number" data-default-left="0.20in" data-default-top="1.45in" style="left: 0.20in; top: 1.45in;">Invoice #:</div>
        <div id="invoiceNumber" class="field mono draggable" data-pos-key="invoice_number" data-default-left="0.95in" data-default-top="1.45in" style="left: 0.95in; top: 1.45in;">{esc(data.get("invoice_number") or "")}</div>

        <div id="lblCustomerName" class="label draggable" data-pos-key="lbl_customer_name" data-default-left="0.20in" data-default-top="1.95in" style="left: 0.20in; top: 1.95in;">Customer:</div>
        <div id="customerName" class="field draggable" data-pos-key="customer_name" data-default-left="0.95in" data-default-top="1.95in" style="left: 0.95in; top: 1.95in;">{esc(customer_name_line)}</div>

        <div id="lblCustomerAddress" class="label draggable" data-pos-key="lbl_customer_address" data-default-left="0.20in" data-default-top="2.35in" style="left: 0.20in; top: 2.35in;">Address:</div>
        <div id="customerAddress" class="field draggable" data-pos-key="customer_address" data-default-left="0.95in" data-default-top="2.35in" style="left: 0.95in; top: 2.35in;">{esc(data.get("customer_address") or "")}</div>

        <div id="lblItemDesc" class="label draggable" data-pos-key="lbl_item_desc" data-default-left="0.20in" data-default-top="4.65in" style="left: 0.20in; top: 4.65in;">Item:</div>
        <div id="itemDesc1" class="field draggable" data-pos-key="item_desc_1" data-default-left="0.95in" data-default-top="4.65in" style="left: 0.95in; top: 4.65in;">{esc(primary.get("model") or primary.get("description") or "")}</div>

        <div id="lblSaleValue" class="label draggable" data-pos-key="lbl_sale_value" data-default-left="3.15in" data-default-top="4.42in" style="left: 3.15in; top: 4.42in;">Sale Value</div>
        <div id="saleValue1" class="field mono draggable" data-pos-key="sale_value_1" data-default-left="3.75in" data-default-top="4.65in" style="left: 3.75in; top: 4.65in; text-align: right;">Rs. {esc(primary.get("sale_value") or "")}</div>

        <div id="lblSalesTax" class="label draggable" data-pos-key="lbl_sales_tax" data-default-left="4.15in" data-default-top="4.42in" style="left: 4.15in; top: 4.42in;">Sales Tax</div>
        <div id="salesTax1" class="field mono draggable" data-pos-key="sales_tax_1" data-default-left="4.65in" data-default-top="4.65in" style="left: 4.65in; top: 4.65in; text-align: right;">Rs. {esc(primary.get("sales_tax") or "")}</div>

        <div id="lblLevy" class="label draggable" data-pos-key="lbl_levy" data-default-left="5.15in" data-default-top="4.42in" style="left: 5.15in; top: 4.42in;">Levy</div>
        <div id="levy1" class="field mono draggable" data-pos-key="levy_1" data-default-left="5.55in" data-default-top="4.65in" style="left: 5.55in; top: 4.65in; text-align: right;">Rs. {esc(primary.get("levy") or "")}</div>

        <div id="lblTotalLine" class="label draggable" data-pos-key="lbl_total_line" data-default-left="6.05in" data-default-top="4.42in" style="left: 6.05in; top: 4.42in;">Total</div>
        <div id="totalLine1" class="field mono draggable" data-pos-key="total_line_1" data-default-left="6.45in" data-default-top="4.65in" style="left: 6.45in; top: 4.65in; text-align: right;">Rs. {esc(primary.get("total_line") or primary.get("price") or "")}</div>

        <div id="lblEngineNo" class="label draggable" data-pos-key="lbl_engine_no" data-default-left="0.20in" data-default-top="5.85in" style="left: 0.20in; top: 5.85in;">Engine #:</div>
        <div id="engineNo" class="field mono draggable" data-pos-key="engine_no" data-default-left="0.95in" data-default-top="5.85in" style="left: 0.95in; top: 5.85in;">{esc(primary.get("engine") or "")}</div>

        <div id="lblChassisNo" class="label draggable" data-pos-key="lbl_chassis_no" data-default-left="0.20in" data-default-top="6.25in" style="left: 0.20in; top: 6.25in;">Chassis #:</div>
        <div id="chassisNo" class="field mono draggable" data-pos-key="chassis_no" data-default-left="0.95in" data-default-top="6.25in" style="left: 0.95in; top: 6.25in;">{esc(primary.get("chassis") or "")}</div>

        <div id="lblModel" class="label draggable" data-pos-key="lbl_model" data-default-left="0.20in" data-default-top="6.65in" style="left: 0.20in; top: 6.65in;">Model:</div>
        <div id="model" class="field draggable" data-pos-key="model" data-default-left="0.95in" data-default-top="6.65in" style="left: 0.95in; top: 6.65in;">{esc(primary.get("model") or "")}</div>

        <div id="lblColor" class="label draggable" data-pos-key="lbl_color" data-default-left="0.20in" data-default-top="7.05in" style="left: 0.20in; top: 7.05in;">Color:</div>
        <div id="color" class="field draggable" data-pos-key="color" data-default-left="0.95in" data-default-top="7.05in" style="left: 0.95in; top: 7.05in;">{esc(primary.get("color") or "")}</div>

        <div id="lblRegLetter" class="label draggable" data-pos-key="lbl_registration_letter_no" data-default-left="0.20in" data-default-top="7.65in" style="left: 0.20in; top: 7.65in;">Reg Letter #:</div>
        <div id="regLetter" class="field mono draggable" data-pos-key="registration_letter_no" data-default-left="0.95in" data-default-top="7.65in" style="left: 0.95in; top: 7.65in;">{esc(data.get("registration_letter_no") or "")}</div>

        <div id="lblFbrInvoice" class="label draggable" data-pos-key="lbl_invoice_fbr_id" data-default-left="2.55in" data-default-top="3.15in" style="left: 2.55in; top: 3.15in;">FBR Invoice #:</div>

        <div id="lblPosServiceFee" class="label draggable" data-pos-key="lbl_pos_service_fee" data-default-left="5.55in" data-default-top="9.55in" style="left: 5.55in; top: 9.55in;">POS Service Fee:</div>
        <div id="posServiceFee" class="field mono draggable" data-pos-key="pos_service_fee" data-default-left="6.55in" data-default-top="9.55in" style="left: 6.55in; top: 9.55in; text-align: right;">Rs. 1</div>

        <div id="lblTotalAmount" class="label draggable" data-pos-key="lbl_total_amount" data-default-left="5.55in" data-default-top="9.90in" style="left: 5.55in; top: 9.90in;">Grand Total:</div>
        <div id="totalAmount" class="field mono draggable" data-pos-key="total_amount" data-default-left="6.55in" data-default-top="9.90in" style="left: 6.55in; top: 9.90in; text-align: right;">Rs. {esc(data.get("total_amount") or "")}</div>

        {qr_img_html}
        <div id="invoiceFbrId" class="field mono draggable" data-pos-key="invoice_fbr_id" data-default-left="2.55in" data-default-top="3.35in" style="left: 2.55in; top: 3.35in; font-size: 10pt;">{esc(data.get("fbr_invoice_number") or "")}</div>
      </div>
    </div>
  </div>

  <div id="styleToolbar" class="style-toolbar" style="display:none;">
    <div class="st-title">
      <span>Styling Toolbar</span>
      <span id="stTarget" class="st-target">—</span>
    </div>
    <div class="st-divider"></div>
    <div class="st-row st-actions">
      <button id="stAddLogo" class="add-logo" type="button" title="Add a custom logo / image (PNG / JPG / SVG / GIF)">＋ Add Logo</button>
      <button id="stDelete" class="delete-selection" type="button" title="Delete selected logo or field (Delete / Backspace)">🗑 Delete</button>
    </div>
    <div class="st-row" style="margin-top:4px;">
      <button id="stDownloadPdf" type="button" title="Download this invoice as a PDF file (Ctrl+S)" style="flex:1; background:#0369a1; border:1px solid #075985; color:#fff; font-weight:700; padding:6px 8px; display:flex; align-items:center; justify-content:center; gap:5px; border-radius:6px;">⬇ Download Invoice as PDF</button>
    </div>
    <div id="stSizeSliderRow" class="st-row" style="margin-top:4px;">
      <label class="st-lbl">Size</label>
      <input id="stSize" type="range" min="20" max="600" step="1" value="120" />
      <input id="stLockAspect" type="checkbox" title="Lock aspect ratio" checked style="accent-color:#3b82f6; margin:0 0 0 4px;" />
    </div>
    <div class="st-divider"></div>
    <div class="st-row">
      <label class="st-lbl">Font Size</label>
      <input id="stFontSize" type="range" min="6" max="48" step="1" value="11" />
      <span id="stFontSizeVal" class="st-val">11px</span>
    </div>
    <div class="st-row">
      <label class="st-lbl">Font Family</label>
      <select id="stFontFamily" style="flex:1;">
        <option value="Arial, sans-serif">Arial</option>
        <option value="Calibri, Arial, sans-serif">Calibri</option>
        <option value="Times New Roman, serif">Times New Roman</option>
        <option value="Georgia, serif">Georgia</option>
        <option value="Verdana, Geneva, sans-serif">Verdana</option>
        <option value="Consolas, &quot;Courier New&quot;, monospace">Consolas (Mono)</option>
        <option value="'Courier New', Courier, monospace">Courier New</option>
      </select>
    </div>
    <div class="st-row">
      <label class="st-lbl">Style</label>
      <button id="stBold" type="button" title="Bold (B)"><b>B</b></button>
      <button id="stItalic" type="button" title="Italic (I)"><i>I</i></button>
      <button id="stUnderline" type="button" title="Underline (U)"><u>U</u></button>
      <label class="st-lbl" style="min-width:auto;margin-left:8px;">Color</label>
      <input id="stColor" type="color" value="#000000" title="Text Color" />
      <button id="stResetColor" type="button" title="Reset color to default" style="padding:5px 7px;">R</button>
    </div>
    <div class="st-divider"></div>
    <div class="st-row">
      <button id="stHide" type="button" title="Hide / Show (H)">Hide</button>
      <button id="stWrap" type="button" title="Word Wrap (W)">Wrap</button>
      <button id="stEdit" type="button" title="Edit Text (F2)">Edit</button>
      <button id="stReset" class="danger" type="button" title="Reset this field's style & position (dbl-click)">Reset</button>
    </div>
  </div>
  <input id="stFileInput" type="file" accept="image/png, image/jpeg, image/jpg, image/gif, image/svg+xml, image/webp" style="display:none;" />

  <div id="posHud" class="pos-hud"></div>
  <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
  <script>
    (function () {{
      const STORAGE_KEY = 'fbr_invoice_template_positions_v2';
      const API_BASES = ['', 'http://127.0.0.1:9000', 'http://localhost:9000'];
      const API_PATH = '/api/print-layout/invoice';
      let qtBridge = null;
      const page = document.getElementById('invoicePage');
      const shell = document.getElementById('pageShell');
      const hud = document.getElementById('posHud');
      if (!page || !hud) return;

      function initQtBridge() {{
        if (qtBridge) return Promise.resolve(qtBridge);
        const hasChannel = typeof QWebChannel !== 'undefined' && window.qt && qt.webChannelTransport;
        if (!hasChannel) return Promise.resolve(null);
        return new Promise((resolve) => {{
          try {{
            new QWebChannel(qt.webChannelTransport, (channel) => {{
              qtBridge = (channel && channel.objects) ? channel.objects.invoiceLayoutBridge : null;
              resolve(qtBridge || null);
            }});
          }} catch (_) {{
            resolve(null);
          }}
        }});
      }}

      function nowMs() {{ return Date.now(); }}
      function safeParseJson(text) {{ try {{ return JSON.parse(String(text || '')); }} catch (_) {{ return null; }} }}
      function clamp(n, min, max) {{ return Math.max(min, Math.min(max, n)); }}
      function getPageRect() {{
        const r = page.getBoundingClientRect();
        const scale = (() => {{
          const s = shell ? Number(shell.getAttribute('data-scale') || 1) : 1;
          return Number.isFinite(s) && s > 0 ? s : 1;
        }})();
        return {{
          left: r.left,
          top: r.top,
          width: page.offsetWidth || (r.width / scale),
          height: page.offsetHeight || (r.height / scale),
          scale,
        }};
      }}
      function getRelPx(el, pageRect) {{
        const r = el.getBoundingClientRect();
        const s = pageRect && pageRect.scale ? pageRect.scale : 1;
        return {{ x: (r.left - pageRect.left) / s, y: (r.top - pageRect.top) / s, w: r.width / s, h: r.height / s }};
      }}

      function readSaved() {{
        try {{
          const raw = localStorage.getItem(STORAGE_KEY);
          const parsed = safeParseJson(raw || '{{}}');
          if (!parsed || typeof parsed !== 'object') return {{ version: 2, updated_at: 0, elements: {{}} }};
          if (parsed.version !== 2) return {{ version: 2, updated_at: 0, elements: {{}} }};
          const elements = parsed.elements;
          if (!elements || typeof elements !== 'object') return {{ version: 2, updated_at: 0, elements: {{}} }};
          return {{ version: 2, updated_at: Number(parsed.updated_at || 0), elements: elements }};
        }} catch (_) {{
          return {{ version: 2, updated_at: 0, elements: {{}} }};
        }}
      }}
      function writeSaved(doc) {{ try {{ localStorage.setItem(STORAGE_KEY, JSON.stringify(doc)); }} catch (_) {{}} }}
      function isImg(el) {{ return !!(el && el.tagName === 'IMG'); }}
      function getFontPx(el) {{
        try {{
          const fs = getComputedStyle(el).fontSize;
          const v = parseFloat(fs || '');
          return Number.isFinite(v) ? v : null;
        }} catch (_) {{
          return null;
        }}
      }}
      function applyEntryVisuals(el, entry) {{
        if (!el || !entry || typeof entry !== 'object') return;
        if (entry.hidden === true) el.classList.add('hidden-field');
        else el.classList.remove('hidden-field');
        if (entry.wrap === true) {{
          el.classList.add('wrap-field');
          if (typeof entry.wrap_max_px === 'number' && Number.isFinite(entry.wrap_max_px)) {{
            el.style.maxWidth = `${{entry.wrap_max_px}}px`;
          }}
        }} else {{
          el.classList.remove('wrap-field');
          el.style.maxWidth = '';
        }}
        if (typeof entry.w === 'number' && Number.isFinite(entry.w) && entry.w > 0) {{
          el.style.width = `${{entry.w}}px`;
        }}
        if (typeof entry.h === 'number' && Number.isFinite(entry.h) && entry.h > 0) {{
          el.style.height = `${{entry.h}}px`;
        }}
        if (typeof entry.font_px === 'number' && Number.isFinite(entry.font_px) && !isImg(el)) {{
          el.style.fontSize = `${{entry.font_px}}px`;
        }}
        if (typeof entry.font_family === 'string' && entry.font_family.trim() && !isImg(el)) {{
          el.style.fontFamily = entry.font_family;
        }}
        if (typeof entry.font_weight === 'string' && entry.font_weight.trim() && !isImg(el)) {{
          el.style.fontWeight = entry.font_weight;
        }}
        if (typeof entry.font_style === 'string' && entry.font_style.trim() && !isImg(el)) {{
          el.style.fontStyle = entry.font_style;
        }}
        if (typeof entry.color === 'string' && entry.color.trim() && !isImg(el)) {{
          el.style.color = entry.color;
        }} else if (typeof entry.color === 'string' && entry.color === '' && !isImg(el)) {{
          el.style.color = '';
        }}
        if (typeof entry.text_decoration === 'string' && entry.text_decoration.trim() && !isImg(el)) {{
          el.style.textDecoration = entry.text_decoration;
        }} else if (typeof entry.text_decoration === 'string' && entry.text_decoration === '' && !isImg(el)) {{
          el.style.textDecoration = '';
        }}
      }}
      function applyEntryContent(el, entry) {{
        if (!el || !entry || typeof entry !== 'object' || isImg(el)) return;
        if (typeof entry.html === 'string' && entry.html.length) {{
          el.innerHTML = entry.html;
        }}
      }}
      function getActiveRangeWithin(el) {{
        try {{
          const sel = window.getSelection();
          if (!sel || sel.rangeCount < 1) return null;
          const r = sel.getRangeAt(0);
          if (!r || r.collapsed) return null;
          const node = r.commonAncestorContainer;
          if (!node) return null;
          if (!el.contains(node)) return null;
          return r;
        }} catch (_) {{
          return null;
        }}
      }}
      function unwrapSpan(span) {{
        if (!span || !(span instanceof HTMLElement) || !span.parentNode) return false;
        const parent = span.parentNode;
        while (span.firstChild) parent.insertBefore(span.firstChild, span);
        parent.removeChild(span);
        return true;
      }}
      function wrapRange(range, span) {{
        try {{
          const frag = range.extractContents();
          span.appendChild(frag);
          range.insertNode(span);
          const sel = window.getSelection();
          if (sel) {{
            sel.removeAllRanges();
            const r = document.createRange();
            r.selectNodeContents(span);
            sel.addRange(r);
          }}
          return true;
        }} catch (_) {{
          return false;
        }}
      }}
      function toggleSelectionHidden(el) {{
        const r = getActiveRangeWithin(el);
        const sel = window.getSelection();
        const focusNode = sel ? sel.focusNode : null;
        const focusEl = (focusNode instanceof HTMLElement) ? focusNode : (focusNode && focusNode.parentElement ? focusNode.parentElement : null);
        const existing = focusEl ? focusEl.closest('span.sub-hidden') : null;
        if (existing && el.contains(existing)) {{
          return unwrapSpan(existing);
        }}
        if (!r) return false;
        const span = document.createElement('span');
        span.className = 'sub-hidden';
        return wrapRange(r, span);
      }}
      function adjustSelectionFont(el, delta) {{
        const r = getActiveRangeWithin(el);
        const sel = window.getSelection();
        const focusNode = sel ? sel.focusNode : null;
        const focusEl = (focusNode instanceof HTMLElement) ? focusNode : (focusNode && focusNode.parentElement ? focusNode.parentElement : null);
        const existing = focusEl ? focusEl.closest('span.sub-font') : null;
        if (existing && el.contains(existing)) {{
          const cur = parseFloat(existing.style.fontSize || '') || getFontPx(existing) || getFontPx(el) || 14;
          const next = clamp(cur + delta, 6, 72);
          existing.style.fontSize = `${{next}}px`;
          return true;
        }}
        if (!r) return false;
        const base = getFontPx(focusEl || el) || getFontPx(el) || 14;
        const next = clamp(base + delta, 6, 72);
        const span = document.createElement('span');
        span.className = 'sub-font';
        span.style.fontSize = `${{next}}px`;
        return wrapRange(r, span);
      }}

      async function fetchJsonWithTimeout(url, options, timeoutMs) {{
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), Math.max(250, timeoutMs || 1200));
        try {{
          const res = await fetch(url, {{ ...(options || {{}}), signal: ctrl.signal }});
          if (!res.ok) return null;
          return await res.json();
        }} catch (_) {{
          return null;
        }} finally {{
          clearTimeout(t);
        }}
      }}
      async function postJsonWithTimeout(url, payload, timeoutMs) {{
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), Math.max(250, timeoutMs || 1200));
        try {{
          const res = await fetch(url, {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify(payload || {{}}),
            signal: ctrl.signal,
          }});
          return !!(res && res.ok);
        }} catch (_) {{
          return false;
        }} finally {{
          clearTimeout(t);
        }}
      }}
      async function loadFromBackend() {{
        await initQtBridge();
        if (qtBridge && typeof qtBridge.load_positions === 'function') {{
          const fromFile = await new Promise((resolve) => {{
            try {{
              qtBridge.load_positions((txt) => {{
                const obj = safeParseJson(txt || '');
                if (!obj || typeof obj !== 'object') return resolve(null);
                const v = obj.version;
                const els = obj.elements;
                if (v !== 2 || !els || typeof els !== 'object') return resolve(null);
                resolve(obj);
              }});
            }} catch (_) {{
              resolve(null);
            }}
          }});
          return fromFile;
        }}
        for (const base of API_BASES) {{
          const url = `${{base}}${{API_PATH}}`;
          const data = await fetchJsonWithTimeout(url, {{ method: 'GET' }}, 1200);
          if (!data || typeof data !== 'object') continue;
          const positions = data.positions;
          if (!positions || typeof positions !== 'object') continue;
          if (positions.version !== 2 || typeof positions.elements !== 'object') continue;
          return positions;
        }}
        return null;
      }}
      function sleep(ms) {{ return new Promise((resolve) => setTimeout(resolve, Math.max(0, ms || 0))); }}

      function clearSelectedClass() {{
        try {{
          const list = document.querySelectorAll('.draggable.selected');
          for (let i = 0; i < list.length; i++) {{
            try {{ list[i].classList.remove('selected'); }} catch (_) {{}}
          }}
        }} catch (_) {{}}
      }}

      function setSelected(nextEl) {{
        const prev = (typeof selected !== 'undefined') ? selected : null;
        const el = (nextEl && nextEl instanceof Element) ? nextEl : null;
        if (prev && prev !== el && prev instanceof Element) {{
          try {{ prev.classList.remove('selected'); }} catch (_) {{}}
        }}
        if (!el) {{
          selected = null;
          // Clear any leftover resize handles when selection is dropped
          try {{ clearResizeHandles(); }} catch (_) {{}}
          return;
        }}
        try {{ el.classList.add('selected'); }} catch (_) {{}}
        selected = el;
      }}
      async function loadFromBackendWithRetry(maxAttempts, baseDelayMs) {{
        await initQtBridge();
        if (qtBridge && typeof qtBridge.load_positions === 'function') {{
          return await loadFromBackend();
        }}
        const attempts = Math.max(1, Number(maxAttempts || 1));
        let delay = Math.max(120, Number(baseDelayMs || 140));
        for (let i = 0; i < attempts; i++) {{
          const positions = await loadFromBackend();
          if (positions) return positions;
          await sleep(delay);
          delay = Math.min(600, Math.floor(delay * 1.25));
        }}
        return null;
      }}
      async function saveToBackend(positions) {{
        await initQtBridge();
        if (qtBridge && typeof qtBridge.save_positions === 'function') {{
          const okFile = await new Promise((resolve) => {{
            try {{
              qtBridge.save_positions(JSON.stringify(positions || {{}}), (ok) => resolve(!!ok));
            }} catch (_) {{
              resolve(false);
            }}
          }});
          return okFile;
        }}
        for (const base of API_BASES) {{
          const url = `${{base}}${{API_PATH}}`;
          const ok = await postJsonWithTimeout(url, {{ positions: positions }}, 1200);
          if (ok) return true;
        }}
        return false;
      }}

      function coerceNumber(n) {{
        const x = typeof n === 'number' ? n : Number(n);
        return Number.isFinite(x) ? x : null;
      }}
      function validateAndNormalizeEntry(entry, pageRect, elRect) {{
        if (!entry || typeof entry !== 'object') return null;
        const x = coerceNumber(entry.x);
        const y = coerceNumber(entry.y);
        const base_w = coerceNumber(entry.base_w);
        const base_h = coerceNumber(entry.base_h);
        const xr = coerceNumber(entry.xr);
        const yr = coerceNumber(entry.yr);

        let finalX = x;
        let finalY = y;

        if (finalX === null || finalY === null) {{
          if (xr === null || yr === null) return null;
          finalX = xr * pageRect.width;
          finalY = yr * pageRect.height;
        }} else if (base_w !== null && base_h !== null && (Math.abs(base_w - pageRect.width) > 1 || Math.abs(base_h - pageRect.height) > 1)) {{
          const safeBaseW = base_w || pageRect.width;
          const safeBaseH = base_h || pageRect.height;
          finalX = (finalX / safeBaseW) * pageRect.width;
          finalY = (finalY / safeBaseH) * pageRect.height;
        }}

        finalX = clamp(finalX, 0, Math.max(0, pageRect.width - elRect.width));
        finalY = clamp(finalY, 0, Math.max(0, pageRect.height - elRect.height));

        return {{ x: finalX, y: finalY }};
      }}

      function applyDefaultsIfMissing(el, pageRect) {{
        const left = (el.getAttribute('data-default-left') || '').trim();
        const top = (el.getAttribute('data-default-top') || '').trim();
        const dw = (el.getAttribute('data-default-width') || '').trim();
        const dh = (el.getAttribute('data-default-height') || '').trim();
        if (!left || !top) return;
        const tmp = document.createElement('div');
        tmp.style.position = 'absolute';
        tmp.style.left = left;
        tmp.style.top = top;
        tmp.style.width = dw || '0px';
        tmp.style.height = dh || '0px';
        page.appendChild(tmp);
        const r = tmp.getBoundingClientRect();
        tmp.remove();
        const s = pageRect && pageRect.scale ? pageRect.scale : 1;
        el.style.left = `${{(r.left - pageRect.left) / s}}px`;
        el.style.top = `${{(r.top - pageRect.top) / s}}px`;
        if (dw) {{
          try {{
            const tmpW = document.createElement('div');
            tmpW.style.position = 'absolute';
            tmpW.style.visibility = 'hidden';
            tmpW.style.pointerEvents = 'none';
            tmpW.style.width = dw;
            tmpW.style.height = '1px';
            page.appendChild(tmpW);
            const rw = tmpW.getBoundingClientRect();
            tmpW.remove();
            if (rw.width > 0) el.style.width = `${{rw.width / s}}px`;
          }} catch (_) {{}}
        }} else {{
          el.style.width = '';
        }}
        if (dh) {{
          try {{
            const tmpH = document.createElement('div');
            tmpH.style.position = 'absolute';
            tmpH.style.visibility = 'hidden';
            tmpH.style.pointerEvents = 'none';
            tmpH.style.height = dh;
            tmpH.style.width = '1px';
            page.appendChild(tmpH);
            const rh = tmpH.getBoundingClientRect();
            tmpH.remove();
            if (rh.height > 0) el.style.height = `${{rh.height / s}}px`;
          }} catch (_) {{}}
        }} else {{
          el.style.height = '';
        }}
      }}

      function applyAllPositions() {{
        const doc = readSaved();
        const pageRect = getPageRect();
        const els = Array.from(document.querySelectorAll('[data-pos-key]'));
        els.forEach((el) => applyDefaultsIfMissing(el, pageRect));
        const refreshPageRect = getPageRect();
        els.forEach((el) => {{
          const key = (el.getAttribute('data-pos-key') || '').trim();
          if (!key) return;
          const entry = doc.elements[key];
          if (!entry) return;
          applyEntryContent(el, entry);
          const elRect = el.getBoundingClientRect();
          const s = refreshPageRect && refreshPageRect.scale ? refreshPageRect.scale : 1;
          const normalized = validateAndNormalizeEntry(entry, refreshPageRect, {{ width: elRect.width / s, height: elRect.height / s }});
          if (!normalized) return;
          el.style.left = `${{normalized.x}}px`;
          el.style.top = `${{normalized.y}}px`;
          applyEntryVisuals(el, entry);
        }});
      }}

      function updateFitScale() {{
        if (!shell) return;
        const baseW = page.offsetWidth || 1;
        const baseH = page.offsetHeight || 1;
        const availW = Math.max(1, window.innerWidth - 24);
        const scale = Math.min(availW / baseW, 1);
        shell.setAttribute('data-scale', String(scale));
        shell.style.width = `${{Math.floor(baseW * scale)}}px`;
        shell.style.height = `${{Math.floor(baseH * scale)}}px`;
        page.style.transform = `scale(${{scale}})`;
      }}

      let userTouched = false;
      (function initFast() {{
        try {{
          const seed = Array.from(document.querySelectorAll('[data-pos-key]'));
          for (const el of seed) {{
            if (!(el instanceof HTMLElement)) continue;
            if (!el.dataset.originalHtml) el.dataset.originalHtml = el.innerHTML || '';
          }}
        }} catch (_) {{}}
        applyAllPositions();
        updateFitScale();
        requestAnimationFrame(() => {{
          try {{
            const wrap = document.querySelector('.page-wrap');
            const pageRect = getPageRect();
            const els = Array.from(document.querySelectorAll('.draggable[data-pos-key]'));
            let minY = null;
            for (const el of els) {{
              const rel = getRelPx(el, pageRect);
              if (!Number.isFinite(rel.y)) continue;
              if (minY === null || rel.y < minY) minY = rel.y;
            }}
            const target = Math.max(0, Math.floor((minY || 0) - 24));
            if (wrap && 'scrollTop' in wrap) {{
              wrap.scrollTop = target;
            }} else {{
              window.scrollTo({{ top: target, left: 0, behavior: 'instant' }});
            }}
          }} catch (_) {{}}
        }});

        (async function syncFromBackendLater() {{
          const localDoc = readSaved();
          const backend = await loadFromBackendWithRetry(18, 140);
          if (!backend || userTouched) return;
          const localUpdated = Number(localDoc.updated_at || 0);
          const backendUpdated = Number(backend.updated_at || 0);
          const localCount = localDoc && localDoc.elements ? Object.keys(localDoc.elements).length : 0;
          const backendCount = backend && backend.elements ? Object.keys(backend.elements).length : 0;
          if (backendCount > 0 && (localCount === 0 || backendUpdated >= localUpdated)) {{
            try {{
              // Merge backend into local while preserving LOCAL DELETIONS: any key missing
              // from a previously-modified local doc stays deleted.
              const localKeys = (localDoc && localDoc.elements && typeof localDoc.elements === 'object')
                ? Object.keys(localDoc.elements)
                : [];
              const isFreshLocal = localUpdated === 0 || localCount === 0;
              const mergedElements = {{}};
              const be = (backend && backend.elements && typeof backend.elements === 'object') ? backend.elements : {{}};
              const le = (localDoc && localDoc.elements && typeof localDoc.elements === 'object') ? localDoc.elements : {{}};
              if (isFreshLocal) {{
                // No local history yet -> trust backend completely
                for (const k of Object.keys(be)) mergedElements[k] = be[k];
              }} else {{
                // Import backend keys only if they were NOT explicitly removed from local
                for (const k of Object.keys(be)) {{
                  if (k in le) {{
                    // Prefer the newer entry
                    const leT = Number(le[k] && le[k].updated_at ? le[k].updated_at : 0);
                    const beT = Number(be[k] && be[k].updated_at ? be[k].updated_at : 0);
                    mergedElements[k] = (beT >= leT) ? be[k] : le[k];
                  }}
                  // else: k is NOT in local doc → user deleted it locally → DON'T import, keep deleted
                }}
                // Also keep any keys that only exist in local (newly-created logos the backend hadn't seen yet)
                for (const k of Object.keys(le)) {{
                  if (!(k in mergedElements)) mergedElements[k] = le[k];
                }}
              }}
              const merged = {{
                version: 2,
                updated_at: Math.max(backendUpdated, localUpdated),
                elements: mergedElements,
              }};
              writeSaved(merged);
              applyAllPositions();
              // After applyAllPositions + sync, re-run restoreDynamicCustomLogos in case
              // backend had custom_logo_* entries local DOM was missing (server-pushed logo)
              try {{
                const rdcl = window.__restoreDynamicCustomLogos;
                if (typeof rdcl === 'function') rdcl();
              }} catch (_) {{}}
              updateFitScale();
            }} catch (_) {{}}
          }}
        }})();
      }})();

      let raf = 0;
      let drag = null;
      let selected = null;

      function showHud(el) {{
        const pageRect = getPageRect();
        const rel = getRelPx(el, pageRect);
        const key = el.getAttribute('data-pos-key') || '';
        const fontPx = getFontPx(el);
        const hidden = el.classList.contains('hidden-field');
        const fontPart = (fontPx !== null && !isImg(el)) ? `, font ${{Math.round(fontPx)}}px` : '';
        const hiddenPart = hidden ? ' (hidden)' : '';
        const sizePart = (typeof rel.w === 'number' && typeof rel.h === 'number') ? `, ${{Math.round(rel.w)}}×${{Math.round(rel.h)}}px` : '';
        hud.textContent = `${{key}}: x ${{Math.round(rel.x)}}px, y ${{Math.round(rel.y)}}px${{sizePart}}${{fontPart}}${{hiddenPart}} · Drag to move · Drag corner handles to resize · [Del to remove, +/= bigger, - smaller]`;
        hud.style.display = 'block';
      }}
      function hideHud() {{ hud.style.display = 'none'; }}

      function persistEntry(el, extras) {{
        userTouched = true;
        const key = (el.getAttribute('data-pos-key') || '').trim();
        if (!key) return;
        const pageRect = getPageRect();
        const rel = getRelPx(el, pageRect);
        const doc = readSaved();
        doc.version = 2;
        doc.updated_at = nowMs();
        doc.elements = doc.elements && typeof doc.elements === 'object' ? doc.elements : {{}};
        const prev = (doc.elements[key] && typeof doc.elements[key] === 'object') ? doc.elements[key] : {{}};
        let html = null;
        let font_family = null;
        let font_weight = null;
        let font_style = null;
        let color = null;
        let text_decoration = null;
        if (!isImg(el)) {{
          try {{
            const cur = el.innerHTML || '';
            const orig = el.dataset.originalHtml || '';
            const hasRich = cur.indexOf('sub-hidden') >= 0 || cur.indexOf('sub-font') >= 0 || cur.indexOf('sub-bold') >= 0 || cur.indexOf('sub-italic') >= 0;
            if (hasRich || cur !== orig) html = cur;
          }} catch (_) {{}}
          try {{
            const cs = getComputedStyle(el);
            font_family = cs && cs.fontFamily ? String(cs.fontFamily) : null;
            font_weight = cs && cs.fontWeight ? String(cs.fontWeight) : null;
            font_style = cs && cs.fontStyle ? String(cs.fontStyle) : null;
            const curColor = cs && cs.color ? String(cs.color) : '';
            if (curColor && curColor !== 'rgb(0, 0, 0)' && curColor.toLowerCase() !== '#000000' && curColor.toLowerCase() !== 'black') {{
              color = curColor;
            }}
            const curDeco = cs && cs.textDecoration ? String(cs.textDecoration) : '';
            const decoLine = (curDeco || '').trim().split(/\\s+/)[0] || '';
            if (decoLine && decoLine !== 'none') {{
              text_decoration = curDeco;
            }}
          }} catch (_) {{}}
        }}
        doc.elements[key] = {{
          ...prev,
          x: rel.x,
          y: rel.y,
          xr: pageRect.width ? rel.x / pageRect.width : 0,
          yr: pageRect.height ? rel.y / pageRect.height : 0,
          base_w: pageRect.width,
          base_h: pageRect.height,
          updated_at: nowMs(),
          ...(html !== null ? {{ html: html }} : {{}}),
          ...(font_family ? {{ font_family: font_family }} : {{}}),
          ...(font_weight ? {{ font_weight: font_weight }} : {{}}),
          ...(font_style ? {{ font_style: font_style }} : {{}}),
          ...(color ? {{ color: color }} : {{}}),
          ...(text_decoration ? {{ text_decoration: text_decoration }} : {{}}),
          ...((typeof rel.w === 'number' && Number.isFinite(rel.w) && rel.w > 0) ? {{ w: rel.w }} : {{}}),
          ...((typeof rel.h === 'number' && Number.isFinite(rel.h) && rel.h > 0) ? {{ h: rel.h }} : {{}}),
          ...(extras || {{}}),
        }};
        writeSaved(doc);
        saveToBackend(doc).catch(() => {{}});
      }}

      function startDragPointer(ev, el) {{
        if (!ev.isPrimary) return;
        selected = el;
        const pageRect = getPageRect();
        const rel = getRelPx(el, pageRect);
        drag = {{
          el,
          pointerId: ev.pointerId,
          startClientX: ev.clientX,
          startClientY: ev.clientY,
          startX: rel.x,
          startY: rel.y,
          pageW: pageRect.width,
          pageH: pageRect.height,
          elW: rel.w,
          elH: rel.h,
          scale: pageRect.scale || 1,
        }};
        el.classList.add('dragging');
        showHud(el);
        try {{ el.setPointerCapture(ev.pointerId); }} catch (_) {{}}
      }}

      function moveDragPointer(ev) {{
        if (!drag || ev.pointerId !== drag.pointerId) return;
        const s = drag.scale || 1;
        const dx = (ev.clientX - drag.startClientX) / s;
        const dy = (ev.clientY - drag.startClientY) / s;
        const rawX = drag.startX + dx;
        const rawY = drag.startY + dy;
        const x = clamp(rawX, 0, Math.max(0, drag.pageW - drag.elW));
        const y = clamp(rawY, 0, Math.max(0, drag.pageH - drag.elH));
        drag.nextX = x;
        drag.nextY = y;
        if (!raf) {{
          raf = requestAnimationFrame(() => {{
            raf = 0;
            if (!drag) return;
            drag.el.style.left = `${{drag.nextX}}px`;
            drag.el.style.top = `${{drag.nextY}}px`;
            showHud(drag.el);
          }});
        }}
      }}

      function persistPosition(el) {{ persistEntry(el, null); }}

      function endDragPointer(ev) {{
        if (!drag || (ev && ev.pointerId !== drag.pointerId)) return;
        const el = drag.el;
        el.classList.remove('dragging');
        persistPosition(el);
        drag = null;
      }}

      page.addEventListener('pointerdown', (ev) => {{
        const target = ev.target;
        if (!(target instanceof Element)) return;
        const el = target.closest('.draggable[data-pos-key]');
        if (!el) return;
        setSelected(el);
        if (el.classList.contains('edit-mode') && !isImg(el)) return;
        startDragPointer(ev, el);
        ev.preventDefault();
      }}, {{ passive: false }});

      page.addEventListener('pointermove', (ev) => {{
        moveDragPointer(ev);
        if (drag) ev.preventDefault();
      }}, {{ passive: false }});

      page.addEventListener('pointerup', (ev) => {{ endDragPointer(ev); }});
      page.addEventListener('pointercancel', (ev) => {{ endDragPointer(ev); }});

      document.addEventListener('dblclick', (ev) => {{
        const target = ev.target;
        if (!(target instanceof Element)) return;
        const el = target.closest('.draggable[data-pos-key]');
        if (!el) return;
        setSelected(el);
        const key = el.getAttribute('data-pos-key') || '';
        const pageRect = getPageRect();
        applyDefaultsIfMissing(el, pageRect);
        // Full factory-style reset (mirrors the toolbar Reset button)
        try {{
          el.style.color = '';
          el.classList.remove('hidden-field');
          el.classList.remove('wrap-field');
          el.style.maxWidth = '';
          el.classList.remove('edit-mode');
          if (typeof el.contentEditable !== 'undefined') el.contentEditable = 'false';
          if (el.dataset && el.dataset.originalHtml) {{
            el.innerHTML = el.dataset.originalHtml;
          }}
        }} catch (_) {{}}
        if (!isImg(el)) {{
          try {{
            el.style.fontSize = '';
            el.style.fontFamily = '';
            el.style.fontWeight = '';
            el.style.fontStyle = '';
            el.style.textDecoration = '';
          }} catch (_) {{}}
        }}
        if (key) {{
          const doc = readSaved();
          if (doc.elements && typeof doc.elements === 'object') delete doc.elements[key];
          doc.updated_at = nowMs();
          writeSaved(doc);
          saveToBackend(doc).catch(() => {{}});
        }}
        syncToolbarFromSelected();
        showHud(el);
        ev.preventDefault();
      }});

      document.addEventListener('keydown', (ev) => {{
        if (selected && (ev.key === 'b' || ev.key === 'B' || ev.key === 'i' || ev.key === 'I' || ev.key === 'f' || ev.key === 'F' || ev.key === 'u' || ev.key === 'U')) {{
          const el = selected;
          const key = (el.getAttribute('data-pos-key') || '').trim();
          if (!key || isImg(el)) return;
          const doc = readSaved();
          const prev = (doc.elements && doc.elements[key] && typeof doc.elements[key] === 'object') ? doc.elements[key] : {{}};
          if (ev.key === 'b' || ev.key === 'B') {{
            const cur = String(prev.font_weight || getComputedStyle(el).fontWeight || '');
            const next = (cur === '700' || cur === '800' || cur === '900' || cur.toLowerCase() === 'bold') ? '400' : '700';
            el.style.fontWeight = next;
            persistEntry(el, {{ font_weight: next }});
            syncToolbarFromSelected();
            showHud(el);
            ev.preventDefault();
            return;
          }}
          if (ev.key === 'i' || ev.key === 'I') {{
            const cur = String(prev.font_style || getComputedStyle(el).fontStyle || 'normal');
            const next = cur.toLowerCase() === 'italic' ? 'normal' : 'italic';
            el.style.fontStyle = next;
            persistEntry(el, {{ font_style: next }});
            syncToolbarFromSelected();
            showHud(el);
            ev.preventDefault();
            return;
          }}
          if (ev.key === 'u' || ev.key === 'U') {{
            const cur = String(prev.text_decoration || getComputedStyle(el).textDecoration || 'none');
            const firstPart = (cur || '').trim().split(/\\s+/)[0] || 'none';
            const isUnderline = firstPart === 'underline';
            const next = isUnderline ? 'none' : 'underline';
            el.style.textDecoration = next;
            persistEntry(el, {{ text_decoration: next }});
            syncToolbarFromSelected();
            showHud(el);
            ev.preventDefault();
            return;
          }}
          if (ev.key === 'f' || ev.key === 'F') {{
            const fonts = ['Arial, sans-serif', 'Calibri, Arial, sans-serif', 'Times New Roman, serif', 'Consolas, \"Courier New\", monospace'];
            const cur = String(prev.font_family || getComputedStyle(el).fontFamily || '');
            const idx = Math.max(0, fonts.findIndex((x) => cur.toLowerCase().indexOf(x.split(',')[0].toLowerCase()) >= 0));
            const next = fonts[(idx + 1) % fonts.length];
            el.style.fontFamily = next;
            persistEntry(el, {{ font_family: next }});
            syncToolbarFromSelected();
            showHud(el);
            ev.preventDefault();
            return;
          }}
        }}
        if (selected && ev.key === 'F2' && !isImg(selected)) {{
          const el = selected;
          const isEditing = el.classList.contains('edit-mode');
          if (isEditing) {{
            el.classList.remove('edit-mode');
            el.contentEditable = 'false';
            persistEntry(el, null);
          }} else {{
            el.classList.add('edit-mode');
            el.contentEditable = 'true';
            el.setAttribute('spellcheck', 'false');
            try {{
              const r = document.createRange();
              r.selectNodeContents(el);
              r.collapse(false);
              const sel = window.getSelection();
              if (sel) {{
                sel.removeAllRanges();
                sel.addRange(r);
              }}
            }} catch (_) {{}}
          }}
          showHud(el);
          ev.preventDefault();
          return;
        }}
        if (selected && (ev.key === 'w' || ev.key === 'W')) {{
          const el = selected;
          const key = (el.getAttribute('data-pos-key') || '').trim();
          if (!key) return;
          const doc = readSaved();
          const prev = (doc.elements && doc.elements[key] && typeof doc.elements[key] === 'object') ? doc.elements[key] : {{}};
          const nextWrap = !(prev.wrap === true);
          if (nextWrap) el.classList.add('wrap-field');
          else el.classList.remove('wrap-field');
          persistEntry(el, {{ wrap: nextWrap, wrap_max_px: (typeof prev.wrap_max_px === 'number' && Number.isFinite(prev.wrap_max_px)) ? prev.wrap_max_px : 280 }});
          showHud(el);
          ev.preventDefault();
          return;
        }}
        if (selected && (ev.key === '+' || ev.key === '=' || ev.key === '-' || ev.key === '_' || ev.key === 'h' || ev.key === 'H')) {{
          const el = selected;
          const key = (el.getAttribute('data-pos-key') || '').trim();
          if (!key) return;
          const doc = readSaved();
          const prev = (doc.elements && doc.elements[key] && typeof doc.elements[key] === 'object') ? doc.elements[key] : {{}};
          if (ev.key === 'h' || ev.key === 'H') {{
            if (el.classList.contains('edit-mode') && (getActiveRangeWithin(el) || ev.ctrlKey) && toggleSelectionHidden(el)) {{
              persistEntry(el, null);
              showHud(el);
              ev.preventDefault();
              return;
            }}
            const nextHidden = !(prev.hidden === true);
            if (nextHidden) el.classList.add('hidden-field');
            else el.classList.remove('hidden-field');
            persistEntry(el, {{ hidden: nextHidden }});
            showHud(el);
            ev.preventDefault();
            return;
          }}
          if (!isImg(el)) {{
            const delta = (ev.key === '-' || ev.key === '_') ? -1 : 1;
            if (el.classList.contains('edit-mode') && adjustSelectionFont(el, delta)) {{
              persistEntry(el, null);
              showHud(el);
              ev.preventDefault();
              return;
            }}
            const current = (typeof prev.font_px === 'number' && Number.isFinite(prev.font_px)) ? prev.font_px : (getFontPx(el) || 14);
            const next = clamp(current + delta, 6, 48);
            el.style.fontSize = `${{next}}px`;
            persistEntry(el, {{ font_px: next }});
            showHud(el);
            ev.preventDefault();
            return;
          }}
        }}
        if (ev.key === 'Escape') {{
          hideHud();
          if (selected && selected.classList && selected.classList.contains('edit-mode') && !isImg(selected)) {{
            selected.classList.remove('edit-mode');
            selected.contentEditable = 'false';
          }}
          setSelected(null);
          if (drag) endDragPointer();
        }}
      }});

      document.addEventListener('click', (ev) => {{
        const target = ev.target;
        if (!(target instanceof Element)) return;
        const hit = target.closest('.draggable[data-pos-key]');
        if (hit) {{
          setSelected(hit);
          showHud(hit);
          syncToolbarFromSelected();
          return;
        }}
        // Clicked empty area: drop selection → hides outline AND resize handles
        hideHud();
        setSelected(null);
        syncToolbarFromSelected();
      }});

      // -------- Styling Toolbar wiring --------
      const toolbar = document.getElementById('styleToolbar');
      const stTarget = document.getElementById('stTarget');
      const stFontSize = document.getElementById('stFontSize');
      const stFontSizeVal = document.getElementById('stFontSizeVal');
      const stFontFamily = document.getElementById('stFontFamily');
      const stBold = document.getElementById('stBold');
      const stItalic = document.getElementById('stItalic');
      const stUnderline = document.getElementById('stUnderline');
      const stColor = document.getElementById('stColor');
      const stResetColor = document.getElementById('stResetColor');
      const stHide = document.getElementById('stHide');
      const stWrap = document.getElementById('stWrap');
      const stEdit = document.getElementById('stEdit');
      const stReset = document.getElementById('stReset');

      function rgbToHex(rgbStr) {{
        try {{
          const s = String(rgbStr || '').trim();
          if (s.startsWith('#')) return s.length === 4 ? s.split('').map((c,i) => i === 0 ? c : c+c).join('') : s;
          const m = s.match(/rgba?\\(([^)]+)\\)/i);
          if (!m) return '#000000';
          const parts = m[1].split(',').map(p => parseInt((p || '').trim(), 10));
          const [r=0, g=0, b=0] = parts;
          const toHex = (n) => clamp(n|0, 0, 255).toString(16).padStart(2, '0');
          return `#${{toHex(r)}}${{toHex(g)}}${{toHex(b)}}`;
        }} catch (_) {{
          return '#000000';
        }}
      }}

      function syncToolbarFromSelected() {{
        if (!toolbar) return;
        const el = selected;
        if (!el || !(el instanceof HTMLElement) || isImg(el)) {{
          toolbar.style.display = 'none';
          if (stTarget) stTarget.textContent = '—';
          return;
        }}
        toolbar.style.display = 'flex';
        const key = (el.getAttribute('data-pos-key') || '').trim();
        if (stTarget) stTarget.textContent = key || 'field';
        const doc = readSaved();
        const prev = (doc.elements && doc.elements[key] && typeof doc.elements[key] === 'object') ? doc.elements[key] : {{}};
        const cs = getComputedStyle(el);
        // Font size
        const fontPx = (typeof prev.font_px === 'number' && Number.isFinite(prev.font_px)) ? prev.font_px : getFontPx(el);
        if (stFontSize) {{
          const rounded = Math.round(fontPx || 11);
          stFontSize.value = String(clamp(rounded, 6, 48));
          if (stFontSizeVal) stFontSizeVal.textContent = `${{rounded}}px`;
        }}
        // Font family
        if (stFontFamily) {{
          const curFam = String(prev.font_family || (cs && cs.fontFamily) || 'Arial, sans-serif').toLowerCase();
          let matchIdx = 0;
          for (let i = 0; i < stFontFamily.options.length; i++) {{
            const v = String(stFontFamily.options[i].value || '').toLowerCase().split(',')[0].trim();
            if (v && curFam.indexOf(v) >= 0) {{ matchIdx = i; break; }}
          }}
          stFontFamily.selectedIndex = matchIdx;
        }}
        // Bold
        if (stBold) {{
          const fw = String(prev.font_weight || (cs && cs.fontWeight) || '400').toLowerCase();
          const isBold = fw === '700' || fw === '800' || fw === '900' || fw === 'bold';
          stBold.classList.toggle('active', isBold);
        }}
        // Italic
        if (stItalic) {{
          const fs = String(prev.font_style || (cs && cs.fontStyle) || 'normal').toLowerCase();
          stItalic.classList.toggle('active', fs === 'italic' || fs === 'oblique');
        }}
        // Underline
        if (stUnderline) {{
          const td = String(prev.text_decoration || (cs && cs.textDecoration) || 'none').trim();
          const first = (td.split(/\\s+/)[0] || 'none').toLowerCase();
          stUnderline.classList.toggle('active', first === 'underline');
        }}
        // Color
        if (stColor) {{
          const cc = typeof prev.color === 'string' && prev.color ? prev.color : ((cs && cs.color) || '#000000');
          stColor.value = rgbToHex(cc);
        }}
        // Hide/Show button label
        if (stHide) {{
          const hidden = el.classList.contains('hidden-field') || prev.hidden === true;
          stHide.textContent = hidden ? 'Show' : 'Hide';
          stHide.classList.toggle('active', hidden);
        }}
        // Wrap button
        if (stWrap) {{
          const wrapped = el.classList.contains('wrap-field') || prev.wrap === true;
          stWrap.classList.toggle('active', wrapped);
        }}
        // Edit button
        if (stEdit) {{
          const editing = el.classList.contains('edit-mode');
          stEdit.classList.toggle('active', editing);
          stEdit.textContent = editing ? 'Save' : 'Edit';
        }}
      }}

      if (toolbar) {{
        // Font size slider
        stFontSize && stFontSize.addEventListener('input', (e) => {{
          if (!selected || isImg(selected)) return;
          const px = clamp(parseInt(e.target.value || '11', 10), 6, 48);
          selected.style.fontSize = `${{px}}px`;
          if (stFontSizeVal) stFontSizeVal.textContent = `${{px}}px`;
          persistEntry(selected, {{ font_px: px }});
          showHud(selected);
        }});

        // Font family
        stFontFamily && stFontFamily.addEventListener('change', (e) => {{
          if (!selected || isImg(selected)) return;
          const fam = e.target.value || 'Arial, sans-serif';
          selected.style.fontFamily = fam;
          persistEntry(selected, {{ font_family: fam }});
          showHud(selected);
        }});

        // Bold toggle
        stBold && stBold.addEventListener('click', () => {{
          if (!selected || isImg(selected)) return;
          const key = (selected.getAttribute('data-pos-key') || '').trim();
          const doc = readSaved();
          const prev = (doc.elements && doc.elements[key] && typeof doc.elements[key] === 'object') ? doc.elements[key] : {{}};
          const cur = String(prev.font_weight || getComputedStyle(selected).fontWeight || '400');
          const isBold = cur === '700' || cur === '800' || cur === '900' || cur.toLowerCase() === 'bold';
          const next = isBold ? '400' : '700';
          selected.style.fontWeight = next;
          persistEntry(selected, {{ font_weight: next }});
          syncToolbarFromSelected();
          showHud(selected);
        }});

        // Italic toggle
        stItalic && stItalic.addEventListener('click', () => {{
          if (!selected || isImg(selected)) return;
          const key = (selected.getAttribute('data-pos-key') || '').trim();
          const doc = readSaved();
          const prev = (doc.elements && doc.elements[key] && typeof doc.elements[key] === 'object') ? doc.elements[key] : {{}};
          const cur = String(prev.font_style || getComputedStyle(selected).fontStyle || 'normal');
          const next = cur.toLowerCase() === 'italic' ? 'normal' : 'italic';
          selected.style.fontStyle = next;
          persistEntry(selected, {{ font_style: next }});
          syncToolbarFromSelected();
          showHud(selected);
        }});

        // Underline toggle
        stUnderline && stUnderline.addEventListener('click', () => {{
          if (!selected || isImg(selected)) return;
          const key = (selected.getAttribute('data-pos-key') || '').trim();
          const doc = readSaved();
          const prev = (doc.elements && doc.elements[key] && typeof doc.elements[key] === 'object') ? doc.elements[key] : {{}};
          const cur = String(prev.text_decoration || getComputedStyle(selected).textDecoration || 'none');
          const first = (cur || '').trim().split(/\\s+/)[0] || 'none';
          const isUnderline = first === 'underline';
          const next = isUnderline ? 'none' : 'underline';
          selected.style.textDecoration = next;
          persistEntry(selected, {{ text_decoration: next }});
          syncToolbarFromSelected();
          showHud(selected);
        }});

        // Color picker
        stColor && stColor.addEventListener('input', (e) => {{
          if (!selected || isImg(selected)) return;
          const col = e.target.value || '#000000';
          selected.style.color = col;
          persistEntry(selected, {{ color: col }});
          showHud(selected);
        }});

        // Reset color
        stResetColor && stResetColor.addEventListener('click', () => {{
          if (!selected || isImg(selected)) return;
          selected.style.color = '';
          persistEntry(selected, {{ color: '' }});
          syncToolbarFromSelected();
          showHud(selected);
        }});

        // Hide / Show
        stHide && stHide.addEventListener('click', () => {{
          if (!selected) return;
          const key = (selected.getAttribute('data-pos-key') || '').trim();
          if (!key) return;
          const doc = readSaved();
          const prev = (doc.elements && doc.elements[key] && typeof doc.elements[key] === 'object') ? doc.elements[key] : {{}};
          const nextHidden = !(prev.hidden === true || selected.classList.contains('hidden-field'));
          if (nextHidden) selected.classList.add('hidden-field');
          else selected.classList.remove('hidden-field');
          persistEntry(selected, {{ hidden: nextHidden }});
          syncToolbarFromSelected();
          showHud(selected);
        }});

        // Word wrap toggle
        stWrap && stWrap.addEventListener('click', () => {{
          if (!selected) return;
          const key = (selected.getAttribute('data-pos-key') || '').trim();
          if (!key) return;
          const doc = readSaved();
          const prev = (doc.elements && doc.elements[key] && typeof doc.elements[key] === 'object') ? doc.elements[key] : {{}};
          const nextWrap = !(prev.wrap === true || selected.classList.contains('wrap-field'));
          if (nextWrap) {{
            selected.classList.add('wrap-field');
            if (typeof prev.wrap_max_px !== 'number' || !Number.isFinite(prev.wrap_max_px)) {{
              selected.style.maxWidth = '280px';
            }}
            persistEntry(selected, {{ wrap: true, wrap_max_px: (typeof prev.wrap_max_px === 'number' && Number.isFinite(prev.wrap_max_px)) ? prev.wrap_max_px : 280 }});
          }} else {{
            selected.classList.remove('wrap-field');
            selected.style.maxWidth = '';
            persistEntry(selected, {{ wrap: false }});
          }}
          syncToolbarFromSelected();
          showHud(selected);
        }});

        // Edit mode toggle
        stEdit && stEdit.addEventListener('click', () => {{
          if (!selected || isImg(selected)) return;
          const isEditing = selected.classList.contains('edit-mode');
          if (isEditing) {{
            selected.classList.remove('edit-mode');
            selected.contentEditable = 'false';
            persistEntry(selected, null);
          }} else {{
            selected.classList.add('edit-mode');
            selected.contentEditable = 'true';
            selected.setAttribute('spellcheck', 'false');
            try {{
              const r = document.createRange();
              r.selectNodeContents(selected);
              r.collapse(false);
              const sel = window.getSelection();
              if (sel) {{
                sel.removeAllRanges();
                sel.addRange(r);
              }}
            }} catch (_) {{}}
          }}
          syncToolbarFromSelected();
          showHud(selected);
        }});

        // Reset (remove stored entry, restore defaults, reapply visuals)
        stReset && stReset.addEventListener('click', () => {{
          if (!selected) return;
          const key = (selected.getAttribute('data-pos-key') || '').trim();
          const pageRect = getPageRect();
          applyDefaultsIfMissing(selected, pageRect);
          // Always clear universal overrides (for text fields AND logos)
          try {{
            selected.style.color = '';
            selected.classList.remove('hidden-field');
            selected.classList.remove('wrap-field');
            selected.style.maxWidth = '';
            selected.classList.remove('edit-mode');
            if (typeof selected.contentEditable !== 'undefined') selected.contentEditable = 'false';
            if (selected.dataset && selected.dataset.originalHtml) {{
              selected.innerHTML = selected.dataset.originalHtml;
            }}
          }} catch (_) {{}}
          // Text-field-only resets
          if (!isImg(selected)) {{
            selected.style.fontSize = '';
            selected.style.fontFamily = '';
            selected.style.fontWeight = '';
            selected.style.fontStyle = '';
            selected.style.textDecoration = '';
          }}
          // Logo/image wrapper size already reset by applyDefaultsIfMissing -> data-default-width/height
          if (key) {{
            const doc = readSaved();
            if (doc.elements && typeof doc.elements === 'object') delete doc.elements[key];
            doc.updated_at = nowMs();
            writeSaved(doc);
            saveToBackend(doc).catch(() => {{}});
          }}
          syncToolbarFromSelected();
          showHud(selected);
        }});

        // Stop clicks inside toolbar from being interpreted by the page handler
        toolbar.addEventListener('click', (e) => {{ e.stopPropagation(); }});
        toolbar.addEventListener('pointerdown', (e) => {{ e.stopPropagation(); }});
        // Initial sync
        try {{ syncToolbarFromSelected(); }} catch (_) {{}}
      }}
      // -------- End Styling Toolbar wiring --------

      // -------- Logo / Resize / Add-Delete wiring --------
      const stAddLogo = document.getElementById('stAddLogo');
      const stDelete = document.getElementById('stDelete');
      const stFileInput = document.getElementById('stFileInput');
      const stSize = document.getElementById('stSize');
      const stLockAspect = document.getElementById('stLockAspect');
      const HANDLE_TYPES = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];
      let resizeHandles = [];
      let resizeDrag = null;

      function clearResizeHandles() {{
        for (const h of resizeHandles) {{
          try {{ if (h.parentNode) h.parentNode.removeChild(h); }} catch (_) {{}}
        }}
        resizeHandles = [];
      }}

      function buildResizeHandles(el) {{
        clearResizeHandles();
        if (!el || !(el instanceof HTMLElement)) return;
        for (const t of HANDLE_TYPES) {{
          const h = document.createElement('div');
          h.className = `resize-handle ${{t}}`;
          h.dataset.handle = t;
          h.setAttribute('draggable', 'false');
          el.appendChild(h);
          resizeHandles.push(h);
          h.addEventListener('pointerdown', (ev) => {{
            ev.stopPropagation();
            ev.preventDefault();
            startResizeDrag(ev, el, t);
          }});
        }}
      }}

      function startResizeDrag(ev, el, handleType) {{
        if (!ev.isPrimary) return;
        const pageRect = getPageRect();
        const rel = getRelPx(el, pageRect);
        resizeDrag = {{
          el,
          handle: handleType,
          pointerId: ev.pointerId,
          startClientX: ev.clientX,
          startClientY: ev.clientY,
          startX: rel.x,
          startY: rel.y,
          startW: typeof rel.w === 'number' && rel.w > 0 ? rel.w : (el.offsetWidth || 100),
          startH: typeof rel.h === 'number' && rel.h > 0 ? rel.h : (el.offsetHeight || 80),
          scale: getFitScale(),
          lockAspect: !!(stLockAspect && stLockAspect.checked),
        }};
        if (resizeDrag.startW && resizeDrag.startH) {{
          resizeDrag.aspect = resizeDrag.startW / resizeDrag.startH;
        }} else {{
          resizeDrag.aspect = null;
        }}
        try {{ el.setPointerCapture(ev.pointerId); }} catch (_) {{}}
        try {{ document.body && document.body.setPointerCapture(ev.pointerId); }} catch (_) {{}}
        el.classList.add('dragging');
        selected = el;
      }}

      function moveResizeDrag(ev) {{
        if (!resizeDrag || ev.pointerId !== resizeDrag.pointerId) return;
        const {{ startClientX, startClientY, startX, startY, startW, startH, handle, scale, lockAspect, aspect }} = resizeDrag;
        const s = typeof scale === 'number' && scale > 0 ? scale : 1;
        const dx = (ev.clientX - startClientX) / s;
        const dy = (ev.clientY - startClientY) / s;
        let x = startX;
        let y = startY;
        let w = startW;
        let h = startH;
        if (handle.indexOf('e') >= 0) w = Math.max(10, startW + dx);
        if (handle.indexOf('s') >= 0) h = Math.max(10, startH + dy);
        if (handle.indexOf('w') >= 0) {{
          const newW = Math.max(10, startW - dx);
          x = startX + (startW - newW);
          w = newW;
        }}
        if (handle.indexOf('n') >= 0) {{
          const newH = Math.max(10, startH - dy);
          y = startY + (startH - newH);
          h = newH;
        }}
        if (lockAspect && aspect && aspect > 0) {{
          // Keep the changed-dominant axis; scale the other
          if (handle === 'e' || handle === 'w') {{
            h = Math.max(10, Math.round(w / aspect));
          }} else if (handle === 'n' || handle === 's') {{
            w = Math.max(10, Math.round(h * aspect));
          }} else {{
            // Corner: keep largest proportional
            const rw = w / startW;
            const rh = h / startH;
            const r = Math.max(rw, rh);
            w = Math.max(10, Math.round(startW * r));
            h = Math.max(10, Math.round(startH * r));
            // Adjust x/y for top-left corners too
            if (handle.indexOf('w') >= 0) x = startX + (startW - w);
            if (handle.indexOf('n') >= 0) y = startY + (startH - h);
          }}
        }}
        const el2 = resizeDrag.el;
        el2.style.left = `${{x}}px`;
        el2.style.top = `${{y}}px`;
        el2.style.width = `${{w}}px`;
        el2.style.height = `${{h}}px`;
        syncSizeSliderFromElement(el2);
        showHud(el2);
      }}

      function endResizeDrag(ev) {{
        if (!resizeDrag) return;
        if (ev && ev.pointerId !== resizeDrag.pointerId) return;
        const el2 = resizeDrag.el;
        resizeDrag = null;
        el2.classList.remove('dragging');
        persistEntry(el2, null);
        syncToolbarFromSelected();
        showHud(el2);
      }}

      document.addEventListener('pointermove', (ev) => {{
        if (resizeDrag) {{
          moveResizeDrag(ev);
          ev.preventDefault();
        }}
      }});
      document.addEventListener('pointerup', (ev) => {{ endResizeDrag(ev); }});
      document.addEventListener('pointercancel', (ev) => {{ endResizeDrag(ev); }});

      function syncSizeSliderFromElement(el) {{
        if (!stSize || !el || !(el instanceof HTMLElement)) return;
        const w = el.offsetWidth || 0;
        if (w <= 0) return;
        const minV = parseInt(stSize.min || '20', 10);
        const maxV = parseInt(stSize.max || '600', 10);
        stSize.value = String(clamp(w, minV, maxV));
      }}

      function deleteSelectedField() {{
        if (!selected || !(selected instanceof HTMLElement)) return;
        const key = (selected.getAttribute('data-pos-key') || '').trim();
        if (!key) return;
        // Guard: don't allow deleting FBR invoice #, grand total, core labels/values unless custom/logo
        const isCustom = key.indexOf('custom_logo_') === 0;
        const confirmName = selected.dataset && selected.dataset.originalHtml ? '' : (selected.textContent || '').slice(0, 40);
        const ok = confirm(`Delete selected "${{key}}" from invoice?${{confirmName ? `\\n("${{confirmName}}")` : ''}}${{isCustom ? '' : '\\n\\n⚠️ This is a built-in field — it will return on Reset or page reload.'}}`);
        if (!ok) return;
        userTouched = true;
        // Remove from DOM
        try {{ selected.parentNode && selected.parentNode.removeChild(selected); }} catch (_) {{}}
        // Remove from saved doc
        const doc = readSaved();
        let changed = false;
        if (doc.elements && typeof doc.elements === 'object' && key in doc.elements) {{
          delete doc.elements[key];
          changed = true;
        }}
        doc.version = 2;
        doc.updated_at = nowMs();
        if (changed) {{
          writeSaved(doc);
          // Persist backend twice (async fire-and-forget; retries help if first post was dropped)
          saveToBackend(doc).catch(() => {{}});
          setTimeout(() => {{ saveToBackend(readSaved()).catch(() => {{}}); }}, 350);
        }} else {{
          writeSaved(doc);
          saveToBackend(doc).catch(() => {{}});
        }}
        // Clear selected & UI
        clearResizeHandles();
        setSelected(null);
        hideHud();
        syncToolbarFromSelected();
      }}

      function addLogoFromDataUrl(dataUrl, fileName) {{
        const pageEl = document.getElementById('invoicePage');
        if (!pageEl) return;
        const doc = readSaved();
        let idx = 1;
        let newKey = `custom_logo_1`;
        const ex = (doc.elements && typeof doc.elements === 'object') ? Object.keys(doc.elements) : [];
        while (ex.indexOf(newKey) >= 0 || document.querySelector(`[data-pos-key="${{newKey}}"]`)) {{
          idx += 1;
          newKey = `custom_logo_${{idx}}`;
        }}
        const wrap = document.createElement('div');
        wrap.id = newKey;
        wrap.className = 'draggable';
        wrap.setAttribute('data-pos-key', newKey);
        wrap.setAttribute('data-default-left', '2.00in');
        wrap.setAttribute('data-default-top', '1.50in');
        wrap.setAttribute('draggable', 'false');
        wrap.style.cssText = `position:absolute; left: 2.00in; top: 1.50in; width: 140px; height: auto; background: transparent; user-select: none; -webkit-user-select: none; -webkit-user-drag: none; touch-action: none;`;
        const img = document.createElement('img');
        img.src = dataUrl;
        img.alt = fileName || newKey;
        img.setAttribute('draggable', 'false');
        img.style.cssText = `pointer-events: none; display: block; width: 100%; height: auto; max-width: 100%; user-select: none; -webkit-user-select: none;`;
        wrap.appendChild(img);
        pageEl.appendChild(wrap);
        // Store original html for reset
        wrap.dataset.originalHtml = wrap.innerHTML || '';
        // Apply defaults
        try {{ applyDefaultsIfMissing(wrap, getPageRect()); }} catch (_) {{}}
        setSelected(wrap);
        showHud(wrap);
        syncToolbarFromSelected();
        buildResizeHandles(wrap);
        // Explicitly persist with html (containing data URL) for restore
        persistEntry(wrap, {{ html: wrap.innerHTML || '' }});
      }}

      // Delete shortcut
      document.addEventListener('keydown', (ev) => {{
        if (!selected) return;
        if (ev.key === 'Delete' || ev.key === 'Backspace') {{
          // Don't fire if currently editing text in a contentEditable
          const ae = document.activeElement;
          if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA' || (ae instanceof HTMLElement && ae.isContentEditable && ae !== selected))) return;
          deleteSelectedField();
          ev.preventDefault();
        }}
      }});

      // Size slider input
      stSize && stSize.addEventListener('input', (e) => {{
        if (!selected || !(selected instanceof HTMLElement)) return;
        const newW = clamp(parseInt(e.target.value || '100', 10), 20, 600);
        const lock = !!(stLockAspect && stLockAspect.checked);
        const oldW = selected.offsetWidth || 1;
        const oldH = selected.offsetHeight || 1;
        selected.style.width = `${{newW}}px`;
        if (lock && oldW > 0 && oldH > 0) {{
          const aspect = oldW / oldH;
          const newH = Math.max(10, Math.round(newW / aspect));
          selected.style.height = `${{newH}}px`;
        }}
        persistEntry(selected, null);
        showHud(selected);
      }});

      // Lock aspect change -> recompute if possible
      stLockAspect && stLockAspect.addEventListener('change', () => {{
        if (selected && selected instanceof HTMLElement) syncSizeSliderFromElement(selected);
      }});

      // Delete button
      stDelete && stDelete.addEventListener('click', () => {{ deleteSelectedField(); }});

      // Download PDF button
      const stDownloadPdf = document.getElementById('stDownloadPdf');
      function doDownloadPdf() {{
        // 1. Prefer the Qt bridge (inside PrintPreviewDialog) -> opens native save dialog
        if (qtBridge && typeof qtBridge.download_current_page_pdf === 'function') {{
          try {{
            const r = qtBridge.download_current_page_pdf();
            if (r === true) return;
          }} catch (_) {{}}
        }}
        // 2. Otherwise fall back to browser's native print dialog (user picks "Save as PDF")
        try {{
          if (window.__pdf_download_lock) return;
          window.__pdf_download_lock = true;
          try {{
            // Temporarily hide any runtime-only UI (drag outlines, HUD, resize handles, toolbar already removed in @media print)
            window.focus();
            window.print();
          }} finally {{
            setTimeout(() => {{ window.__pdf_download_lock = false; }}, 1000);
          }}
        }} catch (exc) {{
          alert('Unable to open print dialog: ' + (exc && exc.message ? exc.message : exc));
        }}
      }}
      stDownloadPdf && stDownloadPdf.addEventListener('click', () => {{ doDownloadPdf(); }});

      // Ctrl+S / Cmd+S shortcut = download PDF (don't trigger Save-As-HTML browser feature)
      document.addEventListener('keydown', (ev) => {{
        const ctrl = (ev.ctrlKey === true) || (ev.metaKey === true);
        if (ctrl && !ev.shiftKey && !ev.altKey && (ev.key === 's' || ev.key === 'S')) {{
          ev.preventDefault();
          doDownloadPdf();
        }}
      }});

      // Add logo button -> click file input
      stAddLogo && stAddLogo.addEventListener('click', () => {{
        if (!stFileInput) return;
        try {{ stFileInput.value = ''; }} catch (_) {{}}
        stFileInput.click();
      }});

      // File input change -> read file as data URL, create logo element
      stFileInput && stFileInput.addEventListener('change', (ev) => {{
        const f = ev.target && ev.target.files && ev.target.files[0];
        if (!f) return;
        const reader = new FileReader();
        reader.onload = () => {{
          const url = String(reader.result || '');
          if (!url) return;
          addLogoFromDataUrl(url, f.name || '');
        }};
        reader.onerror = () => {{ alert('Failed to read the image file.'); }};
        reader.readAsDataURL(f);
      }});

      // Intercept selection updates: rebuild/clear resize handles & sync Size slider + Delete enabled
      (function wrapSelection() {{
        const origSync = syncToolbarFromSelected;
        syncToolbarFromSelected = function() {{
          try {{ origSync(); }} catch (_) {{}}
          const el = selected;
          if (stDelete) stDelete.disabled = !(el && el instanceof HTMLElement);
          if (el && el instanceof HTMLElement) {{
            buildResizeHandles(el);
            syncSizeSliderFromElement(el);
            if (stSize) stSize.disabled = false;
          }} else {{
            clearResizeHandles();
            if (stSize) stSize.disabled = true;
          }}
        }};
      }})();

      // Re-create any dynamically-added custom logos that exist in saved layout but missing from DOM
      function restoreDynamicCustomLogos() {{
        try {{
          const doc = readSaved();
          if (!doc || !doc.elements || typeof doc.elements !== 'object') return;
          const pageEl = document.getElementById('invoicePage');
          if (!pageEl) return;
          const keys = Object.keys(doc.elements);
          let anyAdded = false;
          for (const key of keys) {{
            if (!key || typeof key !== 'string') continue;
            if (!(key === 'honda_logo' || key === 'fbr_pos_logo' || key.indexOf('custom_logo_') === 0)) continue;
            if (document.querySelector(`[data-pos-key="${{key}}"]`)) continue; // already present
            const entry = doc.elements[key];
            if (!entry || typeof entry !== 'object') continue;
            if (key === 'honda_logo' || key === 'fbr_pos_logo') continue; // these are static HTML, skip if removed
            const innerHtml = typeof entry.html === 'string' && entry.html ? entry.html : '';
            if (!innerHtml) continue; // needs stored html to restore
            anyAdded = true;
            const wrap = document.createElement('div');
            wrap.id = key;
            wrap.className = 'draggable';
            wrap.setAttribute('data-pos-key', key);
            wrap.setAttribute('data-default-left', '2.00in');
            wrap.setAttribute('data-default-top', '1.50in');
            wrap.setAttribute('draggable', 'false');
            wrap.style.cssText = `position:absolute; left: 2.00in; top: 1.50in; width: 140px; height: auto; background: transparent; user-select: none; -webkit-user-select: none; -webkit-user-drag: none; touch-action: none;`;
            wrap.innerHTML = innerHtml;
            const images = wrap.querySelectorAll('img, svg');
            for (const im of images) {{
              if (im.tagName === 'IMG') {{
                im.setAttribute('draggable', 'false');
                im.style.cssText = `${{im.style.cssText || ''}} pointer-events: none; display: block; width: 100%; height: auto; max-width: 100%; user-select: none; -webkit-user-select: none;`;
              }} else {{
                im.setAttribute('draggable', 'false');
                im.style.cssText = `${{im.style.cssText || ''}} pointer-events: none; display: block; user-select: none; -webkit-user-select: none;`;
              }}
            }}
            pageEl.appendChild(wrap);
            wrap.dataset.originalHtml = innerHtml;
            applyDefaultsIfMissing(wrap, getPageRect());
            const pageRect2 = getPageRect();
            const elRect = wrap.getBoundingClientRect();
            const s = pageRect2 && pageRect2.scale ? pageRect2.scale : 1;
            const normalized = validateAndNormalizeEntry(entry, pageRect2, {{ width: elRect.width / s, height: elRect.height / s }});
            if (normalized) {{
              wrap.style.left = `${{normalized.x}}px`;
              wrap.style.top = `${{normalized.y}}px`;
            }}
            applyEntryVisuals(wrap, entry);
          }}
          if (anyAdded) {{
            try {{ applyAllPositions(); }} catch (_) {{}}
            try {{ updateFitScale(); }} catch (_) {{}}
          }}
        }} catch (_) {{}}
      }}
      try {{ window.__restoreDynamicCustomLogos = restoreDynamicCustomLogos; }} catch (_) {{}}
      restoreDynamicCustomLogos();

      window.addEventListener('resize', () => {{ updateFitScale(); }});
    }})();
  </script>
</body>
</html>
"""
        return html.strip()

    def render_authority_letter(self, letter_data: Dict[str, Any]) -> str:
        """Renders the HTML for an authority letter using the template."""
        try:
            template = self.jinja_env.get_template("authority_letter.html")
            data = self._get_business_info()
            data.update(letter_data)
            
            # Add metadata
            data["year"] = dt.datetime.now().year
            if isinstance(data.get("date"), dt.datetime):
                data["date"] = data["date"].strftime("%d-%m-%Y")
            
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
        customer_phone = esc(data.get("customer_phone", ""))
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
                <div class="customer-block">
                  <div class="customer-name">{customer_name}</div>
                  <div class="customer-phone"><span class="k">Phone:</span> <span class="mono">{customer_phone}</span></div>
                </div>
                <div class="copy-body">
                  <div class="row"><span class="k">Booking #</span><span class="v mono">{booking_number}</span></div>
                  <div class="row"><span class="k">Date</span><span class="v">{esc(created_at_str)}</span></div>
                  <div class="row"><span class="k">Model / Color</span><span class="v">{motorcycle_model} / {color}</span></div>
                  <div class="row"><span class="k">Total</span><span class="v">Rs. {total_price}</span></div>
                  <div class="row"><span class="k">Advance</span><span class="v">Rs. {advance_paid}</span></div>
                  <div class="row total"><span class="k">Balance</span><span class="v">Rs. {balance_amount}</span></div>
                  <div class="urdu-note">جب گاڑی کے متعلق کال آئے۔تورسید اور ایک لیٹر پٹرول ہمراہ لائیں۔شکریہ</div>
                </div>
                <div class="footer">
                  <div class="sig">
                    <div class="sig-line"></div>
                    <div class="sig-label">Signature</div>
                  </div>
                  <div class="stamp-box">STAMP</div>
                </div>
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
                margin: 0.3in 0.25in 0.25in 0.25in;
              }}
              * {{ box-sizing: border-box; }}
              body {{
                margin: 0;
                padding: 0;
                font-family: Arial, sans-serif;
                color: #111;
                font-size: 8.5pt;
                line-height: 1.12;
              }}
              .sheet {{
                width: 8in;
                height: 3in;
                margin: 0.3in auto 0 auto;
                overflow: hidden;
              }}
              .top-copies {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                column-gap: 0.08in;
                width: 8in;
                height: 3in;
              }}
              .copy-box {{
                border: 1px solid #111;
                height: 3in;
                padding: 0.07in;
                overflow: hidden;
                display: flex;
                flex-direction: column;
              }}
              .copy-title {{
                text-align: center;
                font-weight: 800;
                font-size: 9pt;
                margin-bottom: 0.03in;
                text-transform: uppercase;
              }}
              .biz-line {{
                text-align: center;
                font-size: 8pt;
                font-weight: 700;
                line-height: 1.05;
              }}
              .customer-block {{
                margin-top: 0.04in;
              }}
              .customer-name {{
                font-size: 12pt;
                font-weight: 900;
                padding: 1px 2px;
                border-bottom: 1px solid #111;
                background: #f0f0f0;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
              }}
              .customer-phone {{
                margin-top: 0.02in;
                font-size: 10pt;
                font-weight: 800;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
              }}
              .copy-body {{
                margin-top: 0.04in;
              }}
              .row {{
                display: flex;
                justify-content: space-between;
                align-items: baseline;
                gap: 6px;
                padding: 1px 0;
              }}
              .k {{ color: #222; font-weight: 700; }}
              .v {{ font-weight: 700; text-align: right; }}
              .mono {{ font-family: Consolas, "Courier New", monospace; }}
              .text-end {{ text-align: right; }}
              .total .k, .total .v {{ font-weight: 800; }}
              .urdu-note {{
                margin-top: 0.06in;
                font-size: 10pt;
                font-family: "Jameel Noori Nastaleeq", "Noori Nastaleeq", "Noto Nastaliq Urdu", "Noto Nastaliq Urdu UI", serif !important;
                font-weight: 400;
                text-align: right;
                direction: rtl;
                unicode-bidi: plaintext;
              }}
              .footer {{
                margin-top: auto;
                display: flex;
                justify-content: space-between;
                align-items: flex-end;
                gap: 0.06in;
              }}
              .sig {{
                flex: 1;
              }}
              .sig-line {{
                border-top: 1px solid #111;
                width: 100%;
                height: 0;
                margin-bottom: 2px;
              }}
              .sig-label {{
                font-size: 7.5pt;
                font-weight: 700;
              }}
              .stamp-box {{
                width: 1.05in;
                height: 0.55in;
                border: 1px solid #111;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: 800;
                font-size: 9pt;
                letter-spacing: 0.5px;
              }}
            </style>
          </head>
          <body>
            <div class="sheet">
              <div class="top-copies">
                {render_copy("Customer Copy")}
                {render_copy("Showroom Copy")}
              </div>
            </div>
          </body>
        </html>
        """
        return html

    def print_html(self, html_content: str, title: str = "Print Document"):
        """Displays a print preview dialog and handles the printing process."""
        try:
            dialog = PrintPreviewDialog(_apply_urdu_font_to_html(html_content), title)
            dialog.exec()
        except Exception as e:
            logger.error(f"Printing failed: {e}", exc_info=True)
            QMessageBox.critical(None, "Print Error", f"An error occurred while trying to print: {str(e)}")

    def print_html_direct(self, html_content: str) -> None:
        try:
            if not _WEBENGINE_AVAILABLE:
                QMessageBox.critical(None, "Print Error", "Direct printing is unavailable (PyQt6-WebEngine is not loaded). Please restart the application.")
                return
            job = _SilentPrintJob(_apply_urdu_font_to_html(html_content), on_done=lambda: setattr(self, "active_view", None))
            self.active_view = job
            job.start()
        except Exception as e:
            logger.error(f"Direct print failed: {e}", exc_info=True)
            QMessageBox.critical(None, "Print Error", f"An error occurred while trying to print: {str(e)}")

    def print_html_with_dialog(self, html_content: str, parent: Optional[QWidget] = None) -> None:
        try:
            if not _WEBENGINE_AVAILABLE:
                QMessageBox.critical(parent, "Print Error", "Printing is unavailable (PyQt6-WebEngine is not loaded). Please restart the application.")
                return
            job = _DialogPrintJob(_apply_urdu_font_to_html(html_content), parent=parent, on_done=lambda: setattr(self, "active_view", None))
            self.active_view = job
            job.start()
        except Exception as e:
            logger.error(f"Dialog print failed: {e}", exc_info=True)
            QMessageBox.critical(parent, "Print Error", f"An error occurred while trying to print: {str(e)}")

class PrintPreviewDialog(QDialog):
    """Standalone dialog for document preview and printing."""
    
    def __init__(self, html_content: str, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1000, 800)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: #f8f9fa; border-bottom: 1px solid #dee2e6;")
        toolbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)
        toolbar_layout.setSpacing(8)
        
        self.print_btn = QPushButton("🖨️ Print Now")
        self.print_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                font-weight: bold;
                padding: 4px 12px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #2980b9; }
        """)
        self.print_btn.clicked.connect(self._handle_print)

        self.download_pdf_btn = QPushButton("⬇ Download PDF")
        self.download_pdf_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                padding: 4px 12px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #1e8449; }
        """)
        self.download_pdf_btn.clicked.connect(self._handle_download_pdf)

        self.close_btn = QPushButton("Close")
        self.close_btn.setStyleSheet("""
            QPushButton {
                padding: 4px 12px;
                border: 1px solid #cbd3da;
                border-radius: 4px;
                background-color: #ffffff;
            }
            QPushButton:hover { background-color: #f0f2f4; }
        """)
        self.close_btn.clicked.connect(self.close)

        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.download_pdf_btn)
        toolbar_layout.addWidget(self.print_btn)
        toolbar_layout.addWidget(self.close_btn)
        toolbar_layout.addSpacing(8)
        
        layout.addWidget(toolbar)

        self._html_content = _apply_urdu_font_to_html(html_content)
        self.web_view = None
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView

            self.web_view = QWebEngineView()
            self._preview_base_url = QUrl("http://127.0.0.1:9000/")
            self._reporting_ready_url = QUrl("http://127.0.0.1:9000/api/print-layout/invoice")
            self._pending_preview_html = self._html_content
            self._ready_attempts_left = 40
            self._ready_retry_delay_ms = 250
            self._net = QNetworkAccessManager(self)

            try:
                from PyQt6.QtWebChannel import QWebChannel

                self._web_channel = QWebChannel(self.web_view.page())
                self._invoice_layout_bridge = _InvoiceLayoutFileBridge(self)
                self._web_channel.registerObject("invoiceLayoutBridge", self._invoice_layout_bridge)
                self._authority_layout_bridge = _AuthorityLayoutFileBridge(self)
                self._web_channel.registerObject("authorityLayoutBridge", self._authority_layout_bridge)
                self.web_view.page().setWebChannel(self._web_channel)
            except Exception as exc:
                logger.warning(f"Qt WebChannel unavailable, file-based layout persistence disabled: {exc}")

            self.web_view.setHtml(self._pending_preview_html or "", self._preview_base_url)
            layout.addWidget(self.web_view)
        except Exception as e:
            msg = QWidget()
            msg_layout = QVBoxLayout(msg)
            msg_layout.setContentsMargins(20, 20, 20, 20)
            msg_layout.setSpacing(12)

            lbl = QPushButton(f"Web preview is unavailable on this system.\nOpen in browser to print.\n\nError: {e}")
            lbl.setEnabled(False)
            msg_layout.addWidget(lbl)

            layout.addWidget(msg)

    def _wait_for_reporting_server_then_load(self) -> None:
        if not getattr(self, "_net", None):
            if self.web_view:
                self.web_view.setHtml(self._pending_preview_html or "", self._preview_base_url)
            return

        req = QNetworkRequest(self._reporting_ready_url)
        reply = self._net.get(req)
        reply.finished.connect(lambda r=reply: self._on_reporting_ready_finished(r))

    def _on_reporting_ready_finished(self, reply: QNetworkReply) -> None:
        try:
            ok = reply.error() == QNetworkReply.NetworkError.NoError
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            status_code = int(status) if status is not None else 0
        except Exception:
            ok = False
            status_code = 0
        finally:
            reply.deleteLater()

        if ok and status_code == 200:
            if self.web_view:
                self.web_view.setHtml(self._pending_preview_html or "", self._preview_base_url)
            return

        self._ready_attempts_left = int(getattr(self, "_ready_attempts_left", 0) or 0) - 1
        if self._ready_attempts_left <= 0:
            if self.web_view:
                self.web_view.setHtml(self._pending_preview_html or "", self._preview_base_url)
            return

        delay_ms = int(getattr(self, "_ready_retry_delay_ms", 250) or 250)
        QTimer.singleShot(max(100, delay_ms), self._wait_for_reporting_server_then_load)

    def _handle_print(self):
        if not self.web_view:
            QMessageBox.critical(self, "Print Error", "Preview is not available for direct printing on this system.")
            return
        self.print_btn.setEnabled(False)

        def fail(msg: str) -> None:
            self.print_btn.setEnabled(True)
            QMessageBox.critical(self, "Print Error", msg)

        try:
            page = self.web_view.page()
            page_print_to_pdf = getattr(page, "printToPdf", None)
            if not callable(page_print_to_pdf):
                fail("Printing is not supported by this QtWebEngine build. Please update PyQt6-WebEngine.")
                return

            def print_pdf_file(pdf_path: str, delete_after: bool) -> None:
                try:
                    try:
                        from PyQt6.QtPdf import QPdfDocument
                    except Exception:
                        fail("QtPdf is not available. Please install/enable the QtPdf module for direct printing.")
                        return

                    from PyQt6.QtCore import QSize
                    from PyQt6.QtGui import QPainter, QPageSize
                    from PyQt6.QtPrintSupport import QPrinter
                    if not pdf_path or not os.path.exists(pdf_path):
                        fail("Failed to generate PDF for printing.")
                        return

                    pdf = QPdfDocument(self)
                    status = pdf.load(pdf_path)
                    if pdf.pageCount() <= 0:
                        fail("Failed to load generated PDF for printing.")
                        return

                    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
                    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
                    printer.setFullPage(True)

                    painter = QPainter()
                    if not painter.begin(printer):
                        fail("Unable to start printer device.")
                        return

                    try:
                        paint_rect = printer.pageLayout().paintRectPixels(printer.resolution())
                        target_w = max(1, int(paint_rect.width()))
                        target_h = max(1, int(paint_rect.height()))
                        target_size = QSize(target_w, target_h)

                        for idx in range(pdf.pageCount()):
                            img = pdf.render(idx, target_size)
                            if img.isNull():
                                continue
                            painter.drawImage(paint_rect, img)
                            if idx < pdf.pageCount() - 1:
                                printer.newPage()
                    finally:
                        painter.end()
                        try:
                            if delete_after and os.path.exists(pdf_path):
                                os.unlink(pdf_path)
                        except Exception:
                            pass

                    logger.info("Direct print completed.")
                    self.print_btn.setEnabled(True)
                except Exception as exc:
                    logger.error(f"Direct print failed: {exc}", exc_info=True)
                    fail(f"Printing failed: {exc}")

            from tempfile import NamedTemporaryFile
            tmp = NamedTemporaryFile(delete=False, suffix=".pdf")
            tmp_path = tmp.name
            tmp.close()

            try:
                from PyQt6.QtGui import QPageLayout, QPageSize
                from PyQt6.QtCore import QMarginsF

                layout = QPageLayout(
                    QPageSize(QPageSize.PageSizeId.A4),
                    QPageLayout.Orientation.Portrait,
                    QMarginsF(0, 0, 0, 0),
                )
            except Exception:
                layout = None

            finished_signal = getattr(page, "pdfPrintingFinished", None)
            if hasattr(finished_signal, "connect"):
                def _on_pdf_printing_finished(file_path: str, success: bool) -> None:
                    try:
                        try:
                            finished_signal.disconnect(_on_pdf_printing_finished)
                        except Exception:
                            pass
                        if not success:
                            fail("Failed to generate PDF for printing.")
                            try:
                                if os.path.exists(tmp_path):
                                    os.unlink(tmp_path)
                            except Exception:
                                pass
                            return
                        path_to_use = file_path or tmp_path
                        print_pdf_file(path_to_use, delete_after=True)
                    except Exception as exc:
                        logger.error(f"PDF printing finished handler failed: {exc}", exc_info=True)
                        fail(f"Printing failed: {exc}")

                finished_signal.connect(_on_pdf_printing_finished)
                try:
                    if layout is not None:
                        try:
                            page_print_to_pdf(tmp_path, layout)
                        except TypeError:
                            page_print_to_pdf(layout, tmp_path)
                    else:
                        page_print_to_pdf(tmp_path)
                except Exception as exc:
                    try:
                        finished_signal.disconnect(_on_pdf_printing_finished)
                    except Exception:
                        pass
                    fail(f"Printing failed: {exc}")
                return

            def on_pdf_ready(data) -> None:
                try:
                    raw = bytes(data) if data else b""
                    if not raw:
                        fail("Failed to generate PDF for printing.")
                        return
                    try:
                        with open(tmp_path, "wb") as f:
                            f.write(raw)
                    except Exception as exc:
                        fail(f"Failed to generate PDF for printing: {exc}")
                        return
                    print_pdf_file(tmp_path, delete_after=True)
                except Exception as exc:
                    logger.error(f"PDF callback print failed: {exc}", exc_info=True)
                    fail(f"Printing failed: {exc}")

            try:
                if layout is not None:
                    try:
                        page_print_to_pdf(on_pdf_ready, layout)
                    except TypeError:
                        page_print_to_pdf(layout, on_pdf_ready)
                else:
                    page_print_to_pdf(on_pdf_ready)
            except Exception as exc:
                fail(f"Printing failed: {exc}")
        except Exception as exc:
            logger.error(f"Print initialization failed: {exc}", exc_info=True)
            fail(f"Printing failed: {exc}")

    def _handle_download_pdf(self):
        if not self.web_view:
            QMessageBox.critical(self, "Download PDF", "Preview is not available on this system.")
            return
        self.download_pdf_btn.setEnabled(False)
        try:
            default_name = f"Invoice_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            suggested_dir = str(Path.home() / "Documents" / default_name)
            target_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Invoice as PDF",
                suggested_dir,
                "PDF Documents (*.pdf);;All Files (*)",
            )
            if not target_path:
                self.download_pdf_btn.setEnabled(True)
                return
            if not target_path.lower().endswith(".pdf"):
                target_path = target_path + ".pdf"
        except Exception as exc:
            logger.error(f"PDF file dialog failed: {exc}", exc_info=True)
            self.download_pdf_btn.setEnabled(True)
            QMessageBox.critical(self, "Download PDF", f"Save location error: {exc}")
            return

        def fail(msg: str) -> None:
            self.download_pdf_btn.setEnabled(True)
            QMessageBox.critical(self, "Download PDF", msg)

        try:
            page = self.web_view.page()
            page_print_to_pdf = getattr(page, "printToPdf", None)
            if not callable(page_print_to_pdf):
                fail("PDF export is not supported by this QtWebEngine build. Please install PyQt6-WebEngine properly.")
                return

            try:
                from PyQt6.QtGui import QPageLayout, QPageSize
                from PyQt6.QtCore import QMarginsF
                layout = QPageLayout(
                    QPageSize(QPageSize.PageSizeId.A4),
                    QPageLayout.Orientation.Portrait,
                    QMarginsF(0, 0, 0, 0),
                )
            except Exception:
                layout = None

            finished_signal = getattr(page, "pdfPrintingFinished", None)

            def _write_to_target(pdf_bytes_or_path: Any, _is_path: bool) -> None:
                try:
                    if _is_path:
                        src = str(pdf_bytes_or_path)
                        if not os.path.exists(src):
                            fail("PDF file was not created.")
                            return
                        import shutil
                        if os.path.abspath(src) != os.path.abspath(target_path):
                            try:
                                shutil.copyfile(src, target_path)
                            finally:
                                try:
                                    if os.path.exists(src):
                                        os.unlink(src)
                                except Exception:
                                    pass
                        else:
                            # src already at target; nothing to do
                            pass
                    else:
                        raw = bytes(pdf_bytes_or_path) if pdf_bytes_or_path else b""
                        if not raw:
                            fail("PDF generation produced empty output.")
                            return
                        with open(target_path, "wb") as f:
                            f.write(raw)
                    if os.path.exists(target_path):
                        sz = os.path.getsize(target_path)
                        logger.info(f"PDF saved: {target_path} ({sz} bytes)")
                        self.download_pdf_btn.setEnabled(True)
                        QMessageBox.information(
                            self,
                            "Download PDF",
                            f"PDF saved successfully:\n{target_path}\n\nSize: {sz:,} bytes",
                        )
                    else:
                        fail("File was not written to the selected location.")
                except Exception as exc:
                    logger.error(f"PDF save failed: {exc}", exc_info=True)
                    fail(f"Failed to save PDF: {exc}")

            from tempfile import NamedTemporaryFile
            tmp = NamedTemporaryFile(delete=False, suffix=".pdf")
            tmp_path = tmp.name
            tmp.close()

            if hasattr(finished_signal, "connect"):
                def _on_pdf_printing_finished(file_path: str, success: bool) -> None:
                    try:
                        try:
                            finished_signal.disconnect(_on_pdf_printing_finished)
                        except Exception:
                            pass
                        if not success:
                            try:
                                if os.path.exists(tmp_path):
                                    os.unlink(tmp_path)
                            except Exception:
                                pass
                            fail("Failed to generate PDF.")
                            return
                        actual_path = file_path or tmp_path
                        _write_to_target(actual_path, True)
                    except Exception as exc:
                        logger.error(f"PDF download finished handler failed: {exc}", exc_info=True)
                        fail(f"PDF download failed: {exc}")
                finished_signal.connect(_on_pdf_printing_finished)
                try:
                    if layout is not None:
                        try:
                            page_print_to_pdf(tmp_path, layout)
                        except TypeError:
                            page_print_to_pdf(layout, tmp_path)
                    else:
                        page_print_to_pdf(tmp_path)
                except Exception as exc:
                    try:
                        finished_signal.disconnect(_on_pdf_printing_finished)
                    except Exception:
                        pass
                    try:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                    except Exception:
                        pass
                    fail(f"PDF generation failed: {exc}")
                return

            def on_pdf_ready(data) -> None:
                try:
                    _write_to_target(data, False)
                except Exception as exc:
                    logger.error(f"PDF callback download failed: {exc}", exc_info=True)
                    fail(f"Failed to generate PDF: {exc}")
                finally:
                    try:
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                    except Exception:
                        pass

            try:
                if layout is not None:
                    try:
                        page_print_to_pdf(on_pdf_ready, layout)
                    except TypeError:
                        page_print_to_pdf(layout, on_pdf_ready)
                else:
                    page_print_to_pdf(on_pdf_ready)
            except Exception as exc:
                try:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                except Exception:
                    pass
                fail(f"PDF generation failed: {exc}")
        except Exception as exc:
            logger.error(f"PDF download init failed: {exc}", exc_info=True)
            fail(f"Download failed: {exc}")

    def _on_pdf_ready(self, data):
        # This can be used to auto-save a copy if needed
        pass

    def _open_in_browser(self):
        QMessageBox.information(self, "Print", "Browser printing is disabled. Use Print Now to print directly.")

# Singleton instance for easy access across the app
print_service_v2 = PrintServiceV2()
