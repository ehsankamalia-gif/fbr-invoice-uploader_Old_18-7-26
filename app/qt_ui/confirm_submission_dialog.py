"""Professional "review before submitting to FBR" confirmation dialog.

Display-only: it shows the values it is handed and returns Accepted/Rejected.
It never reads or alters invoice data itself.
"""
from __future__ import annotations

from typing import Sequence, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_STYLE = """
QDialog#ConfirmSubmission { background-color: #f4f6f9; }

QFrame#Header { background-color: #1f3a5f; border: none; }
QLabel#HeaderIcon {
    background-color: rgba(255, 255, 255, 0.16);
    color: #ffffff; border-radius: 22px; font-size: 22px; font-weight: bold;
}
QLabel#HeaderTitle { color: #ffffff; font-size: 17px; font-weight: 600; }
QLabel#HeaderSub { color: #c9d6e8; font-size: 12px; }

QFrame#Card {
    background-color: #ffffff; border: 1px solid #dde3ec; border-radius: 10px;
}
QLabel#RowLabel { color: #6b7686; font-size: 12px; background: transparent; }
QLabel#RowValue { color: #1d2733; font-size: 13px; font-weight: 600; background: transparent; }
QFrame#RowDivider { background-color: #eef1f6; border: none; max-height: 1px; min-height: 1px; }

QFrame#TotalBar { background-color: #eaf6ee; border: 1px solid #bfe3cb; border-radius: 8px; }
QLabel#TotalLabel { color: #1e6b3a; font-size: 12px; font-weight: 600; background: transparent; }
QLabel#TotalValue { color: #14532d; font-size: 18px; font-weight: 700; background: transparent; }

QLabel#Note { color: #6b7686; font-size: 12px; background: transparent; }

QPushButton { font-size: 13px; font-weight: 600; border-radius: 6px; padding: 9px 22px; min-width: 96px; }
QPushButton#Cancel { background-color: #ffffff; color: #3b4757; border: 1px solid #c5cedb; }
QPushButton#Cancel:hover { background-color: #eef1f6; }
QPushButton#Cancel:focus { border: 1px solid #1f3a5f; }
QPushButton#Submit { background-color: #1e8e4e; color: #ffffff; border: 1px solid #1a7a43; }
QPushButton#Submit:hover { background-color: #19793f; }
QPushButton#Submit:focus { border: 2px solid #0f4d29; }
"""


class ConfirmSubmissionDialog(QDialog):
    def __init__(
        self,
        rows: Sequence[Tuple[str, str]],
        total_text: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ConfirmSubmission")
        self.setWindowTitle("Confirm Submission")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setStyleSheet(_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Header band ----
        header = QFrame()
        header.setObjectName("Header")
        h = QHBoxLayout(header)
        h.setContentsMargins(24, 18, 24, 18)
        h.setSpacing(14)

        icon = QLabel("✓")
        icon.setObjectName("HeaderIcon")
        icon.setFixedSize(44, 44)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(icon)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Review Before Submitting")
        title.setObjectName("HeaderTitle")
        sub = QLabel("Please confirm the invoice details below")
        sub.setObjectName("HeaderSub")
        titles.addWidget(title)
        titles.addWidget(sub)
        h.addLayout(titles, 1)
        root.addWidget(header)

        # ---- Body ----
        body = QVBoxLayout()
        body.setContentsMargins(24, 20, 24, 20)
        body.setSpacing(14)

        card = QFrame()
        card.setObjectName("Card")
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(18, 8, 18, 8)
        card_l.setSpacing(0)

        for i, (label, value) in enumerate(rows):
            if i:
                divider = QFrame()
                divider.setObjectName("RowDivider")
                card_l.addWidget(divider)
            row = QHBoxLayout()
            row.setContentsMargins(0, 9, 0, 9)
            lbl = QLabel(label)
            lbl.setObjectName("RowLabel")
            lbl.setMinimumWidth(110)
            val = QLabel(value or "—")
            val.setObjectName("RowValue")
            val.setTextFormat(Qt.TextFormat.PlainText)
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(lbl)
            row.addWidget(val, 1)
            card_l.addLayout(row)
        body.addWidget(card)

        total_bar = QFrame()
        total_bar.setObjectName("TotalBar")
        t = QHBoxLayout(total_bar)
        t.setContentsMargins(18, 12, 18, 12)
        t_lbl = QLabel("Total Amount")
        t_lbl.setObjectName("TotalLabel")
        t_val = QLabel(total_text)
        t_val.setObjectName("TotalValue")
        t_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        t.addWidget(t_lbl)
        t.addWidget(t_val, 1)
        body.addWidget(total_bar)

        note = QLabel("Once submitted, this invoice is sent to FBR and cannot be edited.")
        note.setObjectName("Note")
        note.setWordWrap(True)
        body.addWidget(note)

        # ---- Buttons ----
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 6, 0, 0)
        buttons.setSpacing(10)
        buttons.addStretch(1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("Cancel")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)

        submit_btn = QPushButton("Submit to FBR")
        submit_btn.setObjectName("Submit")
        submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        submit_btn.setDefault(True)
        submit_btn.clicked.connect(self.accept)

        buttons.addWidget(cancel_btn)
        buttons.addWidget(submit_btn)
        body.addLayout(buttons)

        root.addLayout(body)
        submit_btn.setFocus()
