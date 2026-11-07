"""Sales Counter (POS): multiple simultaneous sale "cards" as tabs, each
fully independent (spare_parts/ui/sale_card_widget.py), plus Hold/Resume
so a cashier can set a customer's cart aside and come back to it without
losing anything or blocking other customers (spare_parts/services/
held_sales_service.py). See spare_parts/__init__.py: stock is only ever
reduced when a card is completed into a real sale.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from spare_parts.db.base import get_spare_session
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import fbr_submission_service, held_sales_service
from spare_parts.ui.held_sales_dialog import HeldSalesDialog
from spare_parts.ui.sale_card_widget import SaleCardWidget
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

_SUCCESS_BTN = """
    QPushButton {
        background-color: #27ae60; color: white; border: none;
        border-radius: 4px; padding: 8px 16px; font-weight: bold;
    }
    QPushButton:hover { background-color: #229954; }
"""

_WARNING_BTN = """
    QPushButton {
        background-color: #f39c12; color: white; border: none;
        border-radius: 4px; padding: 8px 16px; font-weight: bold;
    }
    QPushButton:hover { background-color: #d68910; }
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


class PosPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._card_counter = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        toolbar = QHBoxLayout()
        header = QLabel("Sales Counter")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        toolbar.addWidget(header)
        toolbar.addStretch(1)

        self.held_sales_btn = QPushButton("Held Sales (0)")
        self.held_sales_btn.setStyleSheet(_RESET_BTN)
        self.held_sales_btn.clicked.connect(self._on_held_sales_clicked)
        toolbar.addWidget(self.held_sales_btn)

        new_card_btn = QPushButton("+ New Card (Ctrl+T)")
        new_card_btn.setStyleSheet(_PRIMARY_BTN)
        new_card_btn.clicked.connect(self._on_new_card_clicked)
        toolbar.addWidget(new_card_btn)
        layout.addLayout(toolbar)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tabs.tabBarDoubleClicked.connect(self._on_tab_bar_double_clicked)
        layout.addWidget(self.tabs, 1)

        action_row = QHBoxLayout()
        complete_btn = QPushButton("Complete Sale")
        complete_btn.setStyleSheet(_SUCCESS_BTN)
        complete_btn.clicked.connect(self._on_complete_clicked)
        action_row.addWidget(complete_btn)

        hold_btn = QPushButton("Hold Sale")
        hold_btn.setStyleSheet(_WARNING_BTN)
        hold_btn.clicked.connect(self._on_hold_clicked)
        action_row.addWidget(hold_btn)
        action_row.addStretch(1)

        discard_btn = QPushButton("Discard Card")
        discard_btn.setStyleSheet(_DANGER_BTN)
        discard_btn.clicked.connect(self._on_discard_clicked)
        action_row.addWidget(discard_btn)
        layout.addLayout(action_row)

        QShortcut(QKeySequence("Ctrl+T"), self, activated=self._on_new_card_clicked)

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._autosave_open_cards)

        self._new_card()
        self.refresh_held_count()

    # --- card lifecycle --------------------------------------------------------

    def _new_card(self) -> SaleCardWidget:
        self._card_counter += 1
        card = SaleCardWidget(reserved_qty_fn=self._reserved_qty_elsewhere)
        card.totals_changed.connect(lambda c=card: self._update_tab_label(c))
        card.label_changed.connect(lambda c=card: self._update_tab_label(c))
        index = self.tabs.addTab(card, f"Card {self._card_counter}")
        self.tabs.setCurrentIndex(index)
        self._update_tab_label(card)
        return card

    def _update_tab_label(self, card: SaleCardWidget) -> None:
        index = self.tabs.indexOf(card)
        if index < 0:
            return
        label = card.display_label()
        total = card.current_total()
        self.tabs.setTabText(index, f"{label} - Rs. {total:,.2f}" if total > 0 else label)

    def _current_card(self) -> SaleCardWidget | None:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, SaleCardWidget) else None

    def _close_card(self, card: SaleCardWidget) -> None:
        index = self.tabs.indexOf(card)
        if index < 0:
            return
        self.tabs.removeTab(index)
        card.deleteLater()
        if self.tabs.count() == 0:
            self._new_card()

    def _reserved_qty_elsewhere(self, part_id: int, exclude_held_sale_id) -> int:
        """How much of this part is already committed to every OTHER open
        card plus every held draft - see SaleCardWidget._warn_if_oversold."""
        current_card = self._current_card()
        total = 0
        for i in range(self.tabs.count()):
            card = self.tabs.widget(i)
            if card is current_card or not isinstance(card, SaleCardWidget):
                continue
            total += card.qty_reserved_for_part(part_id)
        db = get_spare_session()
        try:
            total += held_sales_service.get_reserved_qty_for_part(
                db, part_id, exclude_held_sale_id=exclude_held_sale_id
            )
        finally:
            db.close()
        return total

    # --- toolbar / shortcuts -----------------------------------------------

    def _on_new_card_clicked(self) -> None:
        self._new_card()

    def _on_tab_bar_double_clicked(self, index: int) -> None:
        card = self.tabs.widget(index)
        if not isinstance(card, SaleCardWidget):
            return
        current_label = card.custom_label or card.display_label()
        new_label, ok = QInputDialog.getText(self, "Rename Card", "Card name:", text=current_label)
        if ok and new_label.strip():
            card.custom_label = new_label.strip()
            self._update_tab_label(card)

    # --- complete / hold / discard -----------------------------------------

    def _on_complete_clicked(self) -> None:
        card = self._current_card()
        if not card:
            return
        if card.is_empty():
            QMessageBox.information(self, "Empty Card", "Add at least one item first.")
            return
        sale = card.complete_sale()
        if not sale:
            return  # validation error already shown on the card itself

        sale_id, sale_no, sale_type = sale.id, sale.sale_no, sale.sale_type
        fbr_note = self._submit_sale_to_fbr(sale_id, sale_no)

        if sale_type == "RETAIL":
            print_confirm = QMessageBox.question(
                self, "Sale Completed", f"Sale {sale_no} completed.{fbr_note}\n\nPrint receipt?",
            )
            if print_confirm == QMessageBox.StandardButton.Yes:
                try:
                    card.print_receipt(sale_id)
                except Exception as e:
                    logger.error(f"Receipt printing failed for sale {sale_no}: {e}", exc_info=True)
                    QMessageBox.warning(
                        self, "Printing Failed",
                        f"Sale {sale_no} was saved, but the receipt could not be printed:\n{e}",
                    )
        else:
            QMessageBox.information(self, "Sale Completed", f"Sale {sale_no} completed.{fbr_note}")

        self._close_card(card)
        self.refresh_held_count()

    def _submit_sale_to_fbr(self, sale_id: int, sale_no: str) -> str:
        """Submits a just-completed sale to FBR immediately, using
        whichever environment (SANDBOX/PRODUCTION) is currently active in
        Spare Parts Settings - same lookup fbr_submission_service.py
        itself does, and the same manual flow the Sales tab's "Submit to
        FBR" button uses. Never blocks the sale from counting as
        completed: the sale is already saved by this point regardless of
        the outcome here, and a failure can always be retried from the
        Sales tab. Returns a short note to fold into the caller's own
        "Sale Completed" dialog instead of popping up a second dialog."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            db = get_spare_session()
            try:
                sale = fbr_submission_service.submit_sale_to_fbr(db, sale_id)
            finally:
                db.close()
            return f"\n\nFBR Invoice Number: {sale.fbr_invoice_number}"
        except SparePartsValidationError as e:
            logger.warning(f"FBR submission failed for sale {sale_no}: {e}")
            return f"\n\nFBR submission failed: {e}\n(You can retry from the Sales tab.)"
        except Exception as e:
            logger.error(f"Unexpected error submitting sale {sale_no} to FBR: {e}", exc_info=True)
            return f"\n\nFBR submission failed: {e}\n(You can retry from the Sales tab.)"
        finally:
            QApplication.restoreOverrideCursor()

    def _on_hold_clicked(self) -> None:
        card = self._current_card()
        if not card:
            return
        if card.is_empty():
            QMessageBox.information(self, "Empty Card", "Add at least one item before holding this sale.")
            return
        if card.hold_sale():
            self._close_card(card)
            self.refresh_held_count()

    def _on_discard_clicked(self) -> None:
        card = self._current_card()
        if not card:
            return
        if not card.is_empty():
            confirm = QMessageBox.question(
                self, "Discard Card",
                "Discard everything in this card? This cannot be undone.",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
        card.discard()
        self._close_card(card)
        self.refresh_held_count()

    def _on_tab_close_requested(self, index: int) -> None:
        card = self.tabs.widget(index)
        if not isinstance(card, SaleCardWidget):
            return

        if card.is_empty():
            self.tabs.removeTab(index)
            card.deleteLater()
            if self.tabs.count() == 0:
                self._new_card()
            return

        self.tabs.setCurrentIndex(index)
        msg = QMessageBox(self)
        msg.setWindowTitle("Close Card")
        msg.setText("This card still has items. What would you like to do?")
        complete_btn = msg.addButton("Complete", QMessageBox.ButtonRole.AcceptRole)
        hold_btn = msg.addButton("Hold", QMessageBox.ButtonRole.ActionRole)
        discard_btn = msg.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(cancel_btn)
        msg.exec()
        clicked = msg.clickedButton()

        if clicked is complete_btn:
            self._on_complete_clicked()
        elif clicked is hold_btn:
            self._on_hold_clicked()
        elif clicked is discard_btn:
            self._on_discard_clicked()
        # cancel_btn (or closing the message box): leave the tab open untouched.

    # --- held sales ----------------------------------------------------------

    def _on_held_sales_clicked(self) -> None:
        dlg = HeldSalesDialog(parent=self)
        if dlg.exec() and dlg.resumed_held_sale_id:
            self._resume_held_sale(dlg.resumed_held_sale_id)
        self.refresh_held_count()

    def _resume_held_sale(self, held_sale_id: int) -> None:
        db = get_spare_session()
        try:
            held = held_sales_service.get_held_sale(db, held_sale_id)
            if not held:
                QMessageBox.warning(self, "Not Found", "This held sale no longer exists.")
                return
            card = self._new_card()
            repriced = card.load_from_held_sale(held)
        finally:
            db.close()

        self._update_tab_label(card)
        if repriced:
            QMessageBox.information(
                self, "Prices Updated",
                "Prices changed since this sale was held and were refreshed for: "
                + ", ".join(repriced),
            )

    def refresh_held_count(self) -> None:
        db = get_spare_session()
        try:
            count = len(held_sales_service.list_held_sales(db))
        finally:
            db.close()
        self.held_sales_btn.setText(f"Held Sales ({count})")

    def refresh_open_cards_parts_lookup(self) -> None:
        """Refreshes every open card's cached parts/brand snapshot - a
        card left open (this page is created once, not rebuilt per tab
        visit) would otherwise keep showing whatever a part's brand/price
        looked like when the card was built, even after it's edited
        elsewhere in the app while this tab wasn't active."""
        for i in range(self.tabs.count()):
            card = self.tabs.widget(i)
            if isinstance(card, SaleCardWidget):
                card.refresh_parts_lookup()

    # --- app-exit safety net ----------------------------------------------

    def _autosave_open_cards(self) -> None:
        """Connected to QApplication.aboutToQuit (see __init__) rather
        than a closeEvent override, since this page is embedded inside
        the main window's stacked pages, not a top-level window itself -
        this fires on every path the application actually exits by."""
        for i in range(self.tabs.count()):
            card = self.tabs.widget(i)
            if isinstance(card, SaleCardWidget) and not card.is_empty():
                try:
                    card.hold_sale()
                except Exception:
                    logger.error("Failed to autosave an open POS card on exit.", exc_info=True)
