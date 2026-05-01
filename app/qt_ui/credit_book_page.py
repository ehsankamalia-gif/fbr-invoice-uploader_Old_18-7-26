from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.db.session import SessionLocal
from app.db.models import CreditBookTransaction, Customer
from app.services.credit_book_service import credit_book_service


class CreditCustomerRow:
    def __init__(self, customer_id: int, name: str, cnic: str, phone: str, balance: float) -> None:
        self.customer_id = customer_id
        self.name = name
        self.cnic = cnic
        self.phone = phone
        self.balance = balance


class CreditTxnRow:
    def __init__(
        self,
        txn_id: int,
        timestamp: Optional[dt.datetime],
        customer: str,
        direction: str,
        entry_type: str,
        reference: str,
        description: str,
        debit: float,
        credit: float,
        balance: Optional[float],
        is_void: bool,
    ) -> None:
        self.txn_id = txn_id
        self.timestamp = timestamp
        self.customer = customer
        self.direction = direction
        self.entry_type = entry_type
        self.reference = reference
        self.description = description
        self.debit = debit
        self.credit = credit
        self.balance = balance
        self.is_void = is_void


class CreditCustomersTableModel(QAbstractTableModel):
    headers = ["Customer", "CNIC", "Phone", "Balance"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[CreditCustomerRow] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row.name
            if col == 1:
                return row.cnic
            if col == 2:
                return row.phone
            if col == 3:
                return f"{row.balance:,.2f}"

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col == 3:
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        if role == Qt.ItemDataRole.ForegroundRole:
            if col == 3 and row.balance < 0:
                return Qt.GlobalColor.red
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.headers):
            return self.headers[section]
        return super().headerData(section, orientation, role)

    def update_rows(self, rows: List[CreditCustomerRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class CreditTransactionsTableModel(QAbstractTableModel):
    headers = ["Date/Time", "Customer", "Type", "Direction", "Reference", "Description", "Debit", "Credit", "Balance", "Status"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[CreditTxnRow] = []

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row.timestamp.strftime("%Y-%m-%d %H:%M") if row.timestamp else ""
            if col == 1:
                return row.customer
            if col == 2:
                return row.entry_type
            if col == 3:
                return row.direction
            if col == 4:
                return row.reference
            if col == 5:
                return row.description
            if col == 6:
                return f"{row.debit:,.2f}" if row.debit else ""
            if col == 7:
                return f"{row.credit:,.2f}" if row.credit else ""
            if col == 8:
                return f"{row.balance:,.2f}" if row.balance is not None else ""
            if col == 9:
                return "VOID" if row.is_void else ""

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (6, 7, 8):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            if col in (0, 2, 3, 9):
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

        if role == Qt.ItemDataRole.ForegroundRole:
            if row.is_void:
                return Qt.GlobalColor.darkGray
            if col == 6 and row.debit:
                return Qt.GlobalColor.darkRed
            if col == 7 and row.credit:
                return Qt.GlobalColor.darkGreen
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.headers):
            return self.headers[section]
        return super().headerData(section, orientation, role)

    def update_rows(self, rows: List[CreditTxnRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class CreditBookPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Credit Book")

        self._customer_cache: List[Tuple[int, str]] = []
        self._customer_label_to_id: Dict[str, int] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        header_layout = QHBoxLayout()
        header = QLabel("Credit Book")
        header.setObjectName("pageHeader")
        header_layout.addWidget(header)
        header_layout.addStretch(1)

        self.btn_refresh = QPushButton("↻ Refresh")
        self.btn_refresh.setObjectName("resetButton")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh)  # type: ignore[arg-type]

        self.btn_new = QPushButton("+ New Entry")
        self.btn_new.setObjectName("primaryButton")
        self.btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new.clicked.connect(self._open_new_entry_dialog)  # type: ignore[arg-type]

        header_layout.addWidget(self.btn_refresh)
        header_layout.addWidget(self.btn_new)
        layout.addLayout(header_layout)

        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(15)
        self.card_total_receivable = self._create_stat_card("TOTAL RECEIVABLE", "0.00", "#3498db")
        self.card_total_debit = self._create_stat_card("TOTAL CHARGES (DEBIT)", "0.00", "#e74c3c")
        self.card_total_credit = self._create_stat_card("TOTAL PAYMENTS (CREDIT)", "0.00", "#2ecc71")
        stats_layout.addWidget(self.card_total_receivable)
        stats_layout.addWidget(self.card_total_debit)
        stats_layout.addWidget(self.card_total_credit)
        layout.addLayout(stats_layout)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self.tab_customers = QWidget()
        self.tab_transactions = QWidget()
        self.tabs.addTab(self.tab_customers, "Customers")
        self.tabs.addTab(self.tab_transactions, "Transactions")

        self._build_customers_tab()
        self._build_transactions_tab()

        self.refresh()

    def _create_stat_card(self, title: str, value: str, color: str) -> QFrame:
        card = QFrame()
        card.setObjectName("statCard")
        card.setStyleSheet(
            f"""
            QFrame#statCard {{
                background: white;
                border-radius: 10px;
                border-top: 4px solid {color};
                padding: 12px;
            }}
            """
        )
        v = QVBoxLayout(card)
        v.setContentsMargins(15, 15, 15, 15)
        v.setSpacing(6)
        t = QLabel(title)
        t.setStyleSheet("color: #6c757d; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        val = QLabel(value)
        val.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold;")
        v.addWidget(t)
        v.addWidget(val)
        card.value_label = val
        return card

    def _build_customers_tab(self) -> None:
        layout = QVBoxLayout(self.tab_customers)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)

        controls = QFrame()
        controls.setObjectName("formGroup")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(15, 10, 15, 10)
        controls_layout.setSpacing(15)

        controls_layout.addWidget(QLabel("Search:"))
        self.customer_search = QLineEdit()
        self.customer_search.setPlaceholderText("Name / CNIC / phone...")
        self.customer_search.textChanged.connect(self.refresh)  # type: ignore[arg-type]
        controls_layout.addWidget(self.customer_search, 1)

        layout.addWidget(controls)

        self.customers_model = CreditCustomersTableModel()
        self.customers_table = QTableView()
        self.customers_table.setModel(self.customers_model)
        self.customers_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.customers_table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.customers_table.doubleClicked.connect(self._on_customer_double_clicked)  # type: ignore[arg-type]
        self.customers_table.horizontalHeader().setStretchLastSection(True)
        self.customers_table.verticalHeader().setVisible(False)
        self.customers_table.setAlternatingRowColors(True)
        layout.addWidget(self.customers_table, 1)

    def _build_transactions_tab(self) -> None:
        layout = QVBoxLayout(self.tab_transactions)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)

        controls = QFrame()
        controls.setObjectName("formGroup")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(15, 10, 15, 10)
        controls_layout.setSpacing(15)

        controls_layout.addWidget(QLabel("Customer:"))
        self.txn_customer_combo = QComboBox()
        self.txn_customer_combo.setEditable(True)
        self.txn_customer_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.txn_customer_combo.currentTextChanged.connect(self.refresh)  # type: ignore[arg-type]
        controls_layout.addWidget(self.txn_customer_combo, 1)

        controls_layout.addWidget(QLabel("Direction:"))
        self.txn_direction_combo = QComboBox()
        self.txn_direction_combo.addItems(["All", "DEBIT", "CREDIT"])
        self.txn_direction_combo.currentTextChanged.connect(self.refresh)  # type: ignore[arg-type]
        controls_layout.addWidget(self.txn_direction_combo)

        controls_layout.addWidget(QLabel("Search:"))
        self.txn_search = QLineEdit()
        self.txn_search.setPlaceholderText("Ref / description / customer...")
        self.txn_search.textChanged.connect(self.refresh)  # type: ignore[arg-type]
        controls_layout.addWidget(self.txn_search, 1)

        layout.addWidget(controls)

        self.txn_model = CreditTransactionsTableModel()
        self.txn_table = QTableView()
        self.txn_table.setModel(self.txn_model)
        self.txn_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.txn_table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.txn_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.txn_table.customContextMenuRequested.connect(self._on_txn_context_menu)  # type: ignore[arg-type]
        self.txn_table.horizontalHeader().setStretchLastSection(True)
        self.txn_table.verticalHeader().setVisible(False)
        self.txn_table.setAlternatingRowColors(True)
        layout.addWidget(self.txn_table, 1)

    def _load_customers_cache(self) -> None:
        db = SessionLocal()
        try:
            customers = (
                db.query(Customer)
                .filter(Customer.is_deleted.is_(False))
                .order_by(Customer.name.asc())
                .limit(5000)
                .all()
            )
            items: List[Tuple[int, str]] = []
            label_to_id: Dict[str, int] = {}
            for c in customers:
                label = f"{c.name or ''} | {c.cnic or ''} | {c.phone or ''} | #{c.id}"
                items.append((int(c.id), label))
                label_to_id[label] = int(c.id)

            self._customer_cache = items
            self._customer_label_to_id = label_to_id

            current = self.txn_customer_combo.currentText()
            self.txn_customer_combo.blockSignals(True)
            self.txn_customer_combo.clear()
            self.txn_customer_combo.addItem("All Customers")
            for _, label in items:
                self.txn_customer_combo.addItem(label)
            if current:
                idx = self.txn_customer_combo.findText(current)
                self.txn_customer_combo.setCurrentIndex(idx if idx >= 0 else 0)
            else:
                self.txn_customer_combo.setCurrentIndex(0)
            self.txn_customer_combo.blockSignals(False)
        finally:
            db.close()

    def _selected_customer_id(self) -> Optional[int]:
        label = (self.txn_customer_combo.currentText() or "").strip()
        if not label or label == "All Customers":
            return None
        return self._customer_label_to_id.get(label)

    def _on_customer_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        row = self.customers_model._rows[index.row()]
        target_label = None
        for cid, label in self._customer_cache:
            if cid == row.customer_id:
                target_label = label
                break
        if target_label:
            idx = self.txn_customer_combo.findText(target_label)
            if idx >= 0:
                self.txn_customer_combo.setCurrentIndex(idx)
        self.tabs.setCurrentWidget(self.tab_transactions)
        self.refresh()

    def _on_txn_context_menu(self, pos) -> None:
        index = self.txn_table.indexAt(pos)
        if not index.isValid():
            return
        row = self.txn_model._rows[index.row()]
        if row.txn_id <= 0:
            return

        menu = QMenu(self)
        void_action = menu.addAction("Void Entry")
        if row.is_void:
            void_action.setEnabled(False)
        action = menu.exec(self.txn_table.viewport().mapToGlobal(pos))
        if action == void_action:
            self._void_transaction(row.txn_id)

    def _void_transaction(self, txn_id: int) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Void Credit Book Entry")
        dlg.setFixedWidth(520)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)
        lay.addWidget(QLabel("Reason (required):"))
        reason = QTextEdit()
        reason.setFixedHeight(90)
        lay.addWidget(reason)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Void Entry")
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        r = reason.toPlainText().strip()
        db = SessionLocal()
        try:
            credit_book_service.void_transaction(db, txn_id, r)
            QMessageBox.information(self, "Voided", "Entry has been voided successfully.")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
        finally:
            db.close()

    def _open_new_entry_dialog(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("New Credit Book Entry")
        dlg.setFixedWidth(520)
        dlg.setStyleSheet(
            """
            QDialog { background-color: white; }
            QLabel { font-size: 13px; color: #2c3e50; font-weight: 500; }
            QLineEdit, QComboBox, QDoubleSpinBox, QDateEdit, QTextEdit {
                padding: 10px; border: 1px solid #dee2e6; border-radius: 6px;
                background-color: #f8f9fa; font-size: 13px;
            }
            QPushButton { padding: 10px 25px; border-radius: 6px; font-weight: bold; font-size: 13px; }
            """
        )

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(25, 25, 25, 25)
        lay.setSpacing(18)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)

        customer_combo = QComboBox()
        customer_combo.setEditable(True)
        customer_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        customer_combo.addItem("Select Customer")
        for _, label in self._customer_cache:
            customer_combo.addItem(label)

        entry_type_combo = QComboBox()
        entry_type_combo.addItems(["SALE", "PAYMENT", "ADJUSTMENT", "OPENING"])

        direction_combo = QComboBox()
        direction_combo.addItems(["DEBIT", "CREDIT"])
        direction_combo.setEnabled(False)

        def on_entry_type_changed(txt: str) -> None:
            t = (txt or "").strip().upper()
            if t in ("SALE", "OPENING"):
                direction_combo.setCurrentText("DEBIT")
                direction_combo.setEnabled(False)
            elif t == "PAYMENT":
                direction_combo.setCurrentText("CREDIT")
                direction_combo.setEnabled(False)
            else:
                direction_combo.setEnabled(True)

        entry_type_combo.currentTextChanged.connect(on_entry_type_changed)  # type: ignore[arg-type]
        on_entry_type_changed(entry_type_combo.currentText())

        amount_spin = QDoubleSpinBox()
        amount_spin.setRange(0, 99999999)
        amount_spin.setDecimals(2)
        amount_spin.setPrefix("Rs. ")

        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDate(dt.date.today())

        ref_input = QLineEdit()
        ref_input.setPlaceholderText("Optional reference (e.g., INV-123 / RCPT-01)")

        desc_input = QTextEdit()
        desc_input.setPlaceholderText("Optional description...")
        desc_input.setFixedHeight(90)

        form.addWidget(QLabel("Customer"), 0, 0)
        form.addWidget(customer_combo, 0, 1)
        form.addWidget(QLabel("Entry Type"), 1, 0)
        form.addWidget(entry_type_combo, 1, 1)
        form.addWidget(QLabel("Direction"), 2, 0)
        form.addWidget(direction_combo, 2, 1)
        form.addWidget(QLabel("Amount"), 3, 0)
        form.addWidget(amount_spin, 3, 1)
        form.addWidget(QLabel("Date"), 4, 0)
        form.addWidget(date_edit, 4, 1)
        form.addWidget(QLabel("Reference"), 5, 0)
        form.addWidget(ref_input, 5, 1)
        form.addWidget(QLabel("Description"), 6, 0)
        form.addWidget(desc_input, 6, 1)

        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        customer_label = customer_combo.currentText().strip()
        cid = self._customer_label_to_id.get(customer_label)
        if not cid:
            QMessageBox.warning(self, "Customer Required", "Please select a customer.")
            return

        qd = date_edit.date()
        ts = dt.datetime(qd.year(), qd.month(), qd.day(), dt.datetime.now().hour, dt.datetime.now().minute)

        db = SessionLocal()
        try:
            credit_book_service.create_transaction(
                db=db,
                customer_id=cid,
                direction=direction_combo.currentText(),
                entry_type=entry_type_combo.currentText(),
                amount=float(amount_spin.value()),
                reference_number=ref_input.text(),
                description=desc_input.toPlainText(),
                timestamp=ts,
            )
            QMessageBox.information(self, "Saved", "Credit book entry saved successfully.")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
        finally:
            db.close()

    def refresh(self) -> None:
        if not self._customer_cache:
            self._load_customers_cache()

        db = SessionLocal()
        try:
            summary = credit_book_service.get_summary(db)
            self.card_total_receivable.value_label.setText(f"{summary['total_balance']:,.2f}")
            self.card_total_debit.value_label.setText(f"{summary['total_debit']:,.2f}")
            self.card_total_credit.value_label.setText(f"{summary['total_credit']:,.2f}")

            cust_search = self.customer_search.text().strip() if hasattr(self, "customer_search") else ""
            cust_rows_raw = credit_book_service.list_customer_balances(db, search=cust_search, limit=800)
            cust_rows = [
                CreditCustomerRow(
                    customer_id=r["customer_id"],
                    name=r["name"],
                    cnic=r["cnic"],
                    phone=r["phone"],
                    balance=r["balance"],
                )
                for r in cust_rows_raw
            ]
            self.customers_model.update_rows(cust_rows)

            selected_customer_id = self._selected_customer_id()
            direction = self.txn_direction_combo.currentText().strip().upper()
            search = self.txn_search.text().strip()
            txns = credit_book_service.list_transactions(
                db,
                customer_id=selected_customer_id,
                direction=direction if direction != "ALL" else "ALL",
                include_void=True,
                search=search,
                limit=3000,
            )

            rows: List[CreditTxnRow] = []
            running_balance: Optional[float] = 0.0 if selected_customer_id else None
            for t in txns:
                debit = float(t.amount or 0.0) if (t.direction or "").upper() == "DEBIT" and not t.is_void else 0.0
                credit = float(t.amount or 0.0) if (t.direction or "").upper() == "CREDIT" and not t.is_void else 0.0
                if running_balance is not None:
                    running_balance += (debit - credit)
                customer_label = ""
                try:
                    customer_label = t.customer.name if t.customer else ""
                except Exception:
                    customer_label = ""
                rows.append(
                    CreditTxnRow(
                        txn_id=int(t.id),
                        timestamp=t.timestamp,
                        customer=customer_label,
                        direction=str(t.direction or ""),
                        entry_type=str(t.entry_type or ""),
                        reference=str(t.reference_number or ""),
                        description=str(t.description or ""),
                        debit=debit,
                        credit=credit,
                        balance=running_balance,
                        is_void=bool(t.is_void),
                    )
                )
            self.txn_model.update_rows(rows)
        finally:
            db.close()

