"""Central look-and-feel for the desktop app: design tokens, ONE application
stylesheet, and font icons.

Why this exists: styling used to live in ~700 scattered inline setStyleSheet()
calls with 170+ hand-typed colours. This module is the single place that
defines the base look of every standard control (inputs, combo boxes, tables,
buttons, scroll bars, tooltips, dialogs). A widget that still has its own
inline stylesheet keeps winning for the properties it sets (Qt applies the
closest stylesheet last), so adopting this is non-breaking - screens can be
migrated off inline styles one at a time and simply start using these tokens.

The colours below are the palette the app already used most (#2c3e50 text,
#3498db primary, #e74c3c danger, ...), so existing screens look consistent
rather than different.

Rollback: set the environment variable APP_DISABLE_THEME=1 and the app starts
exactly as it did before this module existed.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

from PyQt6.QtCore import QEvent, QObject, QSize
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QAbstractButton, QApplication, QPushButton

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Design tokens - change a value here and every standard control follows.
# --------------------------------------------------------------------------
TOKENS = {
    "text": "#2c3e50",
    "text_muted": "#7f8c8d",
    "text_disabled": "#adb5bd",
    "surface": "#ffffff",
    "surface_alt": "#f8f9fa",
    "surface_sunken": "#f1f3f5",
    "border": "#ced4da",
    "border_soft": "#dee2e6",
    "border_hover": "#adb5bd",
    "primary": "#3498db",
    "primary_dark": "#2980b9",
    "primary_soft": "#e3f2fd",
    "primary_text_on_soft": "#1976d2",
    "danger": "#e74c3c",
    "success": "#27ae60",
    "radius": "6px",
    "radius_lg": "10px",
}


def _arrow_files() -> dict[str, str]:
    """Writes the small chevron images the combo/spin-box sub-controls need
    (QSS can only reference image FILES) and returns their forward-slash
    paths. Empty dict if the temp folder isn't writable - the stylesheet then
    simply leaves those arrows to the Fusion style."""
    colour = TOKENS["text_muted"].replace("#", "%23")
    shapes = {
        "down": "M5 7.5l5 5 5-5",
        "up": "M5 12.5l5-5 5 5",
    }
    out: dict[str, str] = {}
    try:
        folder = Path(tempfile.gettempdir()) / "fbr_theme_assets"
        folder.mkdir(parents=True, exist_ok=True)
        for name, path in shapes.items():
            svg = (
                "<svg xmlns='http://www.w3.org/2000/svg' width='20' height='20' viewBox='0 0 20 20' "
                f"fill='none' stroke='{TOKENS['text_muted']}' stroke-width='2' "
                f"stroke-linecap='round' stroke-linejoin='round'><path d='{path}'/></svg>"
            )
            target = folder / f"chevron-{name}.svg"
            target.write_text(svg, encoding="utf-8")
            out[name] = target.as_posix()
    except Exception as e:  # pragma: no cover - cosmetic only
        logger.warning("Theme arrow assets unavailable: %s", e)
        return {}
    return out


def build_stylesheet(t: dict[str, str] | None = None) -> str:
    t = {**TOKENS, **(t or {})}
    arrows = _arrow_files()

    combo_arrow = ""
    spin_arrows = ""
    date_arrow = ""
    if arrows:
        date_arrow = f"""
        QDateEdit::down-arrow, QDateTimeEdit::down-arrow {{ image: url({arrows['down']}); width: 12px; height: 12px; }}
        """
        combo_arrow = f"""
        QComboBox::down-arrow {{ image: url({arrows['down']}); width: 12px; height: 12px; }}
        """
        spin_arrows = f"""
        QAbstractSpinBox::up-arrow {{ image: url({arrows['up']}); width: 9px; height: 9px; }}
        QAbstractSpinBox::down-arrow {{ image: url({arrows['down']}); width: 9px; height: 9px; }}
        """

    return f"""
    QToolTip {{
        background-color: {t['text']}; color: #ffffff;
        border: none; border-radius: 4px; padding: 5px 8px;
    }}

    /* ---- text inputs ---- */
    QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox {{
        background-color: {t['surface']};
        color: {t['text']};
        border: 1px solid {t['border']};
        border-radius: {t['radius']};
        padding: 4px 8px;
        selection-background-color: {t['primary']};
        selection-color: #ffffff;
    }}
    QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QAbstractSpinBox:hover, QComboBox:hover {{
        border-color: {t['border_hover']};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QAbstractSpinBox:focus, QComboBox:focus {{
        border: 1px solid {t['primary']};
    }}
    QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
    QAbstractSpinBox:disabled, QComboBox:disabled {{
        background-color: {t['surface_sunken']}; color: {t['text_disabled']};
    }}
    QLineEdit[readOnly="true"] {{ background-color: {t['surface_alt']}; }}

    /* ---- combo box ---- */
    QComboBox {{ padding-right: 24px; }}
    QComboBox::drop-down {{
        subcontrol-origin: padding; subcontrol-position: center right;
        width: 22px; border: none;
    }}
    {combo_arrow}
    QComboBox QAbstractItemView {{
        background-color: {t['surface']};
        color: {t['text']};
        border: 1px solid {t['border_soft']};
        outline: 0;
        selection-background-color: {t['primary_soft']};
        selection-color: {t['primary_text_on_soft']};
    }}

    /* ---- spin boxes / date edits ---- */
    QAbstractSpinBox {{ padding-right: 4px; }}
    QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
        subcontrol-origin: border; width: 18px; border: none; background: transparent;
    }}
    QAbstractSpinBox::up-button {{ subcontrol-position: top right; }}
    QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; }}
    QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{
        background-color: {t['surface_sunken']};
    }}
    {spin_arrows}
    QDateEdit::drop-down, QDateTimeEdit::drop-down {{
        subcontrol-origin: padding; subcontrol-position: center right;
        width: 22px; border: none; background: transparent;
    }}
    {date_arrow}

    /* ---- buttons (anything without its own stylesheet) ---- */
    QPushButton {{
        background-color: {t['surface']};
        color: {t['text']};
        border: 1px solid {t['border']};
        border-radius: {t['radius']};
        padding: 6px 14px;
    }}
    QPushButton:hover {{ background-color: {t['surface_sunken']}; border-color: {t['border_hover']}; }}
    QPushButton:pressed {{ background-color: {t['border_soft']}; }}
    QPushButton:focus {{ border-color: {t['primary']}; }}
    QPushButton:disabled {{
        background-color: {t['surface_alt']}; color: {t['text_disabled']}; border-color: {t['border_soft']};
    }}
    QPushButton:default {{
        background-color: {t['primary']}; color: #ffffff; border-color: {t['primary_dark']};
    }}
    QPushButton:default:hover {{ background-color: {t['primary_dark']}; }}

    /* ---- tables & lists ---- */
    QTableView, QTableWidget, QTreeView, QListView {{
        background-color: {t['surface']};
        alternate-background-color: {t['surface_alt']};
        color: {t['text']};
        border: 1px solid {t['border_soft']};
        gridline-color: {t['surface_sunken']};
        selection-background-color: {t['primary_soft']};
        selection-color: {t['primary_text_on_soft']};
        outline: 0;
    }}
    QHeaderView::section {{
        background-color: {t['surface_sunken']};
        color: #495057;
        padding: 6px 10px;
        border: none;
        border-bottom: 2px solid {t['border_soft']};
        font-weight: 600;
    }}
    QTableCornerButton::section {{ background-color: {t['surface_sunken']}; border: none; }}

    /* ---- scroll bars ---- */
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: #c1c7cd; min-height: 28px; border-radius: 5px; }}
    QScrollBar::handle:horizontal {{ background: #c1c7cd; min-width: 28px; border-radius: 5px; }}
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{ background: #9aa3ab; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* ---- menus, dialogs, misc ---- */
    QMenu {{
        background-color: {t['surface']}; color: {t['text']};
        border: 1px solid {t['border_soft']}; padding: 4px;
    }}
    QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
    QMenu::item:selected {{ background-color: {t['primary_soft']}; color: {t['primary_text_on_soft']}; }}
    QMenu::separator {{ height: 1px; background: {t['border_soft']}; margin: 4px 8px; }}

    QDialog {{ background-color: {t['surface_alt']}; }}
    QMessageBox {{ background-color: {t['surface']}; }}

    QProgressBar {{
        background-color: {t['surface_sunken']}; border: none; border-radius: 4px; text-align: center;
    }}
    QProgressBar::chunk {{ background-color: {t['primary']}; border-radius: 4px; }}
    """


# --------------------------------------------------------------------------
# Font icons (QtAwesome) replacing the emoji that used to be typed into
# button labels.
# --------------------------------------------------------------------------
_EMOJI_ICONS = {
    "↻": "fa5s.sync-alt",      # ↻
    "\U0001f504": "fa5s.sync-alt",  # 🔄
    "↺": "fa5s.undo-alt",      # ↺
    "\U0001f5d1": "fa5s.trash-alt", # 🗑
    "\U0001f4be": "fa5s.save",      # 💾
    "➕": "fa5s.plus",          # ➕
    "＋": "fa5s.plus",          # ＋
    "\U0001f5a8": "fa5s.print",     # 🖨
    "✎": "fa5s.pen",           # ✎
    "⏻": "fa5s.power-off",     # ⏻
    "✕": "fa5s.times",         # ✕
    "❌": "fa5s.times-circle",  # ❌
    "☰": "fa5s.bars",          # ☰
    "\U0001f50d": "fa5s.search",    # 🔍
    "\U0001f4c4": "fa5s.file-alt",  # 📄
    "\U0001f50c": "fa5s.plug",      # 🔌
    "\U0001f4c2": "fa5s.folder-open",  # 📂
    "\U0001f680": "fa5s.rocket",    # 🚀
    "\U0001f4c1": "fa5s.folder",    # 📁
    "⇄": "fa5s.exchange-alt",  # ⇄
    "\U0001f501": "fa5s.redo",      # 🔁
    "‹": "fa5s.chevron-left",  # ‹
    "\U0001f441": "fa5s.eye",       # 👁
    "\U0001f4e4": "fa5s.upload",    # 📤
    "\U0001f4e5": "fa5s.download",  # 📥
    "←": "fa5s.arrow-left",    # ←
    "⬇": "fa5s.download",      # ⬇
    "⬆": "fa5s.upload",        # ⬆
    "✅": "fa5s.check-circle",  # ✅
    "↩": "fa5s.undo",          # ↩
    "\U0001f9ea": "fa5s.flask",     # 🧪
    "\U0001f558": "fa5s.clock",     # 🕘
}
_VARIATION_SELECTOR = "️"
_COLOR_RE = re.compile(r"(?:^|[;{\s])color\s*:\s*([^;}\s]+)", re.IGNORECASE)

try:  # QtAwesome is optional: without it buttons simply keep their emoji.
    import qtawesome as _qta
except Exception:  # pragma: no cover
    _qta = None


def _icon_colour(button: QAbstractButton) -> str:
    """The icon should match the label colour. Most coloured buttons set it
    in their own inline stylesheet; otherwise use the theme text colour."""
    match = _COLOR_RE.search(button.styleSheet() or "")
    if match:
        value = match.group(1).strip()
        if value.lower() == "white":
            return "#ffffff"
        if QColor(value).isValid():
            return value
    return TOKENS["text"]


def iconize_button(button: QAbstractButton, text: str | None = None) -> str:
    """If the label starts with a known emoji, move it into a real icon.
    Returns the (possibly stripped) text to display."""
    text = button.text() if text is None else text
    if _qta is None or not text:
        return text
    first = text[0]
    name = _EMOJI_ICONS.get(first)
    if not name:
        return text
    rest = text[1:].lstrip(_VARIATION_SELECTOR).lstrip()
    try:
        button.setIcon(_qta.icon(name, color=_icon_colour(button)))
        button.setIconSize(QSize(16, 16))
    except Exception:  # pragma: no cover - never break a screen over an icon
        return text
    return rest


_patched = False


def _patch_set_text() -> None:
    """Buttons whose label is re-set later (e.g. "Converting..." -> back to
    "Convert") must keep using an icon instead of getting their emoji back, so
    route Python-side setText() through iconize_button too."""
    global _patched
    if _patched or _qta is None:
        return
    original = QAbstractButton.setText

    def setText(self, text):  # noqa: N802 - mirrors Qt's name
        original(self, iconize_button(self, text) if isinstance(text, str) else text)

    try:
        QAbstractButton.setText = setText
        _patched = True
    except Exception:  # pragma: no cover
        pass


class IconManager(QObject):
    """Catches buttons built with emoji text through their constructor
    (QPushButton("🗑 Delete")) the first time they are shown."""

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.Type.Show and isinstance(obj, QAbstractButton):
            text = obj.text()
            if text and text[0] in _EMOJI_ICONS:
                try:
                    obj.setText(text)  # patched setText strips + sets the icon
                except Exception:
                    pass
            # Small fixed-width buttons ("+", "x", ...) have no room for the
            # theme's default horizontal padding, which would hide the label.
            # Ones that style themselves are left alone.
            if (
                isinstance(obj, QPushButton)
                and not obj.styleSheet()
                and obj.minimumWidth() == obj.maximumWidth()
                and 0 < obj.maximumWidth() <= 48
            ):
                obj.setStyleSheet("padding: 0px;")
        return False


def apply_theme(app: QApplication) -> None:
    """Call once, right after QApplication is created and before any widget."""
    if os.environ.get("APP_DISABLE_THEME") == "1":
        logger.info("Theme disabled via APP_DISABLE_THEME=1")
        return

    # Fusion renders QSS predictably on every Windows version (the native
    # style mixes badly with a stylesheet).
    app.setStyle("Fusion")

    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Highlight, QColor(TOKENS["primary"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    app.setStyleSheet(build_stylesheet())

    _patch_set_text()
    icon_manager = IconManager(app)
    app.installEventFilter(icon_manager)
    app._icon_manager = icon_manager  # keep a reference alive
