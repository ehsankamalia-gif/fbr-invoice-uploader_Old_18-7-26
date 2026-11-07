"""Barcode Label Printing: printable Code128 labels for one or more
parts, reusing the exact QImage/QPrinter pattern already proven for the
FBR QR code on printed receipts (see ui/sale_card_widget.py's
_build_fbr_qr_image / print_sale_receipt). Prints through the normal
Print dialog, same as a receipt - no new printer setup required.
"""
from __future__ import annotations

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QImage, QTextDocument
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from spare_parts.ui.widgets import NoScrollSpinBox
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)

_PRIMARY_BTN = """
    QPushButton {
        background-color: #3498db; color: white; border: none;
        border-radius: 4px; padding: 8px 16px; font-weight: bold;
    }
    QPushButton:hover { background-color: #2980b9; }
    QPushButton:disabled { background-color: #bdc3c7; }
"""

_RESET_BTN = """
    QPushButton {
        background-color: #f8f9fa; color: #6c757d; border: 1px solid #dee2e6;
        border-radius: 4px; padding: 8px 16px;
    }
    QPushButton:hover { background-color: #e2e6ea; }
"""

_LABELS_PER_ROW = 3


def _build_barcode_image(data: str):
    """Code128 barcode for `data` - the same library -> PIL -> PNG bytes
    -> QImage.loadFromData() pipeline already proven for the FBR QR code
    (see sale_card_widget._build_fbr_qr_image). Returns None on failure
    (e.g. a barcode value Code128 can't encode) rather than raising, so
    one bad part never blocks printing the rest."""
    try:
        import io

        import barcode
        from barcode.writer import ImageWriter

        code = barcode.get("code128", data, writer=ImageWriter())
        pil_image = code.render(writer_options={
            "module_height": 10.0, "font_size": 8, "text_distance": 3, "quiet_zone": 2,
        })
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        qimage = QImage()
        qimage.loadFromData(buffer.getvalue(), "PNG")
        return qimage
    except Exception as e:
        logger.error(f"Failed to build barcode image for {data!r}: {e}", exc_info=True)
        return None


class BarcodeLabelDialog(QDialog):
    """`parts`: live SpPart objects (already loaded, same as
    PurchaseDialog's prefill pattern) - the caller's session may already
    be closed by the time Print is clicked, so only already-loaded
    scalar columns (part_no, name, barcode) are touched here."""

    def __init__(self, parts: list, parent=None):
        super().__init__(parent)
        self.parts = parts
        self.setWindowTitle("Print Barcode Labels")
        self.setMinimumSize(480, 420)

        root = QVBoxLayout(self)

        info = QLabel(
            f"{len(parts)} part(s) selected. Parts with no Barcode set use their "
            "Part No. instead, so every part can always be labeled."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #6c757d;")
        root.addWidget(info)

        self.table = QTableWidget(len(parts), 3)
        self.table.setHorizontalHeaderLabels(["Part", "Barcode Value", "Copies"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)

        self._copies_spins: list[NoScrollSpinBox] = []
        for row, part in enumerate(parts):
            self.table.setItem(row, 0, QTableWidgetItem(f"{part.part_no} - {part.name}"))
            self.table.setItem(row, 1, QTableWidgetItem(self._barcode_value(part)))
            spin = NoScrollSpinBox()
            spin.setRange(1, 999)
            spin.setValue(1)
            self.table.setCellWidget(row, 2, spin)
            self._copies_spins.append(spin)
        root.addWidget(self.table, 1)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        root.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_RESET_BTN)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        self.print_btn = QPushButton("Print")
        self.print_btn.setStyleSheet(_PRIMARY_BTN)
        self.print_btn.clicked.connect(self._on_print_clicked)
        btn_row.addWidget(self.print_btn)
        root.addLayout(btn_row)

    @staticmethod
    def _barcode_value(part) -> str:
        return (part.barcode or part.part_no or "").strip()

    def _on_print_clicked(self) -> None:
        try:
            from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
        except ImportError:
            QMessageBox.warning(self, "Printing Unavailable", "Print support is not installed.")
            return

        self.error_label.hide()
        labels: list[tuple] = []  # (part, barcode_value) repeated per copy
        for row, part in enumerate(self.parts):
            copies = self._copies_spins[row].value()
            barcode_value = self._barcode_value(part)
            labels.extend([(part, barcode_value)] * copies)

        if not labels:
            QMessageBox.information(self, "Nothing to Print", "No labels to print.")
            return

        document = QTextDocument()
        cells_html = []
        skipped = []
        for idx, (part, barcode_value) in enumerate(labels):
            qimage = _build_barcode_image(barcode_value)
            if qimage is None:
                skipped.append(f"{part.part_no} ({barcode_value!r})")
                continue
            resource_name = f"barcode_{idx}"
            document.addResource(QTextDocument.ResourceType.ImageResource, QUrl(resource_name), qimage)
            cells_html.append(
                "<td align='center' style='border:1px solid #ccc; padding:6px;'>"
                f"<div style='font-size:10px;'>{part.part_no} - {part.name}</div>"
                f"<img src='{resource_name}' width='160'/>"
                "</td>"
            )

        if not cells_html:
            self.error_label.setText("Could not generate any barcode images - nothing to print.")
            self.error_label.show()
            return

        rows_html = []
        for i in range(0, len(cells_html), _LABELS_PER_ROW):
            rows_html.append("<tr>" + "".join(cells_html[i:i + _LABELS_PER_ROW]) + "</tr>")
        html = "<table width='100%' cellspacing='4'>" + "".join(rows_html) + "</table>"

        document.setHtml(html)
        printer = QPrinter()
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            document.print(printer)
            if skipped:
                QMessageBox.warning(
                    self, "Some Labels Skipped",
                    "Printed, but these couldn't be encoded as a barcode:\n" + "\n".join(skipped),
                )
            self.accept()
