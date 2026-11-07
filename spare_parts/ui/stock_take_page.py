"""Stock Take: a formal physical-count reconciliation workflow, built
entirely on spare_parts/services/stock_take_service.py. A list of past
stock takes + "+ New Stock Take" (pick scope, snapshot current stock)
+ a detail view (enter counted quantities while DRAFT, Post once done).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spare_parts.db.base import get_spare_session
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import parts_service, stock_take_service
from spare_parts.ui.widgets import NoScrollComboBox
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

_DANGER_BTN = """
    QPushButton {
        background-color: #fdecea; color: #e74c3c; border: 1px solid #f5c6cb;
        border-radius: 4px; padding: 8px 16px;
    }
    QPushButton:hover { background-color: #fadbd8; }
"""


class _NewStockTakeDialog(QDialog):
    """Pick scope (category/brand/search filter - or leave all blank for
    every active part) and create a new DRAFT stock take."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Stock Take")
        self.setMinimumWidth(420)
        self.new_stock_take_id: int | None = None

        root = QVBoxLayout(self)
        info = QLabel(
            "Choose which parts to count. Leave everything blank to count "
            "every active part. Current stock is snapshotted now - counted "
            "quantities are entered afterward, over however long the count "
            "actually takes."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #6c757d;")
        root.addWidget(info)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Category"))
        self.category_combo = NoScrollComboBox()
        self.category_combo.addItem("All Categories", None)
        row1.addWidget(self.category_combo, 1)
        row1.addWidget(QLabel("Brand"))
        self.brand_combo = NoScrollComboBox()
        self.brand_combo.addItem("All Brands", None)
        row1.addWidget(self.brand_combo, 1)
        root.addLayout(row1)

        root.addWidget(QLabel("Search (part no/name/barcode)"))
        self.query_input = QLineEdit()
        root.addWidget(self.query_input)

        root.addWidget(QLabel("Notes"))
        self.notes_input = QLineEdit()
        root.addWidget(self.notes_input)

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
        create_btn = QPushButton("Create")
        create_btn.setStyleSheet(_PRIMARY_BTN)
        create_btn.clicked.connect(self._on_create_clicked)
        btn_row.addWidget(create_btn)
        root.addLayout(btn_row)

        self._load_filters()

    def _load_filters(self) -> None:
        db = get_spare_session()
        try:
            for cat in parts_service.list_categories(db):
                self.category_combo.addItem(cat.name, cat.id)
            for brand in parts_service.list_brands(db):
                self.brand_combo.addItem(brand.name, brand.id)
        finally:
            db.close()

    def _on_create_clicked(self) -> None:
        self.error_label.hide()
        db = get_spare_session()
        try:
            stock_take = stock_take_service.create_stock_take(
                db,
                category_id=self.category_combo.currentData(),
                brand_id=self.brand_combo.currentData(),
                query=self.query_input.text(),
                notes=self.notes_input.text(),
            )
            self.new_stock_take_id = stock_take.id
        except SparePartsValidationError as e:
            self.error_label.setText(str(e))
            self.error_label.show()
            return
        except Exception as e:
            logger.error(f"Unexpected error creating stock take: {e}", exc_info=True)
            self.error_label.setText(f"Unexpected error: {e}")
            self.error_label.show()
            return
        finally:
            db.close()
        self.accept()


class StockTakeDetailDialog(QDialog):
    """Enter counted quantities (while DRAFT) and Post, or view a
    POSTED stock take read-only."""

    def __init__(self, stock_take_id: int, parent=None):
        super().__init__(parent)
        self.stock_take_id = stock_take_id
        self.setMinimumSize(640, 480)
        self._posting = False

        root = QVBoxLayout(self)
        self.header_label = QLabel("")
        self.header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        root.addWidget(self.header_label)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Part", "System Qty", "Counted Qty", "Variance"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        root.addWidget(self.table, 1)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        root.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        self.discard_btn = QPushButton("Discard")
        self.discard_btn.setStyleSheet(_DANGER_BTN)
        self.discard_btn.clicked.connect(self._on_discard_clicked)
        btn_row.addWidget(self.discard_btn)
        btn_row.addStretch(1)
        self.save_btn = QPushButton("Save Counts")
        self.save_btn.setStyleSheet(_RESET_BTN)
        self.save_btn.clicked.connect(self._on_save_counts_clicked)
        btn_row.addWidget(self.save_btn)
        self.post_btn = QPushButton("Post")
        self.post_btn.setStyleSheet(_PRIMARY_BTN)
        self.post_btn.clicked.connect(self._on_post_clicked)
        btn_row.addWidget(self.post_btn)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(_RESET_BTN)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        self._row_item_ids: list[int] = []
        self._reload()

    def _reload(self) -> None:
        db = get_spare_session()
        try:
            stock_take = stock_take_service.get_stock_take(db, self.stock_take_id)
            if not stock_take:
                QMessageBox.critical(self, "Not Found", "Stock take not found.")
                self.reject()
                return
            is_draft = stock_take.status == "DRAFT"
            self.setWindowTitle(f"Stock Take - {stock_take.take_no}")
            self.header_label.setText(
                f"{stock_take.take_no} - {stock_take.take_date.strftime('%Y-%m-%d %H:%M')} - "
                f"Status: {stock_take.status}"
            )

            items = stock_take.items
            self._row_item_ids = [item.id for item in items]
            self.table.setRowCount(len(items))
            for row, item in enumerate(items):
                part = item.part
                self.table.setItem(row, 0, QTableWidgetItem(f"{part.part_no} - {part.name}" if part else f"Part #{item.part_id}"))
                self.table.setItem(row, 1, QTableWidgetItem(str(item.system_qty)))

                counted_edit = QLineEdit()
                counted_edit.setText("" if item.counted_qty is None else str(item.counted_qty))
                counted_edit.setReadOnly(not is_draft)
                counted_edit.setPlaceholderText("Not counted")
                self.table.setCellWidget(row, 2, counted_edit)

                if item.counted_qty is not None:
                    variance = item.counted_qty - item.system_qty
                    variance_item = QTableWidgetItem(f"{variance:+d}")
                else:
                    variance_item = QTableWidgetItem("")
                self.table.setItem(row, 3, variance_item)

            self.discard_btn.setVisible(is_draft)
            self.save_btn.setVisible(is_draft)
            self.post_btn.setVisible(is_draft)
        finally:
            db.close()

    def _save_counts(self, db) -> None:
        """Pushes every row's QLineEdit text into
        stock_take_service.update_counted_qty - blank clears it back to
        "not counted", a valid non-negative int sets it. Raises
        SparePartsValidationError on the first invalid entry."""
        for row, item_id in enumerate(self._row_item_ids):
            counted_edit = self.table.cellWidget(row, 2)
            text = counted_edit.text().strip() if counted_edit else ""
            if not text:
                stock_take_service.update_counted_qty(db, item_id, None)
                continue
            try:
                counted_qty = int(text)
            except ValueError:
                part_name = self.table.item(row, 0).text()
                raise SparePartsValidationError(f"'{text}' is not a valid whole number for {part_name}.")
            stock_take_service.update_counted_qty(db, item_id, counted_qty)

    def _on_save_counts_clicked(self) -> None:
        self.error_label.hide()
        db = get_spare_session()
        try:
            self._save_counts(db)
        except SparePartsValidationError as e:
            self.error_label.setText(str(e))
            self.error_label.show()
            return
        finally:
            db.close()
        self._reload()

    def _on_post_clicked(self) -> None:
        if self._posting:
            return
        self.error_label.hide()
        confirm = QMessageBox.question(
            self, "Post Stock Take?",
            "This will adjust stock for every counted part and lock this "
            "stock take from further edits. Continue?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._posting = True
        self.post_btn.setEnabled(False)
        db = get_spare_session()
        try:
            self._save_counts(db)
            result = stock_take_service.post_stock_take(db, self.stock_take_id)
        except SparePartsValidationError as e:
            self.error_label.setText(str(e))
            self.error_label.show()
            self._posting = False
            self.post_btn.setEnabled(True)
            db.close()
            return
        except Exception as e:
            logger.error(f"Unexpected error posting stock take: {e}", exc_info=True)
            self.error_label.setText(f"Unexpected error: {e}")
            self.error_label.show()
            self._posting = False
            self.post_btn.setEnabled(True)
            db.close()
            return
        finally:
            db.close()

        self._posting = False
        self.post_btn.setEnabled(True)
        message = f"Posted. {result['adjusted_count']} part(s) adjusted."
        if result["drift_warnings"]:
            message += "\n\nWarnings:\n" + "\n".join(result["drift_warnings"])
            QMessageBox.warning(self, "Stock Take Posted (with warnings)", message)
        else:
            QMessageBox.information(self, "Stock Take Posted", message)
        self._reload()

    def _on_discard_clicked(self) -> None:
        confirm = QMessageBox.question(
            self, "Discard Stock Take?",
            "This DRAFT stock take and its counts will be permanently deleted. Continue?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        db = get_spare_session()
        try:
            stock_take_service.cancel_stock_take(db, self.stock_take_id)
        except SparePartsValidationError as e:
            QMessageBox.warning(self, "Could Not Discard", str(e))
            return
        finally:
            db.close()
        self.accept()


class StockTakePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QLabel("Stock Take")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(header)

        toolbar = QHBoxLayout()
        toolbar.addStretch(1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(_RESET_BTN)
        refresh_btn.clicked.connect(self.reload)
        toolbar.addWidget(refresh_btn)
        new_btn = QPushButton("+ New Stock Take")
        new_btn.setStyleSheet(_PRIMARY_BTN)
        new_btn.clicked.connect(self._on_new_clicked)
        toolbar.addWidget(new_btn)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Take No.", "Date", "Status", "Notes"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_open_clicked)
        layout.addWidget(self.table, 1)

        bottom_row = QHBoxLayout()
        open_btn = QPushButton("Open Selected")
        open_btn.setStyleSheet(_RESET_BTN)
        open_btn.clicked.connect(self._on_open_clicked)
        bottom_row.addWidget(open_btn)
        bottom_row.addStretch(1)
        layout.addLayout(bottom_row)

        self.reload()

    def reload(self) -> None:
        db = get_spare_session()
        try:
            stock_takes = stock_take_service.list_stock_takes(db)
            self.table.setRowCount(len(stock_takes))
            for row, take in enumerate(stock_takes):
                no_item = QTableWidgetItem(take.take_no)
                no_item.setData(Qt.ItemDataRole.UserRole, take.id)
                self.table.setItem(row, 0, no_item)
                self.table.setItem(row, 1, QTableWidgetItem(take.take_date.strftime("%Y-%m-%d %H:%M")))
                self.table.setItem(row, 2, QTableWidgetItem(take.status))
                self.table.setItem(row, 3, QTableWidgetItem(take.notes or ""))
        finally:
            db.close()

    def _selected_stock_take_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_new_clicked(self) -> None:
        dlg = _NewStockTakeDialog(parent=self)
        if dlg.exec() and dlg.new_stock_take_id:
            self.reload()
            detail = StockTakeDetailDialog(dlg.new_stock_take_id, parent=self)
            detail.exec()
            self.reload()

    def _on_open_clicked(self) -> None:
        stock_take_id = self._selected_stock_take_id()
        if not stock_take_id:
            QMessageBox.information(self, "No Selection", "Select a stock take first.")
            return
        dlg = StockTakeDetailDialog(stock_take_id, parent=self)
        dlg.exec()
        self.reload()
