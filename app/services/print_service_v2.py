from __future__ import annotations

import os
import json
import threading
import base64
import datetime as dt
from pathlib import Path
from typing import Dict, Any, List, Optional
from jinja2 import Environment, FileSystemLoader
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QHBoxLayout, QMessageBox, QApplication, QWidget, QSizePolicy
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
    .mono {{
      font-family: Consolas, 'Courier New', monospace;
      font-weight: 700;
    }}
    .draggable {{
      outline: 1px dashed rgba(220, 53, 69, 0.75);
      outline-offset: 2px;
      touch-action: none;
      will-change: left, top, transform;
      transition: transform 120ms ease, box-shadow 120ms ease, outline-color 120ms ease;
      user-select: none;
      -webkit-user-select: none;
      cursor: grab;
    }}
    .dragging {{
      outline: 2px solid rgba(220, 53, 69, 0.95);
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
    @media print {{
      .draggable {{ outline: none !important; box-shadow: none !important; }}
      .pos-hud {{ display: none !important; }}
      .hidden-field {{ display: none !important; }}
      .sub-hidden {{ display: none !important; }}
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
        <div id="invoiceDate" class="field mono draggable" data-pos-key="invoice_date" data-default-left="0.95in" data-default-top="1.05in" style="left: 0.95in; top: 1.05in;">{esc(date_str)}</div>
        <div id="invoiceNumber" class="field mono draggable" data-pos-key="invoice_number" data-default-left="0.95in" data-default-top="1.45in" style="left: 0.95in; top: 1.45in;">{esc(data.get("invoice_number") or "")}</div>
        <div id="customerName" class="field draggable" data-pos-key="customer_name" data-default-left="0.95in" data-default-top="1.95in" style="left: 0.95in; top: 1.95in;">{esc(customer_name_line)}</div>
        <div id="customerAddress" class="field draggable" data-pos-key="customer_address" data-default-left="0.95in" data-default-top="2.35in" style="left: 0.95in; top: 2.35in;">{esc(data.get("customer_address") or "")}</div>

        <div id="itemDesc1" class="field draggable" data-pos-key="item_desc_1" data-default-left="0.95in" data-default-top="4.65in" style="left: 0.95in; top: 4.65in;">{esc(primary.get("model") or primary.get("description") or "")}</div>
        <div id="saleValue1" class="field mono draggable" data-pos-key="sale_value_1" data-default-left="3.75in" data-default-top="4.65in" style="left: 3.75in; top: 4.65in; text-align: right;">{esc(primary.get("sale_value") or "")}</div>
        <div id="salesTax1" class="field mono draggable" data-pos-key="sales_tax_1" data-default-left="4.65in" data-default-top="4.65in" style="left: 4.65in; top: 4.65in; text-align: right;">{esc(primary.get("sales_tax") or "")}</div>
        <div id="levy1" class="field mono draggable" data-pos-key="levy_1" data-default-left="5.55in" data-default-top="4.65in" style="left: 5.55in; top: 4.65in; text-align: right;">{esc(primary.get("levy") or "")}</div>
        <div id="totalLine1" class="field mono draggable" data-pos-key="total_line_1" data-default-left="6.45in" data-default-top="4.65in" style="left: 6.45in; top: 4.65in; text-align: right;">{esc(primary.get("total_line") or primary.get("price") or "")}</div>

        <div id="engineNo" class="field mono draggable" data-pos-key="engine_no" data-default-left="0.95in" data-default-top="5.85in" style="left: 0.95in; top: 5.85in;">{esc(primary.get("engine") or "")}</div>
        <div id="chassisNo" class="field mono draggable" data-pos-key="chassis_no" data-default-left="0.95in" data-default-top="6.25in" style="left: 0.95in; top: 6.25in;">{esc(primary.get("chassis") or "")}</div>
        <div id="model" class="field draggable" data-pos-key="model" data-default-left="0.95in" data-default-top="6.65in" style="left: 0.95in; top: 6.65in;">{esc(primary.get("model") or "")}</div>
        <div id="color" class="field draggable" data-pos-key="color" data-default-left="0.95in" data-default-top="7.05in" style="left: 0.95in; top: 7.05in;">{esc(primary.get("color") or "")}</div>

        <div id="regLetter" class="field mono draggable" data-pos-key="registration_letter_no" data-default-left="0.95in" data-default-top="7.65in" style="left: 0.95in; top: 7.65in;">{esc(data.get("registration_letter_no") or "")}</div>

        <div id="totalAmount" class="field mono draggable" data-pos-key="total_amount" data-default-left="6.55in" data-default-top="9.90in" style="left: 6.55in; top: 9.90in; text-align: right;">{esc(data.get("total_amount") or "")}</div>

        {qr_img_html}
        <div id="invoiceFbrId" class="field mono draggable" data-pos-key="invoice_fbr_id" data-default-left="2.55in" data-default-top="3.35in" style="left: 2.55in; top: 3.35in; font-size: 10pt;">{esc(data.get("fbr_invoice_number") or "")}</div>
      </div>
    </div>
  </div>

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
        if (!left || !top) return;
        const tmp = document.createElement('div');
        tmp.style.position = 'absolute';
        tmp.style.left = left;
        tmp.style.top = top;
        tmp.style.width = '0px';
        tmp.style.height = '0px';
        page.appendChild(tmp);
        const r = tmp.getBoundingClientRect();
        tmp.remove();
        const s = pageRect && pageRect.scale ? pageRect.scale : 1;
        el.style.left = `${{(r.left - pageRect.left) / s}}px`;
        el.style.top = `${{(r.top - pageRect.top) / s}}px`;
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
            if (isImg(el)) continue;
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
            try {{ writeSaved(backend); }} catch (_) {{}}
            applyAllPositions();
            updateFitScale();
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
        hud.textContent = `${{key}}: x ${{Math.round(rel.x)}}px, y ${{Math.round(rel.y)}}px${{fontPart}}${{hiddenPart}} [F2 edit, W wrap, +/- font, H hide/show, double-click reset]`;
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
        if (!(target instanceof HTMLElement)) return;
        const el = target.closest('.draggable[data-pos-key]');
        if (!el) return;
        selected = el;
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
        if (!(target instanceof HTMLElement)) return;
        const el = target.closest('.draggable[data-pos-key]');
        if (!el) return;
        selected = el;
        const key = el.getAttribute('data-pos-key') || '';
        const pageRect = getPageRect();
        applyDefaultsIfMissing(el, pageRect);
        if (key) {{
          const doc = readSaved();
          if (doc.elements && typeof doc.elements === 'object') delete doc.elements[key];
          doc.updated_at = nowMs();
          writeSaved(doc);
          saveToBackend(doc).catch(() => {{}});
        }}
        showHud(el);
        ev.preventDefault();
      }});

      document.addEventListener('keydown', (ev) => {{
        if (selected && (ev.key === 'b' || ev.key === 'B' || ev.key === 'i' || ev.key === 'I' || ev.key === 'f' || ev.key === 'F')) {{
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
            showHud(el);
            ev.preventDefault();
            return;
          }}
          if (ev.key === 'i' || ev.key === 'I') {{
            const cur = String(prev.font_style || getComputedStyle(el).fontStyle || 'normal');
            const next = cur.toLowerCase() === 'italic' ? 'normal' : 'italic';
            el.style.fontStyle = next;
            persistEntry(el, {{ font_style: next }});
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
          selected = null;
          if (drag) endDragPointer();
        }}
      }});

      document.addEventListener('click', (ev) => {{
        const target = ev.target;
        if (!(target instanceof HTMLElement)) return;
        const hit = target.closest('.draggable[data-pos-key]');
        if (hit) {{
          selected = hit;
          showHud(hit);
          return;
        }}
        hideHud();
        selected = null;
      }});

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
                margin: 2.25in 0.25in 0.25in 0.25in;
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
                margin: 1.5in auto 0 auto;
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

    def _on_pdf_ready(self, data):
        # This can be used to auto-save a copy if needed
        pass

    def _open_in_browser(self):
        QMessageBox.information(self, "Print", "Browser printing is disabled. Use Print Now to print directly.")

# Singleton instance for easy access across the app
print_service_v2 = PrintServiceV2()
