"""Returns: sale returns (stock back in from a customer) and purchase
returns (stock back out to a supplier). Each sub-tab's "+ New Return"
flow looks the original sale/purchase up by its number first, then opens
a dialog listing its lines with a returnable-quantity spinner per line -
this avoids re-implementing a second part-search/line-item editor, since
a return only ever reverses an existing, already-priced line.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
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
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spare_parts.db.base import get_spare_session
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import purchase_service, returns_service, sales_service
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


def _already_returned_map(db, sale_id=None, purchase_id=None) -> dict[int, int]:
    """Returns {original_item_id: qty_already_returned} so the dialog can
    show/limit the remaining returnable quantity per line."""
    if sale_id is not None:
        returns = returns_service.list_sale_returns(db, sale_id=sale_id)
        totals: dict[int, int] = {}
        for ret in returns:
            for ri in ret.items:
                totals[ri.sale_item_id] = totals.get(ri.sale_item_id, 0) + ri.qty
        return totals
    returns = returns_service.list_purchase_returns(db, purchase_id=purchase_id)
    totals = {}
    for ret in returns:
        for ri in ret.items:
            totals[ri.purchase_item_id] = totals.get(ri.purchase_item_id, 0) + ri.qty
    return totals


class SaleReturnDialog(QDialog):
    """Lists every line of a specific POSTED sale with a 0..returnable
    quantity spinner; lines left at 0 are simply not returned."""

    def __init__(self, sale_id: int, parent=None):
        super().__init__(parent)
        self.sale_id = sale_id
        self.setWindowTitle("New Sale Return")
        self.setMinimumSize(640, 420)
        self._saving = False
        self._row_meta: list[dict] = []

        root = QVBoxLayout(self)
        self.header_label = QLabel("")
        self.header_label.setStyleSheet("font-weight: bold;")
        root.addWidget(self.header_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Part", "Sold Qty", "Already Returned", "Returnable", "Qty To Return"])
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
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_RESET_BTN)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        self.save_btn = QPushButton("Save Return (Ctrl+S)")
        self.save_btn.setStyleSheet(_PRIMARY_BTN)
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)
        root.addLayout(btn_row)

        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_save)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.reject)

        self._load_sale()

    def _load_sale(self) -> None:
        db = get_spare_session()
        try:
            sale = sales_service.get_sale(db, self.sale_id)
            if not sale:
                QMessageBox.critical(self, "Error", f"Sale id={self.sale_id} not found.")
                self.reject()
                return
            if sale.status != "POSTED":
                QMessageBox.warning(self, "Not Returnable", "Only a POSTED sale can be returned.")
                self.reject()
                return
            self.header_label.setText(
                f"Sale {sale.sale_no} - {sale.customer.name if sale.customer else 'Walk-in'} - "
                f"{sale.sale_date.strftime('%Y-%m-%d')}"
            )
            already_returned = _already_returned_map(db, sale_id=self.sale_id)

            self.table.setRowCount(len(sale.items))
            for row, item in enumerate(sale.items):
                part_name = item.part.name if item.part else f"Part #{item.part_id}"
                already = already_returned.get(item.id, 0)
                returnable = item.qty - already

                self.table.setItem(row, 0, QTableWidgetItem(part_name))
                self.table.setItem(row, 1, QTableWidgetItem(str(item.qty)))
                self.table.setItem(row, 2, QTableWidgetItem(str(already)))
                self.table.setItem(row, 3, QTableWidgetItem(str(returnable)))

                spin = NoScrollSpinBox()
                spin.setRange(0, max(0, returnable))
                spin.setValue(0)
                spin.setEnabled(returnable > 0)
                self.table.setCellWidget(row, 4, spin)

                self._row_meta.append(dict(sale_item_id=item.id, returnable=returnable))
        finally:
            db.close()

    def _on_save(self) -> None:
        if self._saving:
            return
        self._saving = True
        self.save_btn.setEnabled(False)
        self.error_label.hide()
        try:
            items = []
            for row, meta in enumerate(self._row_meta):
                spin = self.table.cellWidget(row, 4)
                qty = spin.value() if spin else 0
                if qty > 0:
                    items.append(dict(sale_item_id=meta["sale_item_id"], qty=qty))
            if not items:
                raise SparePartsValidationError("Enter a quantity to return for at least one line.")

            db = get_spare_session()
            try:
                sale_return = returns_service.create_sale_return(db, sale_id=self.sale_id, items=items)
            finally:
                db.close()
            logger.info(f"Saved sale return {sale_return.return_no} via dialog.")
            self.accept()
        except SparePartsValidationError as e:
            self.error_label.setText(str(e))
            self.error_label.show()
        except Exception as e:
            logger.error(f"Unexpected error saving sale return: {e}", exc_info=True)
            self.error_label.setText(f"Unexpected error: {e}")
            self.error_label.show()
        finally:
            self._saving = False
            self.save_btn.setEnabled(True)


class PurchaseReturnDialog(QDialog):
    """Same shape as SaleReturnDialog, for a POSTED purchase sent back to
    its supplier."""

    def __init__(self, purchase_id: int, parent=None):
        super().__init__(parent)
        self.purchase_id = purchase_id
        self.setWindowTitle("New Purchase Return")
        self.setMinimumSize(640, 420)
        self._saving = False
        self._row_meta: list[dict] = []

        root = QVBoxLayout(self)
        self.header_label = QLabel("")
        self.header_label.setStyleSheet("font-weight: bold;")
        root.addWidget(self.header_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Part", "Purchased Qty", "Already Returned", "Returnable", "Qty To Return"])
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
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_RESET_BTN)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        self.save_btn = QPushButton("Save Return (Ctrl+S)")
        self.save_btn.setStyleSheet(_PRIMARY_BTN)
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)
        root.addLayout(btn_row)

        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_save)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.reject)

        self._load_purchase()

    def _load_purchase(self) -> None:
        db = get_spare_session()
        try:
            purchase = purchase_service.get_purchase(db, self.purchase_id)
            if not purchase:
                QMessageBox.critical(self, "Error", f"Purchase id={self.purchase_id} not found.")
                self.reject()
                return
            if purchase.status != "POSTED":
                QMessageBox.warning(self, "Not Returnable", "Only a POSTED purchase can be returned.")
                self.reject()
                return
            self.header_label.setText(
                f"Purchase {purchase.purchase_no} - "
                f"{purchase.supplier.name if purchase.supplier else ''} - "
                f"{purchase.purchase_date.strftime('%Y-%m-%d')}"
            )
            already_returned = _already_returned_map(db, purchase_id=self.purchase_id)

            self.table.setRowCount(len(purchase.items))
            for row, item in enumerate(purchase.items):
                part_name = item.part.name if item.part else f"Part #{item.part_id}"
                already = already_returned.get(item.id, 0)
                returnable = item.qty - already

                self.table.setItem(row, 0, QTableWidgetItem(part_name))
                self.table.setItem(row, 1, QTableWidgetItem(str(item.qty)))
                self.table.setItem(row, 2, QTableWidgetItem(str(already)))
                self.table.setItem(row, 3, QTableWidgetItem(str(returnable)))

                spin = NoScrollSpinBox()
                spin.setRange(0, max(0, returnable))
                spin.setValue(0)
                spin.setEnabled(returnable > 0)
                self.table.setCellWidget(row, 4, spin)

                self._row_meta.append(dict(purchase_item_id=item.id, returnable=returnable))
        finally:
            db.close()

    def _on_save(self) -> None:
        if self._saving:
            return
        self._saving = True
        self.save_btn.setEnabled(False)
        self.error_label.hide()
        try:
            items = []
            for row, meta in enumerate(self._row_meta):
                spin = self.table.cellWidget(row, 4)
                qty = spin.value() if spin else 0
                if qty > 0:
                    items.append(dict(purchase_item_id=meta["purchase_item_id"], qty=qty))
            if not items:
                raise SparePartsValidationError("Enter a quantity to return for at least one line.")

            db = get_spare_session()
            try:
                purchase_return = returns_service.create_purchase_return(
                    db, purchase_id=self.purchase_id, items=items
                )
            finally:
                db.close()
            logger.info(f"Saved purchase return {purchase_return.return_no} via dialog.")
            self.accept()
        except SparePartsValidationError as e:
            self.error_label.setText(str(e))
            self.error_label.show()
        except Exception as e:
            logger.error(f"Unexpected error saving purchase return: {e}", exc_info=True)
            self.error_label.setText(f"Unexpected error: {e}")
            self.error_label.show()
        finally:
            self._saving = False
            self.save_btn.setEnabled(True)


class _SaleReturnsSubTab(QWidget):
    """Lookup-by-sale-no + history list for sale returns."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Guards against the completer popup's Enter-to-accept firing
        # BOTH completer.activated and the line edit's own returnPressed
        # for the same keypress, which would otherwise open the return
        # dialog twice - same pattern as SaleCardWidget's part search.
        self._suppress_lookup_enter = False
        self._lookup_completer_map: dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        lookup_row = QHBoxLayout()
        self.lookup_input = QLineEdit()
        self.lookup_input.setPlaceholderText("Enter or search Sale No. (e.g. RT-0001 or WS-0001)...")
        self.lookup_input.returnPressed.connect(self._on_lookup_enter)
        lookup_row.addWidget(self.lookup_input, 1)
        lookup_btn = QPushButton("+ New Sale Return")
        lookup_btn.setStyleSheet(_PRIMARY_BTN)
        lookup_btn.clicked.connect(self._on_lookup_enter)
        lookup_row.addWidget(lookup_btn)
        layout.addLayout(lookup_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Return No.", "Sale No.", "Date", "Total"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        self.refresh_lookup_completer()
        self._reload()

    def refresh_lookup_completer(self) -> None:
        """Rebuilds the autosuggestion list from today's POSTED sales -
        only POSTED sales are actually returnable, so suggesting anything
        else would just lead to the dialog's own rejection. Called at
        construction and again whenever the Returns tab regains focus, so
        a sale made elsewhere while this tab sat open still shows up."""
        db = get_spare_session()
        try:
            sales = sales_service.list_sales(db, status="POSTED")
            # Built while the session is still open - sale.customer is a
            # lazy relationship that raises DetachedInstanceError if
            # touched after db.close() below.
            self._lookup_completer_map = {
                f"{s.sale_no} - {s.customer.name if s.customer else 'Walk-in'} - "
                f"{s.sale_date.strftime('%Y-%m-%d')}": s.sale_no
                for s in sales
            }
        finally:
            db.close()
        completer = QCompleter(list(self._lookup_completer_map.keys()), self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.activated.connect(self._on_completer_activated)
        self.lookup_input.setCompleter(completer)

    def _on_completer_activated(self, text: str) -> None:
        # Symmetric guard with _on_lookup_enter (both check-then-set) -
        # Qt can fire completer.activated and the line edit's own
        # returnPressed in EITHER order for one Enter keypress (verified
        # both orderings happen in practice for SaleCardWidget's part
        # search), so whichever fires first must win and block the other.
        if self._suppress_lookup_enter:
            return
        sale_no = self._lookup_completer_map.get(text)
        if not sale_no:
            return
        self._suppress_lookup_enter = True
        self.lookup_input.setText(sale_no)
        try:
            self._do_lookup(sale_no)
        finally:
            QTimer.singleShot(0, self._clear_lookup_enter_guard)

    def _clear_lookup_enter_guard(self) -> None:
        self._suppress_lookup_enter = False

    def _on_lookup_enter(self) -> None:
        if self._suppress_lookup_enter:
            return
        self._suppress_lookup_enter = True
        raw_text = self.lookup_input.text().strip()
        try:
            if not raw_text:
                return
            self._do_lookup(raw_text)
        finally:
            # Scheduled only AFTER _do_lookup returns, i.e. after its
            # modal dlg.exec() has already closed - _do_lookup opens a
            # dialog, which runs its own nested event loop, and a timer
            # scheduled before entering that loop can fire WHILE the
            # dialog is still open (nested loops process pending events
            # too), clearing the guard early and letting the other
            # signal (completer.activated) re-open the same dialog the
            # instant this one closes. Scheduling it here instead means
            # it can only fire once this call has fully returned.
            QTimer.singleShot(0, self._clear_lookup_enter_guard)

    def _do_lookup(self, raw_text: str) -> None:
        # Qt fills the line edit with the highlighted suggestion's FULL
        # "Sale No - Customer - Date" text as the user arrows through the
        # popup - independently of which signal ends up calling this, so
        # by the time either one fires the box may hold that full string,
        # not the bare number. Recover the real sale_no from it the same
        # way selecting it normally would, instead of failing an exact
        # match against the whole display string.
        sale_no = self._lookup_completer_map.get(raw_text, raw_text)
        db = get_spare_session()
        try:
            matches = [s for s in sales_service.list_sales(db) if s.sale_no.upper() == sale_no.upper()]
            sale = matches[0] if matches else None
        finally:
            db.close()
        if not sale:
            QMessageBox.warning(self, "Not Found", f"No sale found with number '{sale_no}'.")
            return
        dlg = SaleReturnDialog(sale_id=sale.id, parent=self)
        if dlg.exec():
            self.lookup_input.clear()
            self.refresh_lookup_completer()
            self._reload()

    def _reload(self) -> None:
        db = get_spare_session()
        try:
            returns = returns_service.list_sale_returns(db)
            self.table.setRowCount(len(returns))
            for row, ret in enumerate(returns):
                self.table.setItem(row, 0, QTableWidgetItem(ret.return_no))
                self.table.setItem(row, 1, QTableWidgetItem(ret.sale.sale_no if ret.sale else ""))
                self.table.setItem(row, 2, QTableWidgetItem(ret.return_date.strftime("%Y-%m-%d")))
                self.table.setItem(row, 3, QTableWidgetItem(f"{float(ret.total):,.2f}"))
        finally:
            db.close()


class _PurchaseReturnsSubTab(QWidget):
    """Lookup-by-purchase-no + history list for purchase returns."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._suppress_lookup_enter = False
        self._lookup_completer_map: dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        lookup_row = QHBoxLayout()
        self.lookup_input = QLineEdit()
        self.lookup_input.setPlaceholderText("Enter or search Purchase No. (e.g. PO-0001)...")
        self.lookup_input.returnPressed.connect(self._on_lookup_enter)
        lookup_row.addWidget(self.lookup_input, 1)
        lookup_btn = QPushButton("+ New Purchase Return")
        lookup_btn.setStyleSheet(_PRIMARY_BTN)
        lookup_btn.clicked.connect(self._on_lookup_enter)
        lookup_row.addWidget(lookup_btn)
        layout.addLayout(lookup_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Return No.", "Purchase No.", "Date", "Total"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        self.refresh_lookup_completer()
        self._reload()

    def refresh_lookup_completer(self) -> None:
        """Same rationale as _SaleReturnsSubTab.refresh_lookup_completer -
        only POSTED purchases are returnable."""
        db = get_spare_session()
        try:
            purchases = purchase_service.list_purchases(db, status="POSTED")
            # Built while the session is still open - see the matching
            # comment in _SaleReturnsSubTab.refresh_lookup_completer.
            self._lookup_completer_map = {
                f"{p.purchase_no} - {p.supplier.name if p.supplier else ''} - "
                f"{p.purchase_date.strftime('%Y-%m-%d')}": p.purchase_no
                for p in purchases
            }
        finally:
            db.close()
        completer = QCompleter(list(self._lookup_completer_map.keys()), self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.activated.connect(self._on_completer_activated)
        self.lookup_input.setCompleter(completer)

    def _on_completer_activated(self, text: str) -> None:
        # Symmetric guard with _on_lookup_enter - see the matching
        # comment in _SaleReturnsSubTab.
        if self._suppress_lookup_enter:
            return
        purchase_no = self._lookup_completer_map.get(text)
        if not purchase_no:
            return
        self._suppress_lookup_enter = True
        self.lookup_input.setText(purchase_no)
        try:
            self._do_lookup(purchase_no)
        finally:
            QTimer.singleShot(0, self._clear_lookup_enter_guard)

    def _clear_lookup_enter_guard(self) -> None:
        self._suppress_lookup_enter = False

    def _on_lookup_enter(self) -> None:
        if self._suppress_lookup_enter:
            return
        self._suppress_lookup_enter = True
        raw_text = self.lookup_input.text().strip()
        try:
            if not raw_text:
                return
            self._do_lookup(raw_text)
        finally:
            # See the matching comment in _SaleReturnsSubTab._on_lookup_enter
            # - must be scheduled only after _do_lookup's modal dialog has
            # already closed, not before.
            QTimer.singleShot(0, self._clear_lookup_enter_guard)

    def _do_lookup(self, raw_text: str) -> None:
        # See the matching comment in _SaleReturnsSubTab._do_lookup -
        # recovers the bare purchase_no even if the box holds the full
        # completer display string.
        purchase_no = self._lookup_completer_map.get(raw_text, raw_text)
        db = get_spare_session()
        try:
            matches = [
                p for p in purchase_service.list_purchases(db)
                if p.purchase_no.upper() == purchase_no.upper()
            ]
            purchase = matches[0] if matches else None
        finally:
            db.close()
        if not purchase:
            QMessageBox.warning(self, "Not Found", f"No purchase found with number '{purchase_no}'.")
            return
        dlg = PurchaseReturnDialog(purchase_id=purchase.id, parent=self)
        if dlg.exec():
            self.lookup_input.clear()
            self.refresh_lookup_completer()
            self._reload()

    def _reload(self) -> None:
        db = get_spare_session()
        try:
            returns = returns_service.list_purchase_returns(db)
            self.table.setRowCount(len(returns))
            for row, ret in enumerate(returns):
                self.table.setItem(row, 0, QTableWidgetItem(ret.return_no))
                self.table.setItem(row, 1, QTableWidgetItem(ret.purchase.purchase_no if ret.purchase else ""))
                self.table.setItem(row, 2, QTableWidgetItem(ret.return_date.strftime("%Y-%m-%d")))
                self.table.setItem(row, 3, QTableWidgetItem(f"{float(ret.total):,.2f}"))
        finally:
            db.close()


class ReturnsPage(QWidget):
    """Top-level Returns tab: Sale Returns and Purchase Returns sub-tabs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        sub_tabs = QTabWidget()
        self.sale_returns_tab = _SaleReturnsSubTab()
        self.purchase_returns_tab = _PurchaseReturnsSubTab()
        sub_tabs.addTab(self.sale_returns_tab, "Sale Returns")
        sub_tabs.addTab(self.purchase_returns_tab, "Purchase Returns")
        layout.addWidget(sub_tabs)

    def refresh_lookup_completers(self) -> None:
        """This page is built once (not recreated per tab visit), so a
        sale/purchase posted elsewhere while Returns wasn't the active
        tab would otherwise never show up in either sub-tab's
        autosuggestion list - called from main_widget.py whenever this
        tab regains focus, same pattern as PosPage's parts-lookup
        refresh."""
        self.sale_returns_tab.refresh_lookup_completer()
        self.purchase_returns_tab.refresh_lookup_completer()
