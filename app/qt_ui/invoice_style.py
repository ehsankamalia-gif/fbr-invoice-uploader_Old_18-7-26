"""Look of the desktop Create New Invoice page.

Presentation only: every rule is scoped to #invoicePage (or an object name that
only exists on that page), so no other screen changes, and nothing here touches
field names, values, signals or the submit path. Colours come from the shared
design tokens in app/qt_ui/theme.py.
"""
from __future__ import annotations

from app.qt_ui.theme import TOKENS, _arrow_files

# Eye-comfort palette: no pure white / pure black. Text is a soft slate (still
# well above WCAG AA contrast on the cards), fields are a barely-tinted off-white
# so they don't glare against the white cards, and the page behind the cards is a
# calm blue-grey that lowers overall brightness.
_INK = "#263445"          # input / strong text
_INK_SOFT = "#556473"     # secondary text / secondary buttons
_LABEL = "#3a4d62"        # form field labels: darker than secondary text so they read as labels
_HEADING = "#2f4358"      # section titles
_LINE = "#dce3ea"         # card borders / dividers
_FIELD_BG = "#f8fafc"     # input background (off-white)
_FIELD_BORDER = "#c8d1db"
_FIELD_BORDER_HOVER = "#9fb0c1"
_FOCUS = "#3b82c4"        # calmer blue than the previous #2f80ed
_FOCUS_DARK = "#326fa8"
_FOCUS_DARKER = "#2b5f90"
_PAGE_BG = "#edf1f5"
# Each form section has its own colour family so the sections are told apart at a
# glance: a very soft tint for the card body (kept pale so the page stays easy on
# the eyes and the off-white fields still stand out) and a deeper gradient for the
# heading banner. White banner text is >= 4.5:1 at both gradient ends (tested).
SECTIONS = {
    # Invoice & Customer Information
    "customer": dict(card="#eef5fc", border="#cfe0f1", start="#1f4068", end="#3474b0", hover="#4283c0"),
    # Product & Payment Details
    "product":  dict(card="#ecf7f1", border="#cde8da", start="#0f4c3a", end="#1b7f5b", hover="#2a9070"),
    # Advanced FBR Fields (optional)
    "advanced": dict(card="#f4effa", border="#e0d4ef", start="#43275f", end="#7442a6", hover="#8353b5"),
    # Pricing Summary
    "pricing":  dict(card="#fdf4e8", border="#f1dfc3", start="#7a3f05", end="#ae5909", hover="#be6a17"),
}
DEFAULT_SECTION = "customer"


def tag_section(frame, name: str) -> None:
    """Mark a form-section card so the stylesheet gives it its own colours.
    Call before the page is first shown."""
    if name not in SECTIONS:
        raise ValueError(f"unknown form section {name!r}")
    frame.setProperty("section", name)
_DISABLED_BG = "#eef1f5"


def _banner_gradient(section: str = DEFAULT_SECTION, hover: bool = False) -> str:
    c = SECTIONS[section]
    end = c["hover"] if hover else c["end"]
    return f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c['start']}, stop:1 {end})"


def _section_qss() -> str:
    """One rule set per section: card body tint + border, heading banner, and the
    banner on the collapsible Advanced header (a button)."""
    out = []
    for name, c in SECTIONS.items():
        grad, grad_hover = _banner_gradient(name), _banner_gradient(name, hover=True)
        card = f'#invoicePage QFrame#formGroup[section="{name}"]'
        out.append(f"""
    {card} {{ background-color: {c['card']}; border: 1px solid {c['border']}; }}
    {card} QLabel#groupTitle {{ background: {grad}; }}
    {card} QPushButton#groupTitleToggle {{ background: {grad}; }}
    {card} QPushButton#groupTitleToggle:hover {{ background: {grad_hover}; }}
    {card} QPushButton#groupTitleToggle:pressed {{ background: {grad}; }}""")
    return "\n".join(out)


def build_invoice_page_qss() -> str:
    arrows = _arrow_files()
    combo_arrow = (
        f"#invoicePage QComboBox::down-arrow {{ image: url({arrows['down']}); width: 12px; height: 12px; }}"
        if arrows else ""
    )
    spin_arrows = (
        f"""#invoicePage QAbstractSpinBox::up-arrow {{ image: url({arrows['up']}); width: 9px; height: 9px; }}
        #invoicePage QAbstractSpinBox::down-arrow {{ image: url({arrows['down']}); width: 9px; height: 9px; }}"""
        if arrows else ""
    )
    return f"""
    #invoicePage {{ background-color: {_PAGE_BG}; }}

    #invoicePage QLabel#pageHeader {{
        font-size: 24px; font-weight: 700; color: {_INK}; margin-bottom: 0px;
    }}

    #invoicePage QScrollArea,
    #invoicePage QScrollArea > QWidget,
    #invoicePage QScrollArea > QWidget > QWidget#invoiceFormContainer {{
        background-color: transparent;
    }}

    /* ---- cards ---- */
    #invoicePage QFrame#formGroup {{
        background-color: #ffffff;
        border: 1px solid {_LINE};
        border-radius: 14px;
    }}
    #invoicePage QFrame#formGroup QLabel {{
        font-size: 13px; font-weight: 600; letter-spacing: 0.2px; color: {_LABEL};
        background: transparent; border: none;
    }}
    #invoicePage QFrame#formGroup QLabel#groupTitle {{
        font-size: 14px; font-weight: 800; letter-spacing: 1.2px; color: #ffffff;
        padding: 11px 18px; margin-bottom: 8px;
        border: none; border-radius: 10px;
        background: {_banner_gradient()};
    }}

    /* ---- per-section colours (card tint + heading banner) ---- */
    {_section_qss()}

    /* ---- inputs ---- */
    #invoicePage QLineEdit, #invoicePage QComboBox,
    #invoicePage QSpinBox, #invoicePage QDoubleSpinBox {{
        min-height: 24px;
        padding: 9px 13px;
        border: 1px solid {_FIELD_BORDER};
        border-radius: 8px;
        background-color: {_FIELD_BG};
        color: {_INK};
        font-size: 14px;
        selection-background-color: {TOKENS['primary']};
        selection-color: #ffffff;
    }}
    #invoicePage QLineEdit:hover, #invoicePage QComboBox:hover,
    #invoicePage QSpinBox:hover, #invoicePage QDoubleSpinBox:hover {{
        border-color: {_FIELD_BORDER_HOVER};
    }}
    #invoicePage QLineEdit:focus, #invoicePage QComboBox:focus,
    #invoicePage QSpinBox:focus, #invoicePage QDoubleSpinBox:focus {{
        border: 1px solid {_FOCUS};
        background-color: #ffffff;
    }}
    #invoicePage QLineEdit[readOnly="true"],
    #invoicePage QLineEdit:disabled, #invoicePage QComboBox:disabled,
    #invoicePage QSpinBox:disabled, #invoicePage QDoubleSpinBox:disabled {{
        background-color: {_DISABLED_BG}; color: #6f7c8a; border-color: #dfe5ec;
    }}

    #invoicePage QComboBox {{ padding-right: 28px; }}
    #invoicePage QComboBox::drop-down {{
        subcontrol-origin: padding; subcontrol-position: center right; width: 26px; border: none;
    }}
    {combo_arrow}
    #invoicePage QComboBox QAbstractItemView {{
        background-color: #ffffff; color: {_INK}; border: 1px solid {_LINE};
        selection-background-color: {TOKENS['primary_soft']};
        selection-color: {TOKENS['primary_text_on_soft']}; outline: 0;
    }}

    #invoicePage QAbstractSpinBox {{ padding-right: 6px; }}
    #invoicePage QAbstractSpinBox::up-button, #invoicePage QAbstractSpinBox::down-button {{
        subcontrol-origin: border; width: 20px; border: none; background: transparent;
    }}
    #invoicePage QAbstractSpinBox::up-button {{ subcontrol-position: top right; }}
    #invoicePage QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; }}
    {spin_arrows}

    #invoicePage QCheckBox {{ spacing: 9px; font-size: 13px; font-weight: 600; color: {_INK}; }}

    /* ---- buttons ---- */
    #invoicePage QPushButton#primaryButton {{
        min-height: 24px; padding: 11px 26px; border-radius: 9px;
        background-color: {_FOCUS}; color: #ffffff; border: none;
        font-size: 14px; font-weight: 700;
    }}
    #invoicePage QPushButton#primaryButton:hover {{ background-color: {_FOCUS_DARK}; }}
    #invoicePage QPushButton#primaryButton:pressed {{ background-color: {_FOCUS_DARKER}; }}
    #invoicePage QPushButton#primaryButton:disabled {{ background-color: #c9d1da; color: #f1f4f7; }}

    #invoicePage QPushButton#resetButton {{
        min-height: 24px; padding: 11px 20px; border-radius: 9px;
        background-color: #ffffff; color: {_INK_SOFT};
        border: 1px solid {_FIELD_BORDER}; font-size: 13px; font-weight: 600;
    }}
    #invoicePage QPushButton#resetButton:hover {{ background-color: #f3f6f9; border-color: {_FIELD_BORDER_HOVER}; }}
    #invoicePage QPushButton#resetButton:pressed {{ background-color: #e7ecf1; }}

    /* ---- inline validation states (set by app/qt_ui/form_validation.py) ---- */
    #invoicePage QLineEdit[vstate="invalid"], #invoicePage QComboBox[vstate="invalid"],
    #invoicePage QDoubleSpinBox[vstate="invalid"] {{
        border: 1px solid #d64545; background-color: #fff6f6;
    }}
    #invoicePage QLineEdit[vstate="invalid"]:focus, #invoicePage QComboBox[vstate="invalid"]:focus,
    #invoicePage QDoubleSpinBox[vstate="invalid"]:focus {{
        border: 1px solid #c0392b; background-color: #ffffff;
    }}
    #invoicePage QLineEdit[vstate="valid"], #invoicePage QComboBox[vstate="valid"],
    #invoicePage QDoubleSpinBox[vstate="valid"] {{
        border: 1px solid #7cc4a1;
    }}
    #invoicePage QLineEdit[vstate="valid"]:focus, #invoicePage QComboBox[vstate="valid"]:focus,
    #invoicePage QDoubleSpinBox[vstate="valid"]:focus {{
        border: 1px solid {_FOCUS};
    }}
    """


# ---- header KPI cards: colourful gradient cards ----------------------------
# [ frosted icon tile ]  LABEL
#                        value
# Each card is a diagonal gradient of its own colour with white text, so the
# row catches the eye. The colours are deliberately a touch deep (not neon) so
# white text keeps good contrast and the row stays easy to look at. Every card
# has the same size so the row reads as a set.
_CARD_H = 70
_TILE = 38


def _shade(hex_colour: str, factor: float) -> str:
    """Darken (factor < 1) a #rrggbb colour."""
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, int(r * factor))), max(0, min(255, int(g * factor))), max(0, min(255, int(b * factor)))
    )


def _tint(hex_colour: str, amount: float) -> str:
    """Lighten a #rrggbb colour toward white by `amount` (0..1)."""
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(
        int(r + (255 - r) * amount), int(g + (255 - g) * amount), int(b + (255 - b) * amount)
    )


def _gradient(accent: str, lift: bool = False) -> str:
    # A touch lighter at the top-left, the pure accent shaded a little at the
    # bottom-right: reads as a lit, rich colour rather than a flat/muddy one.
    # `lift` is the brighter version used while a clickable card is hovered / focused.
    start = _tint(accent, 0.24 if lift else 0.10)
    end = _shade(accent, 0.92 if lift else 0.82)
    return f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {start}, stop:1 {end})"


def stat_card_qss(object_name: str, accent: str = "#2e86c1", clickable: bool = False) -> str:
    hover = (
        f"""
        #{object_name}:hover, #{object_name}:focus {{
            background: {_gradient(accent, lift=True)};
        }}"""
        if clickable else ""
    )
    return f"""
        #{object_name} {{
            background: {_gradient(accent)};
            border: none;
            border-radius: 14px;
        }}{hover}
    """


STAT_LABEL_QSS = (
    "font-weight: 700; font-size: 10px; letter-spacing: 0.7px; color: rgba(255, 255, 255, 0.88); "
    "background: transparent; border: none;"
)
STAT_VALUE_QSS = "font-weight: 800; font-size: 24px; color: #ffffff; background: transparent; border: none;"
ENV_VALUE_QSS = "font-weight: 800; font-size: 16px; letter-spacing: 0.6px; color: #ffffff; background: transparent; border: none;"
ENV_TITLE_QSS = STAT_LABEL_QSS


def _icon_tile(icon_name: str, accent: str = "#ffffff"):
    """Frosted (translucent white) rounded square holding a white font icon."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel

    tile = QLabel()
    tile.setObjectName("statIconTile")
    tile.setFixedSize(_TILE, _TILE)
    tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
    tile.setStyleSheet(
        "QLabel#statIconTile { background-color: rgba(255, 255, 255, 0.22); border: none; border-radius: 11px; }"
    )
    try:  # QtAwesome is optional - without it the tile is simply a frosted square.
        from app.qt_ui.theme import _qta

        if _qta is not None:
            tile.setPixmap(_qta.icon(icon_name, color="#ffffff").pixmap(19, 19))
    except Exception:
        pass
    return tile


def _card_shell(parent, object_name: str, accent: str, clickable: bool = False):
    from PyQt6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy

    frame = QFrame(parent)
    frame.setObjectName(object_name)
    # Height is fixed; width follows the content (never clipped, whatever font
    # is in use) and equalize_cards() then makes the whole row the same width.
    frame.setFixedHeight(_CARD_H)
    frame.setMinimumWidth(168)
    frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    frame.setStyleSheet(stat_card_qss(object_name, accent, clickable))
    row = QHBoxLayout(frame)
    row.setContentsMargins(13, 0, 16, 0)
    row.setSpacing(11)
    return frame, row


def equalize_cards(*frames) -> None:
    """Give every card the width of the widest one, so the row looks uniform."""
    width = max(f.sizeHint().width() for f in frames)
    for f in frames:
        f.setMinimumWidth(width)


def build_stat_card(parent, object_name: str, title: str, icon_name: str, accent: str, value: str = "0",
                    clickable: bool = False):
    """Returns (card_frame, value_label). Callers keep updating the value with
    value_label.setText(...) exactly as before. clickable=True only adds the hover
    lift; wire the click itself with make_clickable()."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel, QVBoxLayout

    frame, row = _card_shell(parent, object_name, accent, clickable)
    row.addWidget(_icon_tile(icon_name))

    col = QVBoxLayout()
    col.setSpacing(0)
    col.setContentsMargins(0, 0, 0, 0)
    label = QLabel(title)
    label.setStyleSheet(STAT_LABEL_QSS)
    value_label = QLabel(value)
    value_label.setStyleSheet(STAT_VALUE_QSS)
    value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    col.addStretch(1)
    col.addWidget(label)
    col.addWidget(value_label)
    col.addStretch(1)
    row.addLayout(col, 1)
    return frame, value_label


def make_clickable(frame, callback, tooltip: str = "") -> None:
    """Make a card behave like a button: pointing-hand cursor, tooltip, a click inside
    it (on the card or any label on it) or Enter/Space when focused calls `callback`.
    Interaction only - it changes nothing about the card's content."""
    from PyQt6.QtCore import QEvent, QObject, Qt

    class _Filter(QObject):
        def eventFilter(self, obj, event):  # noqa: N802
            t = event.type()
            if t == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                if frame.rect().contains(event.position().toPoint()):
                    callback()
                    return True
            elif t == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                callback()
                return True
            return False

    flt = _Filter(frame)
    frame.installEventFilter(flt)
    frame._click_filter = flt                      # keep the Python object alive (PyQt would drop it)
    frame.setCursor(Qt.CursorShape.PointingHandCursor)
    frame.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    if tooltip:
        frame.setToolTip(tooltip)


def env_badge_qss(colour: str) -> str:
    """Environment card style: the whole card takes the environment's colour
    (SANDBOX orange / PRODUCTION green), so which FBR environment you are on is
    visible at a glance. Scoped to its object names so nothing leaks onto the
    labels inside it."""
    return f"""
        QFrame#envBadge {{
            background: {_gradient(colour)};
            border: none;
            border-radius: 14px;
        }}
        QLabel#envDot {{
            background-color: #ffffff;
            border: 2px solid rgba(255, 255, 255, 0.45);
            border-radius: 6px;
        }}
    """


def build_env_card(parent):
    """Returns (badge_frame, env_value_label) - same widgets/attributes the
    page always exposed (invoice_env_badge / invoice_env_value_label)."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

    frame, row = _card_shell(parent, "envBadge", "#27ae60")
    frame.setStyleSheet(env_badge_qss("#27ae60"))
    row.addWidget(_icon_tile("fa5s.server"))

    col = QVBoxLayout()
    col.setSpacing(0)
    col.setContentsMargins(0, 0, 0, 0)
    title = QLabel("ENVIRONMENT")
    title.setStyleSheet(ENV_TITLE_QSS)

    value_row = QHBoxLayout()
    value_row.setSpacing(8)
    value_row.setContentsMargins(0, 0, 0, 0)
    dot = QLabel()
    dot.setObjectName("envDot")
    dot.setFixedSize(12, 12)
    value_label = QLabel("UNKNOWN")
    value_label.setStyleSheet(ENV_VALUE_QSS)
    value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    value_row.addWidget(dot)
    value_row.addWidget(value_label, 1)

    col.addStretch(1)
    col.addWidget(title)
    col.addLayout(value_row)
    col.addStretch(1)
    row.addLayout(col, 1)
    return frame, value_label


# ---- small joined-control / badge pieces (radius matches the 8px inputs) ----
def joined_button_qss(font_px: int) -> str:
    """Icon button attached to the right edge of a line edit."""
    return f"""
        QPushButton {{
            background-color: #f1f4f8; color: {_INK_SOFT};
            border: 1px solid {_FIELD_BORDER};
            border-top-left-radius: 0px; border-bottom-left-radius: 0px;
            border-top-right-radius: 8px; border-bottom-right-radius: 8px;
            font-size: {font_px}px; font-weight: bold; padding: 0;
        }}
        QPushButton:hover {{ background-color: #e9eef5; color: {_FOCUS}; }}
        QPushButton:pressed {{ background-color: #dde4ed; }}
    """


STANDALONE_ICON_BUTTON_QSS = f"""
        QPushButton {{
            background-color: #f1f4f8; color: {_INK_SOFT};
            border: 1px solid {_FIELD_BORDER}; border-radius: 8px;
            font-size: 18px; font-weight: bold; padding: 0; margin-left: 6px;
        }}
        QPushButton:hover {{ background-color: #e9eef5; color: {_FOCUS}; }}
        QPushButton:pressed {{ background-color: #dde4ed; }}
"""

# Left half of a joined line edit + button pair.
JOINED_LINEEDIT_QSS = "border-top-right-radius: 0px; border-bottom-right-radius: 0px; border-right: none;"

QR_PLACEHOLDER_QSS = (
    f"border: 1px dashed {_FIELD_BORDER}; border-radius: 10px; background: {_FIELD_BG}; "
    "color: #9aa7b5; font-size: 11px; font-weight: 600;"
)
FBR_NUMBER_DISPLAY_QSS = f"""
    QLabel {{
        font-weight: 700; font-size: 15px; color: {_HEADING};
        border: none; background: transparent; padding: 0px 4px;
    }}
"""

ADVANCED_TOGGLE_QSS = """
    QPushButton#groupTitleToggle {
        text-align: left; border: none; border-radius: 10px;
        padding: 11px 18px; margin: 0px 28px 5px 0px;   /* 28px = the right gutter the other cards have */
        font-weight: 800; font-size: 14px; letter-spacing: 1.2px; color: #ffffff;
    }
"""

# Total Price (Incl. Tax): the figure the cashier checks last, so it stands out.
TOTAL_SPIN_QSS = (
    "font-weight: 700; color: #6b3a06; font-size: 17px; "          # sits on the amber Pricing card
    "background-color: #fff3dc; border: 1px solid #e8c47f;"
)


def _align_field_labels(grid) -> None:
    """Right-align each field label (columns 0 and 2) so it sits right next to
    its input instead of floating at the far left of a wide column. Only plain
    labels are touched: section titles and the small inline hints (which live in
    column 4) keep their own alignment."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel

    for row in range(grid.rowCount()):
        for col in (0, 2):
            item = grid.itemAtPosition(row, col)
            widget = item.widget() if item is not None else None
            if isinstance(widget, QLabel) and widget.objectName() != "groupTitle":
                widget.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)


def polish_form_layouts(*grids, card_margins=None) -> None:
    """Align every form card to the same grid so the eye doesn't have to
    re-find the input column in each card: the label columns (0 and 2) get one
    shared minimum width and never grow, the input columns (1 and 3) share the
    spare width equally, rows get a little more air, and every card keeps the
    same right gutter. Geometry only."""
    gutter = 22  # one horizontal gap: what the (empty) inline-hint column costs other cards
    for grid in grids:
        had_hint_column = grid.columnCount() > 4  # stock count / "existing customer" labels
        grid.setHorizontalSpacing(22)
        grid.setVerticalSpacing(18)
        grid.setColumnMinimumWidth(0, 166)
        grid.setColumnMinimumWidth(2, 166)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)
        grid.setColumnStretch(3, 1)
        grid.setColumnStretch(4, 0)
        grid.setColumnMinimumWidth(4, 6)
        _align_field_labels(grid)
        if card_margins is not None and grid in card_margins:
            grid.setContentsMargins(*card_margins[grid])
        if not had_hint_column:
            # no hint column in this card: reserve the same gutter on the right
            m = grid.contentsMargins()
            grid.setContentsMargins(m.left(), m.top(), m.right() + gutter, m.bottom())
