from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QAbstractTableModel, QEvent, QModelIndex, QObject, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.db.session import SessionLocal
from app.db.models import FinanceApplication, FinanceApplicationItem, FinanceInstallment, FinanceLoan, Motorcycle, Price, ProductModel
from app.services.financing_service import financing_service


class FinanceApplicationRow:
    def __init__(
        self,
        app_id: int,
        created_at: Optional[dt.datetime],
        customer_name: str,
        applicant_type: str,
        total: float,
        financed: float,
        term: int,
        dp_pct: float,
        rate: float,
        score: Optional[int],
        tier: str,
        status: str,
    ) -> None:
        self.app_id = app_id
        self.created_at = created_at
        self.customer_name = customer_name
        self.applicant_type = applicant_type
        self.total = total
        self.financed = financed
        self.term = term
        self.dp_pct = dp_pct
        self.rate = rate
        self.score = score
        self.tier = tier
        self.status = status


class FinanceLoanRow:
    def __init__(
        self,
        loan_id: int,
        loan_number: str,
        customer_name: str,
        financed: float,
        emi: float,
        next_due: Optional[dt.datetime],
        status: str,
    ) -> None:
        self.loan_id = loan_id
        self.loan_number = loan_number
        self.customer_name = customer_name
        self.financed = financed
        self.emi = emi
        self.next_due = next_due
        self.status = status


class FinanceApplicationsTableModel(QAbstractTableModel):
    headers = ["ID", "Created", "Customer", "Type", "Total", "Financed", "Term", "DP%", "Rate%", "Score", "Tier", "Status"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[FinanceApplicationRow] = []

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
                return str(row.app_id)
            if col == 1:
                return row.created_at.strftime("%Y-%m-%d %H:%M") if row.created_at else ""
            if col == 2:
                return row.customer_name
            if col == 3:
                return row.applicant_type
            if col == 4:
                return f"{row.total:,.2f}"
            if col == 5:
                return f"{row.financed:,.2f}"
            if col == 6:
                return str(row.term)
            if col == 7:
                return f"{row.dp_pct:.2f}"
            if col == 8:
                return f"{row.rate:.2f}"
            if col == 9:
                return str(row.score or "")
            if col == 10:
                return row.tier
            if col == 11:
                return row.status

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (0, 1, 3, 6, 9, 10, 11):
                return Qt.AlignmentFlag.AlignCenter
            if col in (4, 5, 7, 8):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.headers):
            return self.headers[section]
        return super().headerData(section, orientation, role)

    def update_rows(self, rows: List[FinanceApplicationRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class FinanceLoansTableModel(QAbstractTableModel):
    headers = ["Loan #", "Customer", "Financed", "EMI", "Next Due", "Status"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[FinanceLoanRow] = []

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
                return row.loan_number
            if col == 1:
                return row.customer_name
            if col == 2:
                return f"{row.financed:,.2f}"
            if col == 3:
                return f"{row.emi:,.2f}"
            if col == 4:
                return row.next_due.strftime("%Y-%m-%d") if row.next_due else ""
            if col == 5:
                return row.status

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (2, 3):
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            if col in (0, 4, 5):
                return Qt.AlignmentFlag.AlignCenter
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.headers):
            return self.headers[section]
        return super().headerData(section, orientation, role)

    def update_rows(self, rows: List[FinanceLoanRow]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()


class FinancingPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Financing")

        self._customer_cache: List[Tuple[int, str]] = []
        self._customer_label_to_id: Dict[str, int] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        header_layout = QHBoxLayout()
        header = QLabel("Motorcycle Financing")
        header.setObjectName("pageHeader")
        header_layout.addWidget(header)
        header_layout.addStretch(1)

        self.btn_refresh = QPushButton("↻ Refresh")
        self.btn_refresh.setObjectName("resetButton")
        self.btn_refresh.clicked.connect(self.refresh)  # type: ignore[arg-type]

        layout.addLayout(header_layout)

        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(15)
        self.card_active_loans = self._create_stat_card("ACTIVE LOANS", "0", "#3498db")
        self.card_outstanding = self._create_stat_card("TOTAL OUTSTANDING", "0.00", "#e67e22")
        self.card_overdue = self._create_stat_card("OVERDUE INSTALLMENTS", "0", "#e74c3c")
        stats_layout.addWidget(self.card_active_loans)
        stats_layout.addWidget(self.card_outstanding)
        stats_layout.addWidget(self.card_overdue)
        stats_layout.addStretch(1)
        stats_layout.addWidget(self.btn_refresh)
        layout.addLayout(stats_layout)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self.tab_apps = QWidget()
        self.tab_loans = QWidget()
        self.tabs.addTab(self.tab_apps, "Applications")
        self.tabs.addTab(self.tab_loans, "Loans")

        self._build_apps_tab()
        self._build_loans_tab()

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
        val.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: bold;")
        v.addWidget(t)
        v.addWidget(val)
        card.value_label = val
        return card

    def _build_apps_tab(self) -> None:
        layout = QVBoxLayout(self.tab_apps)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)

        controls = QFrame()
        controls.setObjectName("formGroup")
        c = QHBoxLayout(controls)
        c.setContentsMargins(15, 10, 15, 10)
        c.setSpacing(12)

        c.addWidget(QLabel("Status:"))
        self.app_status_filter = QComboBox()
        self.app_status_filter.addItems(["All", "DRAFT", "SUBMITTED", "IN_REVIEW", "APPROVED", "REJECTED", "CANCELLED"])
        self.app_status_filter.currentTextChanged.connect(self.refresh)  # type: ignore[arg-type]
        c.addWidget(self.app_status_filter)

        c.addWidget(QLabel("Search:"))
        self.app_search = QLineEdit()
        self.app_search.setPlaceholderText("Customer name / CNIC / notes...")
        self.app_search.textChanged.connect(self.refresh)  # type: ignore[arg-type]
        c.addWidget(self.app_search, 1)

        self.btn_new_app = QPushButton("+ New Application")
        self.btn_new_app.setObjectName("primaryButton")
        self.btn_new_app.clicked.connect(self._open_new_application_dialog)  # type: ignore[arg-type]

        c.addWidget(self.btn_new_app)

        layout.addWidget(controls)

        self.apps_model = FinanceApplicationsTableModel()
        self.apps_table = QTableView()
        self.apps_table.setModel(self.apps_model)
        self.apps_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.apps_table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.apps_table.horizontalHeader().setStretchLastSection(True)
        self.apps_table.verticalHeader().setVisible(False)
        self.apps_table.setAlternatingRowColors(True)
        layout.addWidget(self.apps_table, 1)

    def _build_loans_tab(self) -> None:
        layout = QVBoxLayout(self.tab_loans)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)

        controls = QFrame()
        controls.setObjectName("formGroup")
        c = QHBoxLayout(controls)
        c.setContentsMargins(15, 10, 15, 10)
        c.setSpacing(12)

        c.addWidget(QLabel("Status:"))
        self.loan_status_filter = QComboBox()
        self.loan_status_filter.addItems(["All", "ACTIVE", "CLOSED", "DEFAULTED", "REFINANCED"])
        self.loan_status_filter.currentTextChanged.connect(self.refresh)  # type: ignore[arg-type]
        c.addWidget(self.loan_status_filter)

        c.addWidget(QLabel("Search:"))
        self.loan_search = QLineEdit()
        self.loan_search.setPlaceholderText("Loan # / customer...")
        self.loan_search.textChanged.connect(self.refresh)  # type: ignore[arg-type]
        c.addWidget(self.loan_search, 1)

        self.btn_view_schedule = QPushButton("View Schedule")
        self.btn_view_schedule.clicked.connect(self._view_selected_loan_schedule)  # type: ignore[arg-type]

        self.btn_record_payment = QPushButton("Record Payment")
        self.btn_record_payment.clicked.connect(self._record_payment_for_selected_loan)  # type: ignore[arg-type]

        self.btn_payoff = QPushButton("Payoff")
        self.btn_payoff.clicked.connect(self._show_payoff_for_selected_loan)  # type: ignore[arg-type]

        self.btn_refinance = QPushButton("Refinance")
        self.btn_refinance.clicked.connect(self._refinance_selected_loan)  # type: ignore[arg-type]

        self.btn_portal_token = QPushButton("Portal Token")
        self.btn_portal_token.clicked.connect(self._show_portal_token_for_selected_loan)  # type: ignore[arg-type]

        c.addWidget(self.btn_view_schedule)
        c.addWidget(self.btn_record_payment)
        c.addWidget(self.btn_payoff)
        c.addWidget(self.btn_refinance)
        c.addWidget(self.btn_portal_token)

        layout.addWidget(controls)

        self.loans_model = FinanceLoansTableModel()
        self.loans_table = QTableView()
        self.loans_table.setModel(self.loans_model)
        self.loans_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.loans_table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.loans_table.horizontalHeader().setStretchLastSection(True)
        self.loans_table.verticalHeader().setVisible(False)
        self.loans_table.setAlternatingRowColors(True)
        layout.addWidget(self.loans_table, 1)

    def _load_customer_cache(self) -> None:
        db = SessionLocal()
        try:
            from app.db.models import Customer

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
        finally:
            db.close()

    def _selected_app_id(self) -> Optional[int]:
        sel = self.apps_table.selectionModel().selectedRows()
        if not sel:
            return None
        row = sel[0].row()
        if row < 0 or row >= len(self.apps_model._rows):
            return None
        return int(self.apps_model._rows[row].app_id)

    def _selected_loan_id(self) -> Optional[int]:
        sel = self.loans_table.selectionModel().selectedRows()
        if not sel:
            return None
        row = sel[0].row()
        if row < 0 or row >= len(self.loans_model._rows):
            return None
        return int(self.loans_model._rows[row].loan_id)

    def _open_new_application_dialog(self) -> None:
        if not self._customer_cache:
            self._load_customer_cache()

        class _SelectedMotorcycleRow:
            def __init__(
                self,
                motorcycle_id: int,
                chassis_number: str,
                model_name: str,
                color: str,
                status: str,
                cash_unit_price: float,
                credit_unit_price: float,
            ) -> None:
                self.motorcycle_id = motorcycle_id
                self.chassis_number = chassis_number
                self.model_name = model_name
                self.color = color
                self.status = status
                self.cash_unit_price = cash_unit_price
                self.credit_unit_price = credit_unit_price

        class _SelectedMotorcyclesModel(QAbstractTableModel):
            headers = ["Chassis", "Model", "Color", "Status", "Cash Price", "Credit Price"]

            def __init__(self) -> None:
                super().__init__()
                self.rows: List[_SelectedMotorcycleRow] = []

            def rowCount(self, parent: QModelIndex | None = None) -> int:
                return len(self.rows)

            def columnCount(self, parent: QModelIndex | None = None) -> int:
                return len(self.headers)

            def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
                if not index.isValid():
                    return None
                r = self.rows[index.row()]
                c = index.column()

                if role == Qt.ItemDataRole.DisplayRole:
                    if c == 0:
                        return r.chassis_number
                    if c == 1:
                        return r.model_name
                    if c == 2:
                        return r.color
                    if c == 3:
                        return r.status
                    if c == 4:
                        return f"{float(r.cash_unit_price or 0.0):,.2f}"
                    if c == 5:
                        return f"{float(r.credit_unit_price or 0.0):,.2f}"

                if role == Qt.ItemDataRole.TextAlignmentRole:
                    if c in (4, 5):
                        return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                return None

            def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
                if role != Qt.ItemDataRole.DisplayRole:
                    return None
                if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.headers):
                    return self.headers[section]
                return super().headerData(section, orientation, role)

            def add_row(self, row: _SelectedMotorcycleRow) -> None:
                self.beginInsertRows(QModelIndex(), len(self.rows), len(self.rows))
                self.rows.append(row)
                self.endInsertRows()

            def remove_row(self, row_index: int) -> None:
                if row_index < 0 or row_index >= len(self.rows):
                    return
                self.beginRemoveRows(QModelIndex(), row_index, row_index)
                self.rows.pop(row_index)
                self.endRemoveRows()

        dlg = QDialog(self)
        dlg.setWindowTitle("New Financing Application")
        dlg.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, True)
        dlg.setMinimumSize(720, 640)
        dlg.resize(980, 720)
        dlg.setStyleSheet(
            """
            QDialog { background-color: #f5f7fb; }
            QLabel { font-size: 13px; color: #2c3e50; font-weight: 600; }

            QFrame#dialogContainer {
                background: white;
                border: 1px solid #e9ecef;
                border-radius: 12px;
            }

            QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit, QTextEdit {
                padding: 9px 10px;
                border: 1px solid #dfe3ea;
                border-radius: 8px;
                background-color: white;
                font-size: 13px;
            }
            QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus, QDateEdit:focus, QTextEdit:focus {
                border: 2px solid #2f80ed;
            }
            QComboBox::drop-down {
                width: 28px;
                border-left: 1px solid #dfe3ea;
            }

            QPushButton { padding: 10px 22px; border-radius: 8px; font-weight: 700; font-size: 13px; }
            QPushButton#primaryButton { background: #2f80ed; color: white; border: 1px solid #2f80ed; }
            QPushButton#primaryButton:hover { background: #256fd1; border-color: #256fd1; }
            QPushButton#resetButton { background: #f1f3f5; color: #2c3e50; border: 1px solid #dfe3ea; }
            QPushButton#resetButton:hover { background: #e9ecef; }
            """
        )

        outer_layout = QVBoxLayout(dlg)
        outer_layout.setContentsMargins(16, 16, 16, 16)
        outer_layout.setSpacing(14)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)
        content_lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        container = QFrame()
        container.setObjectName("dialogContainer")
        container.setMaximumWidth(1040)
        lay = QVBoxLayout(container)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        content_lay.addWidget(container)
        scroll.setWidget(content)
        outer_layout.addWidget(scroll, 1)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        form.setColumnMinimumWidth(0, 170)
        form.setColumnStretch(0, 0)
        form.setColumnStretch(1, 1)

        def L(text: str) -> QLabel:
            lab = QLabel(text)
            lab.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return lab

        class _FocusPlaceholderFilter(QObject):
            def eventFilter(self, obj, event) -> bool:
                if event.type() == QEvent.Type.FocusIn:
                    if hasattr(obj, "placeholderText") and hasattr(obj, "setPlaceholderText"):
                        try:
                            if obj.property("_orig_placeholder") is None:
                                obj.setProperty("_orig_placeholder", obj.placeholderText())
                        except Exception:
                            pass
                        try:
                            obj.setPlaceholderText("")
                        except Exception:
                            pass
                if event.type() == QEvent.Type.FocusOut:
                    if hasattr(obj, "placeholderText") and hasattr(obj, "setPlaceholderText"):
                        try:
                            content = ""
                            if hasattr(obj, "text"):
                                content = str(obj.text() or "")
                            elif hasattr(obj, "toPlainText"):
                                content = str(obj.toPlainText() or "")
                            if not content.strip():
                                orig = obj.property("_orig_placeholder")
                                if orig is not None:
                                    obj.setPlaceholderText(str(orig))
                        except Exception:
                            pass
                return super().eventFilter(obj, event)

        focus_filter = _FocusPlaceholderFilter(dlg)

        customer_combo = QComboBox()
        customer_combo.setEditable(True)
        customer_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        customer_combo.addItem("Select Customer")
        for _, label in self._customer_cache:
            customer_combo.addItem(label)
        customer_completer = QCompleter(customer_combo.model(), customer_combo)
        customer_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        customer_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        customer_completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        customer_completer.setWrapAround(False)
        customer_combo.setCompleter(customer_completer)
        if customer_combo.lineEdit():
            customer_combo.lineEdit().setPlaceholderText("Type customer name / CNIC / phone...")
            customer_combo.lineEdit().installEventFilter(focus_filter)

        applicant_type = QComboBox()
        applicant_type.addItems(["CUSTOMER", "DEALER"])

        term_spin = QSpinBox()
        term_spin.setRange(1, 60)
        term_spin.setValue(2)

        down_payment_amount_spin = QDoubleSpinBox()
        down_payment_amount_spin.setRange(0.0, 99999999.0)
        down_payment_amount_spin.setDecimals(2)
        down_payment_amount_spin.setPrefix("Rs. ")
        if down_payment_amount_spin.lineEdit():
            down_payment_amount_spin.lineEdit().installEventFilter(focus_filter)

        chassis_combo = QComboBox()
        chassis_combo.setEditable(True)
        chassis_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        chassis_combo.addItem("Search Chassis...")
        if chassis_combo.lineEdit():
            chassis_combo.lineEdit().setPlaceholderText("Type chassis number...")
            chassis_combo.lineEdit().installEventFilter(focus_filter)

        color_input = QLineEdit()
        color_input.setPlaceholderText("Color")
        color_input.installEventFilter(focus_filter)

        model_display = QLineEdit()
        model_display.setReadOnly(True)
        model_display.setPlaceholderText("Model")

        cash_unit_price_spin = QDoubleSpinBox()
        cash_unit_price_spin.setRange(0.0, 99999999.0)
        cash_unit_price_spin.setDecimals(2)
        cash_unit_price_spin.setPrefix("Rs. ")
        if cash_unit_price_spin.lineEdit():
            cash_unit_price_spin.lineEdit().installEventFilter(focus_filter)

        credit_unit_price_spin = QDoubleSpinBox()
        credit_unit_price_spin.setRange(0.0, 99999999.0)
        credit_unit_price_spin.setDecimals(2)
        credit_unit_price_spin.setPrefix("Rs. ")
        if credit_unit_price_spin.lineEdit():
            credit_unit_price_spin.lineEdit().installEventFilter(focus_filter)

        btn_add_motorcycle = QPushButton("Add Motorcycle")
        btn_add_motorcycle.setObjectName("primaryButton")

        selected_model = _SelectedMotorcyclesModel()
        selected_table = QTableView()
        selected_table.setModel(selected_model)
        selected_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        selected_table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        selected_table.horizontalHeader().setStretchLastSection(True)
        selected_table.verticalHeader().setVisible(False)
        selected_table.setAlternatingRowColors(True)
        selected_table.setMinimumHeight(220)

        btn_remove_motorcycle = QPushButton("Remove Selected")
        btn_remove_motorcycle.setObjectName("resetButton")

        motorcycles_by_label: Dict[str, int] = {}
        motorcycles_cache: Dict[int, Dict[str, object]] = {}

        def load_motorcycles_for_chassis_search() -> None:
            db = SessionLocal()
            try:
                rows = (
                    db.query(Motorcycle, ProductModel)
                    .join(ProductModel, Motorcycle.product_model_id == ProductModel.id)
                    .order_by(Motorcycle.id.desc())
                    .limit(6000)
                    .all()
                )
                chassis_combo.blockSignals(True)
                chassis_combo.clear()
                chassis_combo.addItem("Search Chassis...")
                motorcycles_by_label.clear()
                motorcycles_cache.clear()
                for m, pm in rows:
                    label = f"{m.chassis_number} | {pm.model_name} | {m.color or ''} | {m.status} | #{m.id}"
                    motorcycles_by_label[label] = int(m.id)
                    motorcycles_cache[int(m.id)] = {
                        "chassis": str(m.chassis_number or ""),
                        "status": str(m.status or ""),
                        "color": str(m.color or ""),
                        "product_model_id": int(m.product_model_id),
                        "model_name": str(pm.model_name or ""),
                        "sale_price": float(m.sale_price or 0.0),
                    }
                    chassis_combo.addItem(label)
                chassis_combo.setCurrentIndex(0)
                completer = QCompleter(chassis_combo.model(), chassis_combo)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
                completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
                completer.setWrapAround(False)
                chassis_combo.setCompleter(completer)
                chassis_combo.blockSignals(False)
            finally:
                db.close()

        def get_latest_cash_price(db, product_model_id: int) -> Optional[float]:
            now = dt.datetime.utcnow()
            p = (
                db.query(Price)
                .filter(Price.product_model_id == int(product_model_id))
                .filter((Price.expiration_date.is_(None)) | (Price.expiration_date > now))
                .order_by(Price.effective_date.desc())
                .first()
            )
            if not p:
                return None
            try:
                return float(p.total_price or 0.0)
            except Exception:
                return None

        def on_chassis_changed(text: str) -> None:
            label = (text or "").strip()
            mid = motorcycles_by_label.get(label)
            if not mid:
                return
            info = motorcycles_cache.get(int(mid)) or {}
            model_display.setText(str(info.get("model_name") or ""))
            color_input.setText(str(info.get("color") or ""))
            db = SessionLocal()
            try:
                pm_id = int(info.get("product_model_id") or 0)
                cash_price = get_latest_cash_price(db, pm_id)
                if cash_price is None or cash_price <= 0:
                    cash_price = float(info.get("sale_price") or 0.0)
                if cash_price and cash_price > 0:
                    cash_unit_price_spin.setValue(float(cash_price))
                    if credit_unit_price_spin.value() <= 0:
                        credit_unit_price_spin.setValue(float(cash_price))
            finally:
                db.close()

        chassis_combo.currentTextChanged.connect(on_chassis_changed)  # type: ignore[arg-type]

        load_motorcycles_for_chassis_search()

        for w in (
            customer_combo,
            applicant_type,
            term_spin,
            down_payment_amount_spin,
            chassis_combo,
            model_display,
            color_input,
            cash_unit_price_spin,
            credit_unit_price_spin,
        ):
            try:
                w.setMinimumHeight(38)
            except Exception:
                pass

        form.addWidget(L("Customer"), 0, 0)
        form.addWidget(customer_combo, 0, 1)
        form.addWidget(L("Applicant Type"), 1, 0)
        form.addWidget(applicant_type, 1, 1)
        form.addWidget(L("Term (Months)"), 2, 0)
        form.addWidget(term_spin, 2, 1)
        form.addWidget(L("Down Payment Amount"), 3, 0)
        form.addWidget(down_payment_amount_spin, 3, 1)

        sep = QLabel("Motorcycle Details")
        sep.setStyleSheet("font-weight: 700; font-size: 14px; margin-top: 6px;")
        lay.addLayout(form)
        lay.addWidget(sep)

        item_form = QGridLayout()
        item_form.setHorizontalSpacing(14)
        item_form.setVerticalSpacing(12)
        item_form.setColumnMinimumWidth(0, 170)
        item_form.setColumnStretch(0, 0)
        item_form.setColumnStretch(1, 1)

        item_form.addWidget(L("Chassis"), 0, 0)
        item_form.addWidget(chassis_combo, 0, 1)
        item_form.addWidget(L("Model"), 1, 0)
        item_form.addWidget(model_display, 1, 1)
        item_form.addWidget(L("Color"), 2, 0)
        item_form.addWidget(color_input, 2, 1)
        item_form.addWidget(L("Cash Price"), 3, 0)
        item_form.addWidget(cash_unit_price_spin, 3, 1)
        item_form.addWidget(L("Credit Price"), 4, 0)
        item_form.addWidget(credit_unit_price_spin, 4, 1)

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_add_motorcycle)
        btn_row.addWidget(btn_remove_motorcycle)
        btn_row.addStretch(1)
        item_form.addLayout(btn_row, 5, 0, 1, 2)

        lay.addLayout(item_form)
        selected_title = QLabel("Selected Motorcycles")
        selected_title.setStyleSheet("font-weight: 700; font-size: 14px; margin-top: 6px;")
        lay.addWidget(selected_title)
        try:
            hdr = selected_table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        except Exception:
            pass
        lay.addWidget(selected_table, 1)

        notes = QTextEdit()
        notes.setPlaceholderText("Optional notes...")
        notes.setFixedHeight(80)
        lay.addWidget(notes)
        notes.installEventFilter(focus_filter)

        def _wire_enter_navigation(widgets: List[QWidget]) -> None:
            focusable: List[QWidget] = [w for w in widgets if w is not None]

            def go_next(idx: int) -> None:
                if not focusable:
                    return
                nxt = focusable[(idx + 1) % len(focusable)]
                nxt.setFocus()

            for i, w in enumerate(focusable):
                if isinstance(w, QComboBox) and w.isEditable() and w.lineEdit():
                    w.lineEdit().returnPressed.connect(lambda i=i: go_next(i))  # type: ignore[attr-defined]
                elif hasattr(w, "lineEdit") and callable(getattr(w, "lineEdit")):
                    try:
                        le = w.lineEdit()
                        if le:
                            le.returnPressed.connect(lambda i=i: go_next(i))  # type: ignore[attr-defined]
                    except Exception:
                        pass
                elif isinstance(w, QLineEdit):
                    w.returnPressed.connect(lambda i=i: go_next(i))  # type: ignore[attr-defined]

        _wire_enter_navigation(
            [
                customer_combo,
                applicant_type,
                term_spin,
                down_payment_amount_spin,
                chassis_combo,
                color_input,
                cash_unit_price_spin,
                credit_unit_price_spin,
                btn_add_motorcycle,
            ]
        )

        def get_selected_motorcycle_id() -> Optional[int]:
            label = chassis_combo.currentText().strip()
            mid = motorcycles_by_label.get(label)
            if mid:
                return int(mid)

            typed = (chassis_combo.currentText() or "").strip().upper()
            if typed and typed != "SEARCH CHASSIS...":
                chassis_only = typed.split("|")[0].strip()
                for k, v in motorcycles_cache.items():
                    if str(v.get("chassis") or "").strip().upper() == chassis_only:
                        return int(k)
            return None

        def add_selected_motorcycle_to_list() -> None:
            mid = get_selected_motorcycle_id()
            if not mid:
                QMessageBox.warning(dlg, "Selection Required", "Please select a chassis number.")
                return
            info = motorcycles_cache.get(int(mid)) or {}
            status = str(info.get("status") or "")
            if status.upper() != "IN_STOCK":
                QMessageBox.warning(dlg, "Not Available", "Selected motorcycle is not available in stock.")
                return
            for r in selected_model.rows:
                if int(r.motorcycle_id) == int(mid):
                    QMessageBox.warning(dlg, "Already Added", "This chassis is already added in the list.")
                    return
            cash_price = float(cash_unit_price_spin.value())
            credit_price = float(credit_unit_price_spin.value())
            if credit_price <= 0:
                QMessageBox.warning(dlg, "Price Required", "Credit price is required.")
                return
            if cash_price <= 0:
                QMessageBox.warning(dlg, "Price Required", "Cash price is required.")
                return
            row = _SelectedMotorcycleRow(
                motorcycle_id=int(mid),
                chassis_number=str(info.get("chassis") or ""),
                model_name=str(info.get("model_name") or ""),
                color=str(color_input.text() or info.get("color") or ""),
                status=status,
                cash_unit_price=cash_price,
                credit_unit_price=credit_price,
            )
            selected_model.add_row(row)
            chassis_combo.setCurrentIndex(0)
            model_display.clear()
            color_input.clear()

        def remove_selected_motorcycle_from_list() -> None:
            sel = selected_table.selectionModel().selectedRows()
            if not sel:
                return
            selected_model.remove_row(sel[0].row())

        btn_add_motorcycle.clicked.connect(add_selected_motorcycle_to_list)  # type: ignore[arg-type]
        btn_remove_motorcycle.clicked.connect(remove_selected_motorcycle_from_list)  # type: ignore[arg-type]

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        save_btn = btns.button(QDialogButtonBox.StandardButton.Save)
        cancel_btn = btns.button(QDialogButtonBox.StandardButton.Cancel)
        if save_btn:
            save_btn.setObjectName("primaryButton")
            save_btn.setText("Save")
        if cancel_btn:
            cancel_btn.setObjectName("resetButton")
            cancel_btn.setText("Cancel")
            cancel_btn.clicked.connect(dlg.reject)  # type: ignore[arg-type]
        outer_layout.addWidget(btns)

        def on_save() -> None:
            customer_label = customer_combo.currentText().strip()
            cid = self._customer_label_to_id.get(customer_label)
            if not cid:
                QMessageBox.warning(dlg, "Customer Required", "Please select a customer.")
                return
            if not selected_model.rows:
                QMessageBox.warning(dlg, "Motorcycle Required", "Please add at least one motorcycle (chassis) in the list.")
                return

            db = SessionLocal()
            try:
                app = financing_service.create_application(
                    db=db,
                    customer_id=cid,
                    applicant_type=applicant_type.currentText(),
                    requested_term_months=int(term_spin.value()),
                    down_payment_amount=float(down_payment_amount_spin.value()),
                )
                for r in selected_model.rows:
                    moto = db.query(Motorcycle).filter(Motorcycle.id == int(r.motorcycle_id)).first()
                    if not moto:
                        raise ValueError(f"Motorcycle not found for chassis: {r.chassis_number}")
                    financing_service.add_application_item(
                        db=db,
                        application_id=app.id,
                        product_model_id=int(moto.product_model_id) if getattr(moto, "product_model_id", None) else None,
                        motorcycle_id=int(moto.id),
                        color=str(r.color or moto.color or ""),
                        quantity=1,
                        cash_unit_price=float(r.cash_unit_price or 0.0),
                        unit_price=float(r.credit_unit_price or 0.0),
                    )

                financing_service.set_down_payment_amount(db, app.id, float(down_payment_amount_spin.value()))
                financing_service.submit_application(db, app.id)

                QMessageBox.information(dlg, "Saved", "Application submitted successfully.")
                self.refresh()

                selected_model.beginResetModel()
                selected_model.rows = []
                selected_model.endResetModel()
                chassis_combo.setCurrentIndex(0)
                model_display.clear()
                color_input.clear()
                cash_unit_price_spin.setValue(0.0)
                credit_unit_price_spin.setValue(0.0)
                down_payment_amount_spin.setValue(0.0)
                term_spin.setValue(2)
                load_motorcycles_for_chassis_search()
                customer_combo.setFocus()
            except Exception as exc:
                QMessageBox.critical(dlg, "Error", str(exc))
            finally:
                db.close()

        if save_btn:
            save_btn.clicked.connect(on_save)  # type: ignore[arg-type]

        dlg.exec()
        return

    def _assess_selected_app(self) -> None:
        return

    def _approve_selected_app(self) -> None:
        return

    def _reject_selected_app(self) -> None:
        return

    def _create_loan_for_selected_app(self) -> None:
        return

    def _view_selected_loan_schedule(self) -> None:
        loan_id = self._selected_loan_id()
        if not loan_id:
            QMessageBox.warning(self, "Selection Required", "Please select a loan.")
            return
        db = SessionLocal()
        try:
            loan = db.query(FinanceLoan).filter(FinanceLoan.id == int(loan_id)).first()
            if not loan:
                raise ValueError("Loan not found.")
            insts = (
                db.query(FinanceInstallment)
                .filter(FinanceInstallment.loan_id == loan.id)
                .order_by(FinanceInstallment.installment_no.asc())
                .all()
            )
        finally:
            db.close()

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Schedule - {loan.loan_number}")
        dlg.setMinimumSize(900, 600)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        table = QTableView()
        model = _InstallmentsTableModel(insts)
        table.setModel(model)
        table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        lay.addWidget(table, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        dlg.exec()

    def _record_payment_for_selected_loan(self) -> None:
        loan_id = self._selected_loan_id()
        if not loan_id:
            QMessageBox.warning(self, "Selection Required", "Please select a loan.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Record Payment")
        dlg.setFixedWidth(520)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(25, 25, 25, 25)
        lay.setSpacing(18)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)

        amount = QDoubleSpinBox()
        amount.setRange(0.0, 99999999.0)
        amount.setDecimals(2)
        amount.setPrefix("Rs. ")

        method = QComboBox()
        method.addItems(["CASH", "BANK_TRANSFER", "CHEQUE", "ONLINE", "CARD"])

        ref = QLineEdit()
        ref.setPlaceholderText("Optional reference / receipt number")

        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDate(dt.date.today())

        form.addWidget(QLabel("Amount"), 0, 0)
        form.addWidget(amount, 0, 1)
        form.addWidget(QLabel("Method"), 1, 0)
        form.addWidget(method, 1, 1)
        form.addWidget(QLabel("Reference"), 2, 0)
        form.addWidget(ref, 2, 1)
        form.addWidget(QLabel("Date"), 3, 0)
        form.addWidget(date_edit, 3, 1)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        qd = date_edit.date()
        ts = dt.datetime(qd.year(), qd.month(), qd.day(), dt.datetime.now().hour, dt.datetime.now().minute)

        db = SessionLocal()
        try:
            financing_service.record_payment(
                db=db,
                loan_id=int(loan_id),
                amount=float(amount.value()),
                method=method.currentText(),
                reference_number=ref.text(),
                timestamp=ts,
            )
            QMessageBox.information(self, "Saved", "Payment recorded successfully.")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
        finally:
            db.close()

    def _show_payoff_for_selected_loan(self) -> None:
        loan_id = self._selected_loan_id()
        if not loan_id:
            QMessageBox.warning(self, "Selection Required", "Please select a loan.")
            return
        db = SessionLocal()
        try:
            payoff = financing_service.calculate_payoff(db, int(loan_id))
            QMessageBox.information(
                self,
                "Payoff",
                f"Principal: {payoff['outstanding_principal']:,.2f}\n"
                f"Interest: {payoff['outstanding_interest']:,.2f}\n"
                f"Fees: {payoff['outstanding_fees']:,.2f}\n\n"
                f"Total: {payoff['payoff_total']:,.2f}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
        finally:
            db.close()

    def _refinance_selected_loan(self) -> None:
        loan_id = self._selected_loan_id()
        if not loan_id:
            QMessageBox.warning(self, "Selection Required", "Please select a loan.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Refinance Loan")
        dlg.setFixedWidth(520)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(25, 25, 25, 25)
        lay.setSpacing(18)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)

        term = QSpinBox()
        term.setRange(12, 60)
        term.setValue(36)

        rate = QDoubleSpinBox()
        rate.setRange(0.0, 60.0)
        rate.setDecimals(2)
        rate.setValue(22.0)
        rate.setSuffix(" %")

        fees = QDoubleSpinBox()
        fees.setRange(0.0, 99999999.0)
        fees.setDecimals(2)
        fees.setPrefix("Rs. ")

        form.addWidget(QLabel("New Term (Months)"), 0, 0)
        form.addWidget(term, 0, 1)
        form.addWidget(QLabel("New Interest Rate"), 1, 0)
        form.addWidget(rate, 1, 1)
        form.addWidget(QLabel("Fees"), 2, 0)
        form.addWidget(fees, 2, 1)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Refinance")
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        db = SessionLocal()
        try:
            new_loan = financing_service.refinance_loan(
                db=db,
                old_loan_id=int(loan_id),
                new_term_months=int(term.value()),
                new_interest_rate_annual=float(rate.value()),
                fees=float(fees.value()),
            )
            QMessageBox.information(self, "Refinanced", f"New Loan: {new_loan.loan_number}")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
        finally:
            db.close()

    def _show_portal_token_for_selected_loan(self) -> None:
        loan_id = self._selected_loan_id()
        if not loan_id:
            QMessageBox.warning(self, "Selection Required", "Please select a loan.")
            return
        db = SessionLocal()
        try:
            loan = db.query(FinanceLoan).filter(FinanceLoan.id == int(loan_id)).first()
            if not loan:
                raise ValueError("Loan not found.")
            tok = financing_service.ensure_portal_token(db, int(loan.customer_id))
            QMessageBox.information(
                self,
                "Portal Token",
                f"Token:\n{tok.token}\n\nPortal Link:\n/credit-portal/{tok.token}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
        finally:
            db.close()

    def refresh(self) -> None:
        db = SessionLocal()
        try:
            metrics = financing_service.portfolio_metrics(db)
            self.card_active_loans.value_label.setText(f"{int(metrics['active_loans']):,}")
            self.card_outstanding.value_label.setText(f"{metrics['total_outstanding']:,.2f}")
            self.card_overdue.value_label.setText(f"{int(metrics['overdue_installments']):,}")

            status_filter = self.app_status_filter.currentText().strip().upper()
            search = self.app_search.text().strip().upper()
            q = db.query(FinanceApplication).order_by(FinanceApplication.id.desc())
            if status_filter != "ALL":
                q = q.filter(FinanceApplication.status == status_filter)
            apps = q.limit(500).all()
            app_rows: List[FinanceApplicationRow] = []
            for a in apps:
                cust_name = ""
                try:
                    cust_name = a.customer.name if a.customer else ""
                except Exception:
                    cust_name = ""
                if search and search not in (cust_name or "").upper() and search not in (str(getattr(a.customer, "cnic", "") or "").upper()):
                    continue
                app_rows.append(
                    FinanceApplicationRow(
                        app_id=int(a.id),
                        created_at=a.created_at,
                        customer_name=cust_name,
                        applicant_type=str(a.applicant_type or ""),
                        total=float(a.requested_total_price or 0.0),
                        financed=float(a.requested_financed_amount or 0.0),
                        term=int(a.requested_term_months or 0),
                        dp_pct=float(a.down_payment_percent or 0.0),
                        rate=float(a.interest_rate_annual or 0.0),
                        score=int(a.credit_score) if a.credit_score is not None else None,
                        tier=str(a.risk_tier or ""),
                        status=str(a.status or ""),
                    )
                )
            self.apps_model.update_rows(app_rows)

            loan_status = self.loan_status_filter.currentText().strip().upper()
            loan_search = self.loan_search.text().strip().upper()
            ql = db.query(FinanceLoan).order_by(FinanceLoan.id.desc())
            if loan_status != "ALL":
                ql = ql.filter(FinanceLoan.status == loan_status)
            loans = ql.limit(500).all()
            loan_rows: List[FinanceLoanRow] = []
            for l in loans:
                cust_name = ""
                try:
                    cust_name = l.customer.name if l.customer else ""
                except Exception:
                    cust_name = ""
                if loan_search and (loan_search not in (l.loan_number or "").upper()) and (loan_search not in (cust_name or "").upper()):
                    continue
                loan_rows.append(
                    FinanceLoanRow(
                        loan_id=int(l.id),
                        loan_number=str(l.loan_number or ""),
                        customer_name=cust_name,
                        financed=float(l.financed_amount or 0.0),
                        emi=float(l.emi_amount or 0.0),
                        next_due=l.next_due_date,
                        status=str(l.status or ""),
                    )
                )
            self.loans_model.update_rows(loan_rows)
        finally:
            db.close()


class _InstallmentsTableModel(QAbstractTableModel):
    headers = ["#", "Due Date", "Principal", "Interest", "Fees", "Total", "Paid", "Status"]

    def __init__(self, rows: List[FinanceInstallment]) -> None:
        super().__init__()
        self._rows = rows or []

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r = self._rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return str(r.installment_no)
            if col == 1:
                return r.due_date.strftime("%Y-%m-%d") if r.due_date else ""
            if col == 2:
                return f"{float(r.principal_due or 0.0):,.2f}"
            if col == 3:
                return f"{float(r.interest_due or 0.0):,.2f}"
            if col == 4:
                return f"{float(r.fees_due or 0.0):,.2f}"
            if col == 5:
                return f"{float(r.total_due or 0.0):,.2f}"
            if col == 6:
                return f"{float(r.paid_total or 0.0):,.2f}"
            if col == 7:
                return str(r.status or "")

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in (0, 1, 7):
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.headers):
            return self.headers[section]
        return super().headerData(section, orientation, role)
