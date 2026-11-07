"""Purchase entry (new) + purchase history (list/view/cancel).

Part search loads the active catalog once per dialog open into a
QCompleter (MatchContains, case-insensitive) rather than querying the DB
per keystroke - simple and fast for a parts catalog of realistic size.
Matching tries barcode first, then part number, then the completer's
"part_no - name" label, so a barcode scanner's raw output (which has no
spaces/formatting) resolves the same as a typed search.
"""
from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCompleter,
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
from spare_parts.services import parts_service, purchase_service, suppliers_service
from spare_parts.ui.suppliers_page import SupplierDialog
from spare_parts.ui.widgets import NoScrollComboBox, NoScrollDoubleSpinBox, NoScrollSpinBox, trash_icon
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
        background-color: #e74c3c; color: white; border: none;
        border-radius: 4px; padding: 8px 16px; font-weight: bold;
    }
    QPushButton:hover { background-color: #c0392b; }
"""

_REMOVE_LINE_ICON_QSS = """
    QPushButton {
        background-color: #fdecea; color: #e74c3c; border: 1px solid #f5b7b1;
        border-radius: 13px; font-weight: bold; font-size: 13px; padding: 0px;
    }
    QPushButton:hover { background-color: #e74c3c; color: white; border-color: #e74c3c; }
    QPushButton:pressed { background-color: #c0392b; border-color: #c0392b; }
"""

_ITEM_COLUMNS = ["Part", "Qty", "Unit Cost", "Discount", "Line Total", ""]


class PurchaseDialog(QDialog):
    """New purchase entry, or a read-only view of a saved one (with a
    Cancel Purchase action if it's still POSTED)."""

    def __init__(
        self,
        purchase_id: int | None = None,
        parent=None,
        *,
        prefill_items: list[dict] | None = None,
        prefill_supplier_id: int | None = None,
    ):
        """prefill_items (new-purchase mode only): [{"part": <live SpPart>,
        "qty": <int>}, ...] - e.g. from Reports > Reorder Suggestions'
        "Create Purchase from Selected". Each part is added the same way
        _add_line_item already adds a scanned/searched part (defaulting
        cost to part.cost_price), then its qty spinner is overridden to
        the suggested quantity. prefill_supplier_id just pre-selects that
        supplier in the combo - it's still a required, editable field,
        same as always."""
        super().__init__(parent)
        self.purchase_id = purchase_id
        self.view_only = purchase_id is not None
        self.setWindowTitle("View Purchase" if self.view_only else "New Purchase")
        self.setMinimumSize(760, 520)
        self._saving = False
        self._dirty = False
        self._purchase_status = "POSTED"

        root = QVBoxLayout(self)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("Supplier *"))
        self.supplier_combo = NoScrollComboBox()
        self.supplier_combo.setEditable(True)
        self.supplier_combo.setInsertPolicy(NoScrollComboBox.InsertPolicy.NoInsert)
        header_row.addWidget(self.supplier_combo, 2)
        self.add_supplier_btn = QPushButton("+")
        self.add_supplier_btn.setFixedWidth(28)
        self.add_supplier_btn.setToolTip("Add new supplier")
        self.add_supplier_btn.setAutoDefault(False)
        self.add_supplier_btn.clicked.connect(self._on_add_supplier)
        header_row.addWidget(self.add_supplier_btn)

        header_row.addWidget(QLabel("Notes"))
        self.notes_input = QLineEdit()
        header_row.addWidget(self.notes_input, 2)
        root.addLayout(header_row)

        if not self.view_only:
            search_row = QHBoxLayout()
            self.part_search_input = QLineEdit()
            self.part_search_input.setPlaceholderText(
                "Scan barcode or search part no / name, then Enter..."
            )
            self.part_search_input.returnPressed.connect(self._on_part_search_enter)
            search_row.addWidget(self.part_search_input)
            root.addLayout(search_row)

        self.items_table = QTableWidget(0, len(_ITEM_COLUMNS))
        self.items_table.setHorizontalHeaderLabels(_ITEM_COLUMNS)
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.items_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.items_table.verticalHeader().setMinimumSectionSize(36)
        self.items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.items_table, 1)

        if not self.view_only:
            line_actions_row = QHBoxLayout()
            line_actions_row.addStretch(1)
            remove_line_btn = QPushButton("Remove Selected Line")
            remove_line_btn.setStyleSheet(_DANGER_BTN)
            remove_line_btn.setAutoDefault(False)
            remove_line_btn.clicked.connect(self._on_remove_selected_line)
            line_actions_row.addWidget(remove_line_btn)
            root.addLayout(line_actions_row)

        totals_row = QHBoxLayout()
        totals_row.addStretch(1)
        totals_row.addWidget(QLabel("Subtotal:"))
        self.subtotal_label = QLabel("0.00")
        self.subtotal_label.setStyleSheet("font-weight: bold;")
        totals_row.addWidget(self.subtotal_label)

        totals_row.addWidget(QLabel("  Discount:"))
        self.discount_spin = NoScrollDoubleSpinBox()
        self.discount_spin.setRange(0, 99_999_999)
        self.discount_spin.setDecimals(2)
        self.discount_spin.valueChanged.connect(self._recalc_totals)
        self.discount_spin.setFixedWidth(110)
        totals_row.addWidget(self.discount_spin)

        totals_row.addWidget(QLabel("  Total:"))
        self.total_label = QLabel("0.00")
        self.total_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #2c3e50;")
        totals_row.addWidget(self.total_label)

        totals_row.addWidget(QLabel("  Paid:"))
        self.paid_spin = NoScrollDoubleSpinBox()
        self.paid_spin.setRange(0, 99_999_999)
        self.paid_spin.setDecimals(2)
        self.paid_spin.valueChanged.connect(self._recalc_totals)
        self.paid_spin.setFixedWidth(110)
        totals_row.addWidget(self.paid_spin)

        totals_row.addWidget(QLabel("  Due:"))
        self.due_label = QLabel("0.00")
        self.due_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
        totals_row.addWidget(self.due_label)
        root.addLayout(totals_row)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        root.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("Close" if self.view_only else "Cancel")
        close_btn.setStyleSheet(_RESET_BTN)
        close_btn.setAutoDefault(False)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        if self.view_only:
            self.cancel_purchase_btn = QPushButton("Cancel This Purchase")
            self.cancel_purchase_btn.setStyleSheet(_DANGER_BTN)
            self.cancel_purchase_btn.setAutoDefault(False)
            self.cancel_purchase_btn.clicked.connect(self._on_cancel_purchase)
            btn_row.addWidget(self.cancel_purchase_btn)
        else:
            self.save_btn = QPushButton("Save (Ctrl+S)")
            self.save_btn.setStyleSheet(_PRIMARY_BTN)
            # Enter must never silently save/remove/click something while
            # the user is mid-entry in the item table - Ctrl+S is the one
            # deliberate way to save.
            self.save_btn.setAutoDefault(False)
            self.save_btn.clicked.connect(self._on_save)
            btn_row.addWidget(self.save_btn)
        root.addLayout(btn_row)

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.reject)
        if not self.view_only:
            QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_save)

        self._reload_suppliers()
        self._parts_by_barcode: dict[str, object] = {}
        self._parts_by_part_no: dict[str, object] = {}
        self._parts_completer_map: dict[str, object] = {}
        if not self.view_only:
            self._reload_parts_lookup()
            self.part_search_input.setFocus()

        if self.view_only:
            self._load_purchase(purchase_id)
            self._set_view_only_mode()
        elif prefill_items:
            for entry in prefill_items:
                part = entry["part"]
                qty = int(entry.get("qty") or 1)
                self._add_line_item(part)
                row = self.items_table.rowCount() - 1
                qty_spin = self.items_table.cellWidget(row, 1)
                if qty_spin is not None:
                    qty_spin.setValue(max(1, qty))
            # _add_line_item already marked _dirty=True for each row above -
            # correct: these are real unsaved line items, so Cancel should
            # still prompt "discard this purchase?" same as any manual entry.
            if prefill_supplier_id:
                idx = self.supplier_combo.findData(prefill_supplier_id)
                if idx >= 0:
                    self.supplier_combo.setCurrentIndex(idx)

    # --- lookups -----------------------------------------------------------

    def _reload_suppliers(self) -> None:
        db = get_spare_session()
        try:
            self.supplier_combo.clear()
            self.supplier_combo.addItem("", None)
            for supplier in suppliers_service.list_suppliers(db, active_only=True):
                self.supplier_combo.addItem(supplier.name, supplier.id)
        finally:
            db.close()

    def _reload_parts_lookup(self) -> None:
        db = get_spare_session()
        try:
            parts = parts_service.search_parts(db, active_only=True)
            self._parts_by_barcode = {p.barcode.upper(): p for p in parts if p.barcode}
            self._parts_by_part_no = {p.part_no.upper(): p for p in parts}
            self._parts_completer_map = {f"{p.part_no} - {p.name}": p for p in parts}
            completer = QCompleter(list(self._parts_completer_map.keys()), self)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            completer.activated.connect(self._on_part_completer_activated)
            self.part_search_input.setCompleter(completer)
        finally:
            db.close()

    def _on_add_supplier(self) -> None:
        dlg = SupplierDialog(parent=self)
        if dlg.exec():
            self._reload_suppliers()
            self.supplier_combo.setCurrentIndex(self.supplier_combo.count() - 1)

    # --- part search / line items ------------------------------------------

    def _on_part_completer_activated(self, text: str) -> None:
        part = self._parts_completer_map.get(text)
        if part:
            self._add_line_item(part)
            self.part_search_input.clear()

    def _on_part_search_enter(self) -> None:
        text = self.part_search_input.text().strip()
        if not text:
            return
        key = text.upper()
        part = self._parts_by_barcode.get(key) or self._parts_by_part_no.get(key)
        if not part:
            # Fall back to a contains-match against "part_no - name" labels
            # (same matching the completer popup offers), in case the user
            # typed a partial name rather than an exact code.
            matches = [p for label, p in self._parts_completer_map.items() if key in label.upper()]
            part = matches[0] if len(matches) == 1 else None
        if not part:
            QMessageBox.warning(self, "Part Not Found", f"No active part matches '{text}'.")
            return
        self._add_line_item(part)
        self.part_search_input.clear()

    def _find_row_for_part(self, part_id: int) -> int | None:
        for row in range(self.items_table.rowCount()):
            part_item = self.items_table.item(row, 0)
            if part_item and part_item.data(Qt.ItemDataRole.UserRole) == part_id:
                return row
        return None

    def _add_line_item(self, part) -> None:
        existing_row = self._find_row_for_part(part.id)
        if existing_row is not None:
            # Scanning/searching the same part again means "one more of
            # this", not a second line for it.
            qty_widget = self.items_table.cellWidget(existing_row, 1)
            qty_widget.setValue(qty_widget.value() + 1)
            self._dirty = True
            self.items_table.setCurrentCell(existing_row, 1)
            qty_widget.setFocus()
            qty_widget.selectAll()
            return

        row = self.items_table.rowCount()
        self.items_table.insertRow(row)

        part_item = QTableWidgetItem(f"{part.part_no} - {part.name}")
        part_item.setFlags(part_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        part_item.setData(Qt.ItemDataRole.UserRole, part.id)
        self.items_table.setItem(row, 0, part_item)

        qty_spin = NoScrollSpinBox()
        qty_spin.setRange(1, 1_000_000)
        qty_spin.setValue(1)
        qty_spin.valueChanged.connect(self._recalc_totals)
        self.items_table.setCellWidget(row, 1, qty_spin)

        cost_spin = NoScrollDoubleSpinBox()
        cost_spin.setRange(0, 99_999_999)
        cost_spin.setDecimals(2)
        cost_spin.setValue(float(part.cost_price or 0))
        cost_spin.valueChanged.connect(self._recalc_totals)
        self.items_table.setCellWidget(row, 2, cost_spin)

        discount_spin = NoScrollDoubleSpinBox()
        discount_spin.setRange(0, 99_999_999)
        discount_spin.setDecimals(2)
        discount_spin.valueChanged.connect(self._recalc_totals)
        self.items_table.setCellWidget(row, 3, discount_spin)

        line_total_item = QTableWidgetItem("0.00")
        line_total_item.setFlags(line_total_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.items_table.setItem(row, 4, line_total_item)

        remove_btn = QPushButton()
        remove_btn.setIcon(trash_icon(14))
        remove_btn.setIconSize(QSize(14, 14))
        remove_btn.setFixedSize(26, 26)
        remove_btn.setToolTip("Remove this line")
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet(_REMOVE_LINE_ICON_QSS)
        remove_btn.setAutoDefault(False)
        remove_btn.clicked.connect(lambda: self._remove_line_item(remove_btn))
        self.items_table.setCellWidget(row, 5, remove_btn)

        self._dirty = True
        self._recalc_totals()
        qty_spin.setFocus()
        qty_spin.selectAll()

    def _remove_line_item(self, btn) -> None:
        for row in range(self.items_table.rowCount()):
            if self.items_table.cellWidget(row, 5) is btn:
                self.items_table.removeRow(row)
                break
        self._recalc_totals()

    def _on_remove_selected_line(self) -> None:
        """Scroll-proof alternative to the per-row "x" button: that button
        sits in the table's last column and can end up squeezed against -
        or past - the viewport edge once enough lines are added to trigger
        a vertical scrollbar, making it hard or impossible to reach. This
        button works on whichever row is currently selected/focused, no
        matter how the table is scrolled."""
        row = self.items_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "No Line Selected",
                "Click a line in the table first, then click Remove Selected Line.",
            )
            return
        self.items_table.removeRow(row)
        self._recalc_totals()

    def _recalc_totals(self) -> None:
        subtotal = Decimal("0")
        for row in range(self.items_table.rowCount()):
            qty_widget = self.items_table.cellWidget(row, 1)
            cost_widget = self.items_table.cellWidget(row, 2)
            discount_widget = self.items_table.cellWidget(row, 3)
            if not (qty_widget and cost_widget and discount_widget):
                continue
            qty = qty_widget.value()
            unit_cost = Decimal(str(cost_widget.value()))
            discount = Decimal(str(discount_widget.value()))
            line_total = (unit_cost * qty) - discount
            if line_total < 0:
                line_total = Decimal("0")
            item = self.items_table.item(row, 4)
            if item:
                item.setText(f"{line_total:,.2f}")
            subtotal += line_total

        self.subtotal_label.setText(f"{subtotal:,.2f}")
        header_discount = Decimal(str(self.discount_spin.value()))
        total = subtotal - header_discount
        if total < 0:
            total = Decimal("0")
        self.total_label.setText(f"{total:,.2f}")
        paid = Decimal(str(self.paid_spin.value()))
        due = total - paid
        self.due_label.setText(f"{due:,.2f}")

    # --- view mode -----------------------------------------------------------

    def _load_purchase(self, purchase_id: int) -> None:
        db = get_spare_session()
        try:
            purchase = purchase_service.get_purchase(db, purchase_id)
            if not purchase:
                QMessageBox.critical(self, "Error", f"Purchase id={purchase_id} not found.")
                self.reject()
                return
            idx = self.supplier_combo.findData(purchase.supplier_id)
            if idx >= 0:
                self.supplier_combo.setCurrentIndex(idx)
            self.notes_input.setText(purchase.notes or "")
            self.discount_spin.blockSignals(True)
            self.discount_spin.setValue(float(purchase.discount or 0))
            self.discount_spin.blockSignals(False)
            self.paid_spin.blockSignals(True)
            self.paid_spin.setValue(float(purchase.paid or 0))
            self.paid_spin.blockSignals(False)

            for item in purchase.items:
                part = item.part
                label = f"{part.part_no} - {part.name}" if part else f"(deleted part id={item.part_id})"
                row = self.items_table.rowCount()
                self.items_table.insertRow(row)

                part_cell = QTableWidgetItem(label)
                part_cell.setFlags(part_cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.items_table.setItem(row, 0, part_cell)

                qty_spin = NoScrollSpinBox()
                qty_spin.setRange(1, 1_000_000)
                qty_spin.setValue(item.qty)
                qty_spin.setEnabled(False)
                self.items_table.setCellWidget(row, 1, qty_spin)

                cost_spin = NoScrollDoubleSpinBox()
                cost_spin.setRange(0, 99_999_999)
                cost_spin.setDecimals(2)
                cost_spin.setValue(float(item.unit_cost))
                cost_spin.setEnabled(False)
                self.items_table.setCellWidget(row, 2, cost_spin)

                discount_spin = NoScrollDoubleSpinBox()
                discount_spin.setRange(0, 99_999_999)
                discount_spin.setDecimals(2)
                discount_spin.setValue(float(item.discount or 0))
                discount_spin.setEnabled(False)
                self.items_table.setCellWidget(row, 3, discount_spin)

                total_cell = QTableWidgetItem(f"{float(item.line_total):,.2f}")
                total_cell.setFlags(total_cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.items_table.setItem(row, 4, total_cell)

            self.subtotal_label.setText(f"{float(purchase.subtotal):,.2f}")
            self.total_label.setText(f"{float(purchase.total):,.2f}")
            self.due_label.setText(f"{float(purchase.due):,.2f}")
            self._purchase_status = purchase.status
        finally:
            db.close()

    def _set_view_only_mode(self) -> None:
        self.supplier_combo.setEnabled(False)
        self.notes_input.setReadOnly(True)
        self.discount_spin.setEnabled(False)
        self.paid_spin.setEnabled(False)
        self.add_supplier_btn.setEnabled(False)
        if hasattr(self, "cancel_purchase_btn"):
            self.cancel_purchase_btn.setEnabled(self._purchase_status == "POSTED")
            if self._purchase_status != "POSTED":
                self.cancel_purchase_btn.setText(f"({self._purchase_status})")

    def _on_cancel_purchase(self) -> None:
        reason, ok = ("", True)
        confirm = QMessageBox.question(
            self, "Cancel Purchase",
            "Reverse this purchase's stock and mark it CANCELLED?\n"
            "This cannot be undone - you would need to enter a new purchase.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        db = get_spare_session()
        try:
            purchase_service.cancel_purchase(db, self.purchase_id)
        except SparePartsValidationError as e:
            QMessageBox.warning(self, "Cannot Cancel", str(e))
            return
        finally:
            db.close()
        self.accept()

    # --- save ---------------------------------------------------------------

    def _on_save(self) -> None:
        if self._saving:
            return
        self._saving = True
        self.save_btn.setEnabled(False)
        self.error_label.hide()
        try:
            supplier_id = self.supplier_combo.currentData()
            if not supplier_id:
                raise SparePartsValidationError("Select a supplier.")

            items = []
            for row in range(self.items_table.rowCount()):
                part_item = self.items_table.item(row, 0)
                qty_widget = self.items_table.cellWidget(row, 1)
                cost_widget = self.items_table.cellWidget(row, 2)
                discount_widget = self.items_table.cellWidget(row, 3)
                items.append(dict(
                    part_id=part_item.data(Qt.ItemDataRole.UserRole),
                    qty=qty_widget.value(),
                    unit_cost=cost_widget.value(),
                    discount=discount_widget.value(),
                ))

            db = get_spare_session()
            try:
                purchase = purchase_service.create_purchase(
                    db,
                    supplier_id=supplier_id,
                    items=items,
                    discount=self.discount_spin.value(),
                    paid=self.paid_spin.value(),
                    notes=self.notes_input.text(),
                )
            finally:
                db.close()
            self._dirty = False
            logger.info(f"Saved purchase {purchase.purchase_no} via dialog.")
            self.accept()
        except SparePartsValidationError as e:
            self.error_label.setText(str(e))
            self.error_label.show()
        except Exception as e:
            logger.error(f"Unexpected error saving purchase: {e}", exc_info=True)
            self.error_label.setText(f"Unexpected error: {e}")
            self.error_label.show()
        finally:
            self._saving = False
            self.save_btn.setEnabled(True)

    def reject(self) -> None:
        if not self.view_only and self._dirty:
            confirm = QMessageBox.question(
                self, "Discard Purchase?",
                "You have unsaved line items. Discard this purchase?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
        super().reject()


class PurchasesPage(QWidget):
    """Purchase history - search/filter + new/view/cancel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QLabel("Purchases")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(header)

        toolbar = QHBoxLayout()
        self.supplier_filter = NoScrollComboBox()
        self.supplier_filter.addItem("All Suppliers", None)
        self.supplier_filter.currentIndexChanged.connect(self._reload)
        toolbar.addWidget(self.supplier_filter, 1)

        self.status_filter = NoScrollComboBox()
        self.status_filter.addItems(["All", "POSTED", "CANCELLED"])
        self.status_filter.currentIndexChanged.connect(self._reload)
        toolbar.addWidget(self.status_filter)
        toolbar.addStretch(1)

        new_btn = QPushButton("+ New Purchase (Ctrl+N)")
        new_btn.setStyleSheet(_PRIMARY_BTN)
        new_btn.clicked.connect(self._on_new_clicked)
        toolbar.addWidget(new_btn)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Purchase No.", "Supplier", "Date", "Total", "Paid", "Due", "Status"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_view_clicked)
        layout.addWidget(self.table, 1)

        action_row = QHBoxLayout()
        view_btn = QPushButton("View Selected")
        view_btn.setStyleSheet(_RESET_BTN)
        view_btn.clicked.connect(self._on_view_clicked)
        action_row.addWidget(view_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_new_clicked)

        self._reload_suppliers_filter()
        self._reload()

    def _reload_suppliers_filter(self) -> None:
        db = get_spare_session()
        try:
            current = self.supplier_filter.currentData()
            self.supplier_filter.blockSignals(True)
            self.supplier_filter.clear()
            self.supplier_filter.addItem("All Suppliers", None)
            for supplier in suppliers_service.list_suppliers(db, active_only=False):
                self.supplier_filter.addItem(supplier.name, supplier.id)
            if current is not None:
                idx = self.supplier_filter.findData(current)
                if idx >= 0:
                    self.supplier_filter.setCurrentIndex(idx)
            self.supplier_filter.blockSignals(False)
        finally:
            db.close()

    def _reload(self) -> None:
        db = get_spare_session()
        try:
            status = self.status_filter.currentText()
            purchases = purchase_service.list_purchases(
                db,
                supplier_id=self.supplier_filter.currentData(),
                status=None if status == "All" else status,
            )
            self.table.setRowCount(len(purchases))
            for row, purchase in enumerate(purchases):
                self.table.setItem(row, 0, QTableWidgetItem(purchase.purchase_no))
                self.table.setItem(row, 1, QTableWidgetItem(purchase.supplier.name if purchase.supplier else ""))
                self.table.setItem(row, 2, QTableWidgetItem(purchase.purchase_date.strftime("%Y-%m-%d")))
                self.table.setItem(row, 3, QTableWidgetItem(f"{float(purchase.total):,.2f}"))
                self.table.setItem(row, 4, QTableWidgetItem(f"{float(purchase.paid):,.2f}"))
                self.table.setItem(row, 5, QTableWidgetItem(f"{float(purchase.due):,.2f}"))
                status_item = QTableWidgetItem(purchase.status)
                if purchase.status == "CANCELLED":
                    status_item.setForeground(Qt.GlobalColor.gray)
                self.table.setItem(row, 6, status_item)
                self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, purchase.id)
        finally:
            db.close()

    def _selected_purchase_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_new_clicked(self) -> None:
        dlg = PurchaseDialog(parent=self)
        if dlg.exec():
            self._reload_suppliers_filter()
            self._reload()

    def _on_view_clicked(self) -> None:
        purchase_id = self._selected_purchase_id()
        if not purchase_id:
            QMessageBox.information(self, "No Selection", "Select a purchase first.")
            return
        dlg = PurchaseDialog(purchase_id=purchase_id, parent=self)
        if dlg.exec():
            self._reload()
