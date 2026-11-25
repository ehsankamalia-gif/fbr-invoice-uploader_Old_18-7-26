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
_DISABLED_BG = "#eef1f5"


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
        font-size: 14px; font-weight: 700; letter-spacing: 0.6px; color: {_HEADING};
        padding: 3px 0px 3px 12px; margin-bottom: 8px;
        border: none; border-left: 4px solid {_FOCUS};
    }}

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


def _gradient(accent: str) -> str:
    # A touch lighter at the top-left, the pure accent shaded a little at the
    # bottom-right: reads as a lit, rich colour rather than a flat/muddy one.
    return (
        "qlineargradient(x1:0, y1:0, x2:1, y2:1, "
        f"stop:0 {_tint(accent, 0.10)}, stop:1 {_shade(accent, 0.82)})"
    )


def stat_card_qss(object_name: str, accent: str = "#2e86c1") -> str:
    return f"""
        #{object_name} {{
            background: {_gradient(accent)};
            border: none;
            border-radius: 14px;
        }}
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


def _card_shell(parent, object_name: str, accent: str):
    from PyQt6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy

    frame = QFrame(parent)
    frame.setObjectName(object_name)
    # Height is fixed; width follows the content (never clipped, whatever font
    # is in use) and equalize_cards() then makes the whole row the same width.
    frame.setFixedHeight(_CARD_H)
    frame.setMinimumWidth(168)
    frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    frame.setStyleSheet(stat_card_qss(object_name, accent))
    row = QHBoxLayout(frame)
    row.setContentsMargins(13, 0, 16, 0)
    row.setSpacing(11)
    return frame, row


def equalize_cards(*frames) -> None:
    """Give every card the width of the widest one, so the row looks uniform."""
    width = max(f.sizeHint().width() for f in frames)
    for f in frames:
        f.setMinimumWidth(width)


def build_stat_card(parent, object_name: str, title: str, icon_name: str, accent: str, value: str = "0"):
    """Returns (card_frame, value_label). Callers keep updating the value with
    value_label.setText(...) exactly as before."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel, QVBoxLayout

    frame, row = _card_shell(parent, object_name, accent)
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

ADVANCED_TOGGLE_QSS = f"""
    QPushButton#groupTitleToggle {{
        background: transparent; border: none; text-align: left;
        font-weight: 700; color: {_HEADING}; font-size: 14px; letter-spacing: 0.6px;
        padding: 0; margin-bottom: 5px;
    }}
    QPushButton#groupTitleToggle:hover {{ color: {_FOCUS}; }}
"""

# Total Price (Incl. Tax): the figure the cashier checks last, so it stands out.
TOTAL_SPIN_QSS = (
    f"font-weight: 700; color: {_HEADING}; font-size: 17px; "
    "background-color: #eaf2fb; border: 1px solid #b7cde6;"
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
