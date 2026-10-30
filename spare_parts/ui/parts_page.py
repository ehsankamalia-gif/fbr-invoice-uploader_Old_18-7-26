"""Parts master screen: searchable/filterable list + Add/Edit dialog.

PyQt6 only - no imports from app.qt_ui or any other app package (see
spare_parts/__init__.py). Visual style is hand-matched to the rest of the
app (not imported from it, which would violate independence).
"""
from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spare_parts.db.base import get_spare_session
from spare_parts.services import parts_service, stock_service, stock_import_export
from spare_parts.services.parts_service import SparePartsValidationError
from spare_parts.ui.barcode_label_dialog import BarcodeLabelDialog
from spare_parts.ui.bulk_price_update_dialog import BulkPriceUpdateDialog
from spare_parts.ui.stock_adjustment_dialog import StockAdjustmentDialog
from spare_parts.ui.stock_ledger_dialog import StockLedgerDialog
from spare_parts.ui.widgets import NoScrollComboBox, NoScrollDoubleSpinBox, NoScrollSpinBox
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)

_UNITS = ["pcs", "set", "box", "litre", "kg", "meter"]

_GROUP_STYLE = """
    QFrame#spFormGroup {
        background-color: white;
        border: 1px solid #e9ecef;
        border-radius: 8px;
    }
"""

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


class PartDialog(QDialog):
    """Add/Edit a single sp_parts row."""

    def __init__(self, part_id: int | None = None, parent=None):
        super().__init__(parent)
        self.part_id = part_id
        self.setWindowTitle("Edit Part" if part_id else "Add Part")
        self.setMinimumWidth(480)
        self.resize(520, 640)
        self._saving = False

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self.part_no_input = QLineEdit()
        self.part_no_input.setPlaceholderText("e.g. HD-1234")
        form.addRow("Part No. *", self.part_no_input)

        self.name_input = QLineEdit()
        form.addRow("Name *", self.name_input)

        cat_row = QHBoxLayout()
        self.category_combo = NoScrollComboBox()
        self.category_combo.addItem("(none)", None)
        cat_add_btn = QPushButton("+")
        cat_add_btn.setFixedWidth(28)
        cat_add_btn.setToolTip("Add new category")
        cat_add_btn.clicked.connect(self._on_add_category)
        cat_row.addWidget(self.category_combo, 1)
        cat_row.addWidget(cat_add_btn)
        form.addRow("Category", cat_row)

        brand_row = QHBoxLayout()
        self.brand_combo = NoScrollComboBox()
        self.brand_combo.addItem("(none)", None)
        brand_add_btn = QPushButton("+")
        brand_add_btn.setFixedWidth(28)
        brand_add_btn.setToolTip("Add new brand")
        brand_add_btn.clicked.connect(self._on_add_brand)
        brand_row.addWidget(self.brand_combo, 1)
        brand_row.addWidget(brand_add_btn)
        form.addRow("Brand", brand_row)

        self.compatible_models_input = QLineEdit()
        self.compatible_models_input.setPlaceholderText("e.g. CG125, CD70, Pridor")
        form.addRow("Compatible Models", self.compatible_models_input)

        self.unit_combo = NoScrollComboBox()
        self.unit_combo.setEditable(True)
        self.unit_combo.addItems(_UNITS)
        form.addRow("Unit", self.unit_combo)

        self.pack_size_spin = NoScrollSpinBox()
        self.pack_size_spin.setRange(1, 100000)
        self.pack_size_spin.setValue(1)
        self.pack_size_spin.setToolTip("Units per box/carton, for wholesale selling by pack.")
        form.addRow("Pack Size", self.pack_size_spin)

        self.barcode_input = QLineEdit()
        form.addRow("Barcode", self.barcode_input)

        self.rack_location_input = QLineEdit()
        form.addRow("Rack Location", self.rack_location_input)

        self.cost_price_spin = NoScrollDoubleSpinBox()
        self.cost_price_spin.setRange(0, 99_999_999)
        self.cost_price_spin.setDecimals(2)
        self.cost_price_spin.setToolTip(
            "Moving-average cost. From Phase 2 onward this is updated "
            "automatically by purchases - edit it by hand only to set an "
            "opening cost for a brand-new part."
        )
        form.addRow("Cost Price", self.cost_price_spin)

        self.retail_price_spin = NoScrollDoubleSpinBox()
        self.retail_price_spin.setRange(0, 99_999_999)
        self.retail_price_spin.setDecimals(2)
        form.addRow("Retail Price", self.retail_price_spin)

        self.wholesale_price_spin = NoScrollDoubleSpinBox()
        self.wholesale_price_spin.setRange(0, 99_999_999)
        self.wholesale_price_spin.setDecimals(2)
        form.addRow("Wholesale Price", self.wholesale_price_spin)

        self.min_wholesale_qty_spin = NoScrollSpinBox()
        self.min_wholesale_qty_spin.setRange(1, 100000)
        self.min_wholesale_qty_spin.setValue(1)
        form.addRow("Min Wholesale Qty", self.min_wholesale_qty_spin)

        self.reorder_level_spin = NoScrollSpinBox()
        self.reorder_level_spin.setRange(0, 1_000_000)
        form.addRow("Reorder Level", self.reorder_level_spin)

        self.reorder_qty_spin = NoScrollSpinBox()
        self.reorder_qty_spin.setRange(0, 1_000_000)
        self.reorder_qty_spin.setToolTip(
            "Quantity suggested on the Reports > Reorder Suggestions tab once "
            "stock drops to/below Reorder Level. 0 = suggest bringing stock "
            "back up to Reorder Level itself."
        )
        form.addRow("Reorder Qty", self.reorder_qty_spin)

        self.warranty_days_spin = NoScrollSpinBox()
        self.warranty_days_spin.setRange(0, 36500)
        self.warranty_days_spin.setToolTip(
            "Days of warranty this part carries when sold. 0 = no warranty. "
            "Recorded per sale on the Reports > Warranty tab."
        )
        form.addRow("Warranty Days", self.warranty_days_spin)

        if part_id:
            # Stock is never set by editing a field - see
            # spare_parts/__init__.py. This is read-only, just to answer
            # "where do I see/change stock" from the one dialog a user
            # might expect it in.
            self.current_stock_display = QLineEdit()
            self.current_stock_display.setReadOnly(True)
            self.current_stock_display.setToolTip(
                "Use 'Adjust Stock' or 'View Stock Ledger' from the Parts "
                "list to add, remove, or review stock movements."
            )
            form.addRow("Current Stock", self.current_stock_display)
        else:
            self.opening_stock_spin = NoScrollSpinBox()
            self.opening_stock_spin.setRange(0, 1_000_000)
            self.opening_stock_spin.setValue(0)
            self.opening_stock_spin.setToolTip(
                "Quantity already on hand, if any - recorded as an opening "
                "stock-ledger entry once the part is saved."
            )
            form.addRow("Opening Stock", self.opening_stock_spin)

        self.notes_input = QPlainTextEdit()
        self.notes_input.setFixedHeight(60)
        form.addRow("Notes", self.notes_input)

        self.active_checkbox = QCheckBox("Active")
        self.active_checkbox.setChecked(True)
        if part_id:
            form.addRow("", self.active_checkbox)

        scroll_content = QWidget()
        scroll_content.setLayout(form)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area, 1)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_RESET_BTN)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        self.save_btn = QPushButton("Save (Ctrl+S)")
        self.save_btn.setStyleSheet(_PRIMARY_BTN)
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_save)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.reject)

        self.setTabOrder(self.part_no_input, self.name_input)
        self.setTabOrder(self.name_input, self.category_combo)
        self.setTabOrder(self.category_combo, self.brand_combo)
        self.setTabOrder(self.brand_combo, self.compatible_models_input)
        self.setTabOrder(self.compatible_models_input, self.unit_combo)
        self.setTabOrder(self.unit_combo, self.pack_size_spin)
        self.setTabOrder(self.pack_size_spin, self.barcode_input)
        self.setTabOrder(self.barcode_input, self.rack_location_input)
        self.setTabOrder(self.rack_location_input, self.cost_price_spin)
        self.setTabOrder(self.cost_price_spin, self.retail_price_spin)
        self.setTabOrder(self.retail_price_spin, self.wholesale_price_spin)
        self.setTabOrder(self.wholesale_price_spin, self.min_wholesale_qty_spin)
        self.setTabOrder(self.min_wholesale_qty_spin, self.reorder_level_spin)
        self.setTabOrder(self.reorder_level_spin, self.reorder_qty_spin)
        self.setTabOrder(self.reorder_qty_spin, self.warranty_days_spin)

        for line_edit in (self.part_no_input, self.name_input, self.compatible_models_input,
                          self.barcode_input, self.rack_location_input):
            line_edit.returnPressed.connect(self.focusNextChild)

        self._reload_lookups()
        if part_id:
            self._load_part(part_id)

    def _reload_lookups(self) -> None:
        db = get_spare_session()
        try:
            current_cat = self.category_combo.currentData()
            current_brand = self.brand_combo.currentData()

            self.category_combo.blockSignals(True)
            self.category_combo.clear()
            self.category_combo.addItem("(none)", None)
            for cat in parts_service.list_categories(db):
                self.category_combo.addItem(cat.name, cat.id)
            if current_cat is not None:
                idx = self.category_combo.findData(current_cat)
                if idx >= 0:
                    self.category_combo.setCurrentIndex(idx)
            self.category_combo.blockSignals(False)

            self.brand_combo.blockSignals(True)
            self.brand_combo.clear()
            self.brand_combo.addItem("(none)", None)
            for brand in parts_service.list_brands(db):
                self.brand_combo.addItem(brand.name, brand.id)
            if current_brand is not None:
                idx = self.brand_combo.findData(current_brand)
                if idx >= 0:
                    self.brand_combo.setCurrentIndex(idx)
            self.brand_combo.blockSignals(False)
        finally:
            db.close()

    def _on_add_category(self) -> None:
        name, ok = QInputDialog.getText(self, "Add Category", "Category name:")
        if not ok or not name.strip():
            return
        db = get_spare_session()
        try:
            cat = parts_service.create_category(db, name)
        except SparePartsValidationError as e:
            QMessageBox.warning(self, "Validation Error", str(e))
            return
        finally:
            db.close()
        self._reload_lookups()
        idx = self.category_combo.findData(cat.id)
        if idx >= 0:
            self.category_combo.setCurrentIndex(idx)

    def _on_add_brand(self) -> None:
        name, ok = QInputDialog.getText(self, "Add Brand", "Brand name:")
        if not ok or not name.strip():
            return
        db = get_spare_session()
        try:
            brand = parts_service.create_brand(db, name)
        except SparePartsValidationError as e:
            QMessageBox.warning(self, "Validation Error", str(e))
            return
        finally:
            db.close()
        self._reload_lookups()
        idx = self.brand_combo.findData(brand.id)
        if idx >= 0:
            self.brand_combo.setCurrentIndex(idx)

    def _load_part(self, part_id: int) -> None:
        db = get_spare_session()
        try:
            part = parts_service.get_part(db, part_id)
            if not part:
                QMessageBox.critical(self, "Error", f"Part id={part_id} not found.")
                self.reject()
                return
            self.part_no_input.setText(part.part_no)
            self.name_input.setText(part.name)
            if part.category_id:
                idx = self.category_combo.findData(part.category_id)
                if idx >= 0:
                    self.category_combo.setCurrentIndex(idx)
            if part.brand_id:
                idx = self.brand_combo.findData(part.brand_id)
                if idx >= 0:
                    self.brand_combo.setCurrentIndex(idx)
            self.compatible_models_input.setText(part.compatible_models or "")
            self.unit_combo.setCurrentText(part.unit or "pcs")
            self.pack_size_spin.setValue(part.pack_size or 1)
            self.barcode_input.setText(part.barcode or "")
            self.rack_location_input.setText(part.rack_location or "")
            self.cost_price_spin.setValue(float(part.cost_price or 0))
            self.retail_price_spin.setValue(float(part.retail_price or 0))
            self.wholesale_price_spin.setValue(float(part.wholesale_price or 0))
            self.min_wholesale_qty_spin.setValue(part.min_wholesale_qty or 1)
            self.reorder_level_spin.setValue(part.reorder_level or 0)
            self.reorder_qty_spin.setValue(part.reorder_qty or 0)
            self.warranty_days_spin.setValue(part.warranty_days or 0)
            self.notes_input.setPlainText(part.notes or "")
            self.active_checkbox.setChecked(bool(part.is_active))
            current_stock = stock_service.get_current_stock(db, part_id)
            self.current_stock_display.setText(f"{current_stock} {part.unit or ''}".strip())
        finally:
            db.close()

    def _on_save(self) -> None:
        if self._saving:
            return
        self._saving = True
        self.save_btn.setEnabled(False)
        self.error_label.hide()
        try:
            fields = dict(
                part_no=self.part_no_input.text(),
                name=self.name_input.text(),
                category_id=self.category_combo.currentData(),
                brand_id=self.brand_combo.currentData(),
                compatible_models=self.compatible_models_input.text(),
                unit=self.unit_combo.currentText(),
                pack_size=self.pack_size_spin.value(),
                barcode=self.barcode_input.text(),
                rack_location=self.rack_location_input.text(),
                cost_price=Decimal(str(self.cost_price_spin.value())),
                retail_price=Decimal(str(self.retail_price_spin.value())),
                wholesale_price=Decimal(str(self.wholesale_price_spin.value())),
                min_wholesale_qty=self.min_wholesale_qty_spin.value(),
                reorder_level=self.reorder_level_spin.value(),
                reorder_qty=self.reorder_qty_spin.value(),
                warranty_days=self.warranty_days_spin.value(),
                notes=self.notes_input.toPlainText(),
            )
            db = get_spare_session()
            try:
                if self.part_id:
                    parts_service.update_part(db, self.part_id, **fields)
                    # is_active has its own setter (parts have no generic
                    # "is_active" field handler in update_part) - same
                    # two-call pattern as CustomerDialog._on_save.
                    parts_service.set_part_active(db, self.part_id, self.active_checkbox.isChecked())
                else:
                    new_part = parts_service.create_part(db, **fields)
                    opening_qty = self.opening_stock_spin.value()
                    if opening_qty > 0:
                        # A fresh part has no ledger history yet, so this is
                        # safe/unambiguous - see spare_parts/__init__.py on
                        # why stock otherwise is never set by a form field.
                        stock_service.add_ledger_entry(
                            db, part_id=new_part.id, qty_in=opening_qty,
                            reference_type="OPENING",
                            note="Opening stock set when part was created",
                        )
                        db.commit()
            finally:
                db.close()
            self.accept()
        except SparePartsValidationError as e:
            self.error_label.setText(str(e))
            self.error_label.show()
        except Exception as e:
            logger.error(f"Unexpected error saving part: {e}", exc_info=True)
            self.error_label.setText(f"Unexpected error: {e}")
            self.error_label.show()
        finally:
            self._saving = False
            self.save_btn.setEnabled(True)


class PartsPage(QWidget):
    """Searchable/filterable parts list with Add/Edit/Deactivate."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QLabel("Parts")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(header)

        toolbar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search part no, name, barcode, compatible model... (F2)")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        toolbar.addWidget(self.search_input, 2)

        self.category_filter = NoScrollComboBox()
        self.category_filter.addItem("All Categories", None)
        self.category_filter.currentIndexChanged.connect(self._reload)
        toolbar.addWidget(self.category_filter, 1)

        self.brand_filter = NoScrollComboBox()
        self.brand_filter.addItem("All Brands", None)
        self.brand_filter.currentIndexChanged.connect(self._reload)
        toolbar.addWidget(self.brand_filter, 1)

        self.show_inactive_checkbox = QCheckBox("Show inactive")
        self.show_inactive_checkbox.stateChanged.connect(self._reload)
        toolbar.addWidget(self.show_inactive_checkbox)

        toolbar.addStretch(1)

        sample_btn = QPushButton("Sample File")
        sample_btn.setStyleSheet(_RESET_BTN)
        sample_btn.setToolTip("Download a sample Excel/CSV file showing the import format")
        sample_btn.clicked.connect(self._on_sample_file_clicked)
        toolbar.addWidget(sample_btn)

        export_btn = QPushButton("Export")
        export_btn.setStyleSheet(_RESET_BTN)
        export_btn.setToolTip("Export all parts & current stock to Excel or CSV")
        export_btn.clicked.connect(self._on_export_clicked)
        toolbar.addWidget(export_btn)

        import_btn = QPushButton("Import")
        import_btn.setStyleSheet(_RESET_BTN)
        import_btn.setToolTip("Bulk create/update parts & stock from an Excel or CSV file")
        import_btn.clicked.connect(self._on_import_clicked)
        toolbar.addWidget(import_btn)

        bulk_price_btn = QPushButton("Bulk Price Update")
        bulk_price_btn.setStyleSheet(_RESET_BTN)
        bulk_price_btn.setToolTip("Apply a % or fixed change to cost/retail/wholesale price across a category or brand")
        bulk_price_btn.clicked.connect(self._on_bulk_price_update_clicked)
        toolbar.addWidget(bulk_price_btn)

        barcode_labels_btn = QPushButton("Print Barcode Labels")
        barcode_labels_btn.setStyleSheet(_RESET_BTN)
        barcode_labels_btn.setToolTip("Select one or more parts above, then print barcode labels for them")
        barcode_labels_btn.clicked.connect(self._on_print_barcode_labels_clicked)
        toolbar.addWidget(barcode_labels_btn)

        add_btn = QPushButton("+ Add Part (Ctrl+N)")
        add_btn.setStyleSheet(_PRIMARY_BTN)
        add_btn.clicked.connect(self._on_add_clicked)
        toolbar.addWidget(add_btn)

        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels([
            "Part No.", "Name", "Category", "Brand", "Unit", "Stock",
            "Cost", "Retail", "Wholesale", "Status",
        ])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # ExtendedSelection (not the original SingleSelection) so "Print
        # Barcode Labels" can act on several rows at once - every OTHER
        # action here (_selected_part_id) keys off currentRow(), which
        # stays well-defined (the single focused row) regardless of how
        # many rows are selected, so none of them needed to change.
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_edit_clicked)
        layout.addWidget(self.table, 1)

        action_row = QHBoxLayout()
        edit_btn = QPushButton("Edit Selected")
        edit_btn.setStyleSheet(_RESET_BTN)
        edit_btn.clicked.connect(self._on_edit_clicked)
        action_row.addWidget(edit_btn)

        view_stock_btn = QPushButton("View Stock Ledger")
        view_stock_btn.setStyleSheet(_RESET_BTN)
        view_stock_btn.clicked.connect(self._on_view_stock_ledger_clicked)
        action_row.addWidget(view_stock_btn)

        adjust_stock_btn = QPushButton("Adjust Stock")
        adjust_stock_btn.setStyleSheet(_PRIMARY_BTN)
        adjust_stock_btn.clicked.connect(self._on_adjust_stock_clicked)
        action_row.addWidget(adjust_stock_btn)

        self.toggle_active_btn = QPushButton("Deactivate Selected")
        self.toggle_active_btn.setStyleSheet(_RESET_BTN)
        self.toggle_active_btn.clicked.connect(self._on_toggle_active_clicked)
        action_row.addWidget(self.toggle_active_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._reload)

        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._on_add_clicked)
        QShortcut(QKeySequence(Qt.Key.Key_F2), self, activated=self.search_input.setFocus)

        self._reload_filters()
        self._reload()

    def _on_search_text_changed(self, _text: str) -> None:
        self._search_timer.start()

    def _reload_filters(self) -> None:
        db = get_spare_session()
        try:
            current_cat = self.category_filter.currentData()
            self.category_filter.blockSignals(True)
            self.category_filter.clear()
            self.category_filter.addItem("All Categories", None)
            for cat in parts_service.list_categories(db):
                self.category_filter.addItem(cat.name, cat.id)
            if current_cat is not None:
                idx = self.category_filter.findData(current_cat)
                if idx >= 0:
                    self.category_filter.setCurrentIndex(idx)
            self.category_filter.blockSignals(False)

            current_brand = self.brand_filter.currentData()
            self.brand_filter.blockSignals(True)
            self.brand_filter.clear()
            self.brand_filter.addItem("All Brands", None)
            for brand in parts_service.list_brands(db):
                self.brand_filter.addItem(brand.name, brand.id)
            if current_brand is not None:
                idx = self.brand_filter.findData(current_brand)
                if idx >= 0:
                    self.brand_filter.setCurrentIndex(idx)
            self.brand_filter.blockSignals(False)
        finally:
            db.close()

    def _reload(self) -> None:
        db = get_spare_session()
        try:
            parts = parts_service.search_parts(
                db,
                query=self.search_input.text(),
                category_id=self.category_filter.currentData(),
                brand_id=self.brand_filter.currentData(),
                active_only=not self.show_inactive_checkbox.isChecked(),
            )
            stock_by_id = stock_service.get_current_stock_bulk(db, [p.id for p in parts])
            self.table.setRowCount(len(parts))
            for row, part in enumerate(parts):
                self.table.setItem(row, 0, QTableWidgetItem(part.part_no))
                self.table.setItem(row, 1, QTableWidgetItem(part.name))
                self.table.setItem(row, 2, QTableWidgetItem(part.category.name if part.category else ""))
                self.table.setItem(row, 3, QTableWidgetItem(part.brand.name if part.brand else ""))
                self.table.setItem(row, 4, QTableWidgetItem(part.unit or ""))

                current_stock = stock_by_id.get(part.id, 0)
                stock_item = QTableWidgetItem(str(current_stock))
                if current_stock <= (part.reorder_level or 0):
                    stock_item.setForeground(Qt.GlobalColor.red)
                self.table.setItem(row, 5, stock_item)

                self.table.setItem(row, 6, QTableWidgetItem(f"{float(part.cost_price or 0):,.2f}"))
                self.table.setItem(row, 7, QTableWidgetItem(f"{float(part.retail_price or 0):,.2f}"))
                self.table.setItem(row, 8, QTableWidgetItem(f"{float(part.wholesale_price or 0):,.2f}"))
                status_item = QTableWidgetItem("Active" if part.is_active else "Inactive")
                if not part.is_active:
                    status_item.setForeground(Qt.GlobalColor.gray)
                self.table.setItem(row, 9, status_item)
                # Stash the id on the row for edit/toggle/stock-ledger actions.
                self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, part.id)
        finally:
            db.close()

    def _selected_part_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_part_ids(self) -> list[int]:
        """Every selected row's part id (for multi-select actions like
        Print Barcode Labels), in on-screen row order, de-duplicated."""
        ids: list[int] = []
        seen: set[int] = set()
        for index in self.table.selectionModel().selectedRows(0):
            item = self.table.item(index.row(), 0)
            part_id = item.data(Qt.ItemDataRole.UserRole) if item else None
            if part_id is not None and part_id not in seen:
                seen.add(part_id)
                ids.append(part_id)
        return ids

    def _on_add_clicked(self) -> None:
        dlg = PartDialog(parent=self)
        if dlg.exec():
            self._reload_filters()
            self._reload()

    def _on_edit_clicked(self) -> None:
        part_id = self._selected_part_id()
        if not part_id:
            QMessageBox.information(self, "No Selection", "Select a part first.")
            return
        dlg = PartDialog(part_id=part_id, parent=self)
        if dlg.exec():
            self._reload_filters()
            self._reload()

    def _on_view_stock_ledger_clicked(self) -> None:
        part_id = self._selected_part_id()
        if not part_id:
            QMessageBox.information(self, "No Selection", "Select a part first.")
            return
        dlg = StockLedgerDialog(part_id=part_id, parent=self)
        dlg.exec()

    def _on_adjust_stock_clicked(self) -> None:
        # Pre-fills the currently selected row if there is one, but the
        # dialog also has its own part picker, so no row needs to be
        # selected first - "Adjust Stock" works as a standalone action too.
        dlg = StockAdjustmentDialog(part_id=self._selected_part_id(), parent=self)
        if dlg.exec():
            self._reload()

    def _on_toggle_active_clicked(self) -> None:
        part_id = self._selected_part_id()
        if not part_id:
            QMessageBox.information(self, "No Selection", "Select a part first.")
            return
        db = get_spare_session()
        try:
            part = parts_service.get_part(db, part_id)
            if not part:
                return
            new_state = not part.is_active
            action = "activate" if new_state else "deactivate"
            confirm = QMessageBox.question(
                self, f"{action.title()} Part",
                f"{action.title()} part '{part.part_no} - {part.name}'?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            parts_service.set_part_active(db, part_id, new_state)
        finally:
            db.close()
        self._reload()

    # --- bulk import/export --------------------------------------------------

    def _on_sample_file_clicked(self) -> None:
        """Writes a ready-to-edit template (a couple of example rows,
        plus an Instructions sheet in the Excel version) - unlike
        Export, this needs no database read, since the examples are
        fixed sample data, not real parts."""
        path, chosen_filter = QFileDialog.getSaveFileName(
            self, "Download Sample Import File", "parts_and_stock_sample.xlsx",
            "Excel Files (*.xlsx);;CSV Files (*.csv)",
        )
        if not path:
            return
        if not path.lower().endswith((".xlsx", ".csv")):
            path += ".csv" if "csv" in chosen_filter.lower() else ".xlsx"

        try:
            if path.lower().endswith(".csv"):
                stock_import_export.write_sample_csv(path)
            else:
                stock_import_export.write_sample_xlsx(path)
        except Exception as e:
            logger.error(f"Writing sample import file failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Could Not Create Sample File", f"Could not write the file:\n{e}")
            return

        QMessageBox.information(
            self, "Sample File Ready",
            f"Saved a sample import file to:\n{path}\n\n"
            "Edit it with your own parts (or delete the example rows) and "
            "then use Import to load it.",
        )

    def _on_export_clicked(self) -> None:
        path, chosen_filter = QFileDialog.getSaveFileName(
            self, "Export Parts & Stock", "parts_and_stock.xlsx",
            "Excel Files (*.xlsx);;CSV Files (*.csv)",
        )
        if not path:
            return
        if not path.lower().endswith((".xlsx", ".csv")):
            path += ".csv" if "csv" in chosen_filter.lower() else ".xlsx"

        db = get_spare_session()
        try:
            rows = stock_import_export.export_rows(db)
        finally:
            db.close()

        try:
            if path.lower().endswith(".csv"):
                stock_import_export.write_csv(path, rows)
            else:
                stock_import_export.write_xlsx(path, rows)
        except Exception as e:
            logger.error(f"Parts/stock export failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Export Failed", f"Could not write the file:\n{e}")
            return

        QMessageBox.information(self, "Export Complete", f"Exported {len(rows)} part(s) to:\n{path}")

    def _on_import_clicked(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self, "Import Parts & Stock", "",
            "Excel/CSV Files (*.xlsx *.csv);;Excel Files (*.xlsx);;CSV Files (*.csv)",
        )
        if not path:
            return

        try:
            if path.lower().endswith(".csv"):
                rows = stock_import_export.read_csv(path)
            elif path.lower().endswith(".xlsx"):
                rows = stock_import_export.read_xlsx(path)
            else:
                QMessageBox.warning(self, "Unsupported File", "Only .xlsx and .csv files are supported.")
                return
        except SparePartsValidationError as e:
            QMessageBox.warning(self, "Import File Problem", str(e))
            return
        except Exception as e:
            logger.error(f"Failed to read import file: {e}", exc_info=True)
            QMessageBox.critical(self, "Import Failed", f"Could not read the file:\n{e}")
            return

        if not rows:
            QMessageBox.information(self, "Nothing To Import", "No data rows were found in this file.")
            return

        confirm = QMessageBox.question(
            self, "Confirm Import",
            f"This will create or update parts (and may adjust stock) from "
            f"{len(rows)} row(s) in this file. Continue?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        db = get_spare_session()
        try:
            result = stock_import_export.import_rows(db, rows)
        finally:
            db.close()

        self._reload_filters()
        self._reload()
        self._show_import_result(result)

    def _on_bulk_price_update_clicked(self) -> None:
        dlg = BulkPriceUpdateDialog(parent=self)
        if dlg.exec():
            self._reload()

    def _on_print_barcode_labels_clicked(self) -> None:
        part_ids = self._selected_part_ids()
        if not part_ids:
            QMessageBox.information(self, "No Selection", "Select one or more parts first.")
            return
        db = get_spare_session()
        try:
            parts = [parts_service.get_part(db, pid) for pid in part_ids]
            parts = [p for p in parts if p is not None]
        finally:
            db.close()
        dlg = BarcodeLabelDialog(parts, parent=self)
        dlg.exec()

    def _show_import_result(self, result) -> None:
        lines = [
            f"Created: {result.created}",
            f"Updated: {result.updated}",
            f"Stock adjusted: {result.stock_adjusted}",
            f"Errors: {len(result.errors)}",
        ]
        if result.errors:
            lines.append("")
            lines.append("Row errors:")
            for err in result.errors:
                lines.append(f"  Row {err.row_number} ({err.part_no}): {err.message}")

        dlg = QDialog(self)
        dlg.setWindowTitle("Import Results")
        dlg.setMinimumSize(480, 320)
        layout = QVBoxLayout(dlg)
        text = QPlainTextEdit("\n".join(lines))
        text.setReadOnly(True)
        layout.addWidget(text)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(_PRIMARY_BTN)
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
        dlg.exec()
        self._reload()
