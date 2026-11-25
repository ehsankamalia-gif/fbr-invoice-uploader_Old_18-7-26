"""Professional result / notice dialogs for the desktop app.

Replaces the plain QMessageBox look (a stock blue "i" icon with green text) with one
consistent design: a coloured gradient header with a badge icon and bold title, a clean
body (message, optional labelled detail rows, an optional tinted callout for a reason or
warning, an optional muted hint) and tidy buttons.

PRESENTATION ONLY: these dialogs just show text and return when dismissed. They never
change what happens before or after - callers decide that exactly as before.
"""
from __future__ import annotations

from typing import Iterable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.qt_ui.theme import _qta

# kind -> colours / icon / tagline
KINDS = {
    "success": dict(start="#0f5c36", end="#1b8a4e", button="#17803f", button_hover="#126a34",
                    soft="#eaf6ef", line="#bfe3cd", ink="#0f5c36", icon="fa5s.check", glyph="✓",
                    tagline="Completed successfully"),
    "warning": dict(start="#8a4b08", end="#c26a10", button="#b85f0c", button_hover="#9c4f08",
                    soft="#fdf3e4", line="#f0d3a6", ink="#7a3f05", icon="fa5s.exclamation", glyph="!",
                    tagline="Needs your attention"),
    "error":   dict(start="#7a2018", end="#c0392b", button="#c0392b", button_hover="#a42f23",
                    soft="#fdeeed", line="#f3c4c0", ink="#8f2a20", icon="fa5s.times", glyph="✕",
                    tagline="Something went wrong"),
    "info":    dict(start="#1f4068", end="#3474b0", button="#2f6fb0", button_hover="#265b94",
                    soft="#eaf2fb", line="#bcd3ee", ink="#1f4068", icon="fa5s.info", glyph="i",
                    tagline="For your information"),
}

_INK = "#263445"
_MUTED = "#6b7a8b"
_LINE = "#e3e8ef"


def _qss(c: dict) -> str:
    return f"""
    QDialog#noticeDialog {{ background-color: #ffffff; }}

    QFrame#noticeHeader {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c['start']}, stop:1 {c['end']});
        border: none;
    }}
    QLabel#noticeBadge {{
        background-color: rgba(255, 255, 255, 0.22);
        border: 2px solid rgba(255, 255, 255, 0.55);
        border-radius: 26px;
        color: #ffffff; font-size: 24px; font-weight: 800;
    }}
    QLabel#noticeTitle {{ color: #ffffff; font-size: 19px; font-weight: 800; background: transparent; }}
    QLabel#noticeTagline {{
        color: rgba(255, 255, 255, 0.85); font-size: 11px; font-weight: 700;
        letter-spacing: 1px; background: transparent;
    }}

    QLabel#noticeMessage {{ color: {_INK}; font-size: 14px; background: transparent; }}

    QFrame#noticeDetails {{ background-color: #f6f8fb; border: 1px solid {_LINE}; border-radius: 10px; }}
    QLabel#detailLabel {{ color: {_MUTED}; font-size: 12px; font-weight: 600; background: transparent; }}
    QLabel#detailValue {{ color: {_INK}; font-size: 14px; font-weight: 700; background: transparent; }}

    QFrame#noticeCallout {{
        background-color: {c['soft']};
        border: 1px solid {c['line']};
        border-left: 5px solid {c['end']};
        border-radius: 10px;
    }}
    QLabel#calloutLabel {{ color: {c['ink']}; font-size: 11px; font-weight: 800; letter-spacing: 1px; background: transparent; }}
    QLabel#calloutText {{ color: {c['ink']}; font-size: 14px; font-weight: 600; background: transparent; }}

    QLabel#noticeHint {{ color: {_MUTED}; font-size: 13px; background: transparent; }}

    QFrame#noticeFooter {{ background-color: #f6f8fb; border: none; border-top: 1px solid {_LINE}; }}

    QPushButton#noticePrimary {{
        background-color: {c['button']}; color: #ffffff; border: none; border-radius: 9px;
        padding: 10px 30px; font-size: 14px; font-weight: 700; min-width: 90px;
    }}
    QPushButton#noticePrimary:hover {{ background-color: {c['button_hover']}; }}
    QPushButton#noticePrimary:focus {{ border: 2px solid rgba(255, 255, 255, 0.7); }}
    QPushButton#noticeSecondary {{
        background-color: #ffffff; color: {_INK}; border: 1px solid #c8d1db; border-radius: 9px;
        padding: 10px 20px; font-size: 13px; font-weight: 600;
    }}
    QPushButton#noticeSecondary:hover {{ background-color: #eef2f7; border-color: #9fb0c1; }}
    """


class NoticeDialog(QDialog):
    def __init__(
        self,
        parent: Optional[QWidget],
        kind: str,
        title: str,
        message: str = "",
        *,
        window_title: Optional[str] = None,
        tagline: Optional[str] = None,
        details: Optional[Iterable[tuple[str, str]]] = None,
        callout: Optional[tuple[str, str]] = None,
        hint: Optional[str] = None,
        button_text: str = "OK",
        copy_button: Optional[tuple[str, str]] = None,
    ):
        super().__init__(parent)
        c = KINDS.get(kind, KINDS["info"])
        self.kind = kind
        self.setObjectName("noticeDialog")
        self.setWindowTitle(window_title or title)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(500)
        self.setMaximumWidth(620)
        self.setStyleSheet(_qss(c))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- header -------------------------------------------------------------
        header = QFrame()
        header.setObjectName("noticeHeader")
        hrow = QHBoxLayout(header)
        hrow.setContentsMargins(26, 22, 26, 22)
        hrow.setSpacing(16)
        badge = QLabel()
        badge.setObjectName("noticeBadge")
        badge.setFixedSize(52, 52)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if _qta is not None:
            try:
                badge.setPixmap(_qta.icon(c["icon"], color="#ffffff").pixmap(24, 24))
            except Exception:
                badge.setText(c["glyph"])
        else:
            badge.setText(c["glyph"])
        hrow.addWidget(badge)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        tag = QLabel((tagline or c["tagline"]).upper())
        tag.setObjectName("noticeTagline")
        self.title_label = QLabel(title)
        self.title_label.setObjectName("noticeTitle")
        self.title_label.setWordWrap(True)
        titles.addWidget(tag)
        titles.addWidget(self.title_label)
        hrow.addLayout(titles, 1)
        root.addWidget(header)

        # ---- body ---------------------------------------------------------------
        body = QVBoxLayout()
        body.setContentsMargins(28, 24, 28, 22)
        body.setSpacing(16)

        self.message_label = QLabel(message)
        self.message_label.setObjectName("noticeMessage")
        self.message_label.setTextFormat(Qt.TextFormat.PlainText)     # never interpret HTML in a message
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.message_label.setVisible(bool(message))
        body.addWidget(self.message_label)

        rows = [(k, v) for k, v in (details or []) if v]
        self.details_frame = QFrame()
        self.details_frame.setObjectName("noticeDetails")
        dv = QVBoxLayout(self.details_frame)
        dv.setContentsMargins(18, 14, 18, 14)
        dv.setSpacing(10)
        self.detail_values: dict[str, QLabel] = {}
        for label_text, value_text in rows:
            r = QHBoxLayout()
            lab = QLabel(label_text)
            lab.setObjectName("detailLabel")
            lab.setMinimumWidth(120)
            val = QLabel(str(value_text))
            val.setObjectName("detailValue")
            val.setTextFormat(Qt.TextFormat.PlainText)
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            r.addWidget(lab, 0, Qt.AlignmentFlag.AlignTop)
            r.addWidget(val, 1)
            dv.addLayout(r)
            self.detail_values[label_text] = val
        self.details_frame.setVisible(bool(rows))
        body.addWidget(self.details_frame)

        self.callout_frame = QFrame()
        self.callout_frame.setObjectName("noticeCallout")
        cv = QVBoxLayout(self.callout_frame)
        cv.setContentsMargins(18, 12, 18, 14)
        cv.setSpacing(4)
        self.callout_text = QLabel("")
        if callout and callout[1]:
            cl = QLabel(callout[0].upper())
            cl.setObjectName("calloutLabel")
            self.callout_text = QLabel(callout[1])
            self.callout_text.setObjectName("calloutText")
            self.callout_text.setTextFormat(Qt.TextFormat.PlainText)
            self.callout_text.setWordWrap(True)
            self.callout_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            cv.addWidget(cl)
            cv.addWidget(self.callout_text)
        self.callout_frame.setVisible(bool(callout and callout[1]))
        body.addWidget(self.callout_frame)

        self.hint_label = QLabel(hint or "")
        self.hint_label.setObjectName("noticeHint")
        self.hint_label.setTextFormat(Qt.TextFormat.PlainText)
        self.hint_label.setWordWrap(True)
        self.hint_label.setVisible(bool(hint))
        body.addWidget(self.hint_label)

        wrapper = QWidget()
        wrapper.setLayout(body)
        root.addWidget(wrapper)

        # ---- footer -------------------------------------------------------------
        footer = QFrame()
        footer.setObjectName("noticeFooter")
        frow = QHBoxLayout(footer)
        frow.setContentsMargins(24, 14, 24, 14)
        frow.setSpacing(10)
        frow.addStretch(1)

        self.copy_button: Optional[QPushButton] = None
        if copy_button:
            label, text = copy_button
            self.copy_button = QPushButton(label)
            self.copy_button.setObjectName("noticeSecondary")
            self.copy_button.setAutoDefault(False)
            self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.copy_button.clicked.connect(lambda: self._copy(label, text))
            frow.addWidget(self.copy_button)

        self.ok_button = QPushButton(button_text)
        self.ok_button.setObjectName("noticePrimary")
        self.ok_button.setDefault(True)
        self.ok_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ok_button.clicked.connect(self.accept)
        frow.addWidget(self.ok_button)
        root.addWidget(footer)

        self.ok_button.setFocus()

    def _copy(self, label: str, text: str) -> None:
        QGuiApplication.clipboard().setText(text)
        if self.copy_button is not None:
            self.copy_button.setText("Copied ✓")


# ---- convenience entry points ---------------------------------------------------------
def show_notice(parent, kind: str, title: str, message: str = "", **kw) -> None:
    NoticeDialog(parent, kind, title, message, **kw).exec()


def show_invoice_result(parent, invoice_number: str, fbr_invoice_number: Optional[str],
                        fbr_message: Optional[str]) -> None:
    """The dialog shown right after an invoice is submitted.

    * FBR accepted it  -> green "Uploaded to FBR" with the invoice / FBR numbers.
    * FBR refused it   -> amber "Saved locally": the invoice is safe on this computer, the
      reason FBR gave is shown in a callout, and the user is told they can retry later.
    """
    if fbr_invoice_number:
        NoticeDialog(
            parent, "success", "Invoice Uploaded to FBR",
            f"Invoice {invoice_number} was created and uploaded to FBR successfully.",
            window_title="Submission Success",
            details=[("Invoice No.", invoice_number), ("FBR Invoice ID", fbr_invoice_number)],
            copy_button=("Copy FBR ID", fbr_invoice_number),
        ).exec()
        return
    reason = (fbr_message or "").strip() or "No reason was returned by FBR."
    NoticeDialog(
        parent, "warning", "Saved Locally — FBR Upload Failed",
        f"Invoice {invoice_number} has been saved on this computer, but it could not be uploaded to FBR.",
        window_title="Local Save Success",
        tagline="Saved · not yet uploaded",
        details=[("Invoice No.", invoice_number), ("FBR Status", "Not uploaded")],
        callout=("Reason from FBR", reason),
        hint="You can retry the upload later from the Reports section.",
        copy_button=("Copy reason", reason),
    ).exec()
