"""Categories & Brands master screen: two simple list + Add/Edit/Delete
sub-tabs. Mirrors customers_page.py's pattern, except categories/brands have
no is_active flag - delete is a real hard-delete, blocked by the service
layer (SparePartsValidationError) when a part or subcategory still
references the row."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from spare_parts.db.base import get_spare_session
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import parts_service
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
        background-color: #fff5f5; color: #e74c3c; border: 1px solid #f5c6c6;
        border-radius: 4px; padding: 8px 16px;
    }
    QPushButton:hover { background-color: #fde3e3; }
"""


class CategoryDialog(QDialog):
    def __init__(self, category_id: int | None = None, parent=None):
        super().__init__(parent)
        self.category_id = category_id
        self.setWindowTitle("Edit Category" if category_id else "Add Category")
        self.setMinimumWidth(380)
        self._saving = False

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self.name_input = QLineEdit()
        form.addRow("Name *", self.name_input)

        self.parent_combo = NoScrollComboBox()
        form.addRow("Parent Category", self.parent_combo)

        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_RESET_BTN)
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        self.save_btn = QPushButton("Save (Ctrl+S)")
        self.save_btn.setStyleSheet(_PRIMARY_BTN)
        self.save_btn.setAutoDefault(False)
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_save)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.reject)

        self._load_parent_choices()
        if category_id:
            self._load_category(category_id)

    def _load_parent_choices(self) -> None:
        db = get_spare_session()
        try:
            choices = parts_service.get_valid_parent_choices(db, self.category_id)
        finally:
            db.close()
        self.parent_combo.addItem("(None - top level)", None)
        for cat in choices:
            self.parent_combo.addItem(cat.name, cat.id)

    def _load_category(self, category_id: int) -> None:
        db = get_spare_session()
        try:
            category = parts_service.get_category(db, category_id)
            if not category:
                QMessageBox.critical(self, "Error", f"Category id={category_id} not found.")
                self.reject()
                return
            self.name_input.setText(category.name)
            idx = self.parent_combo.findData(category.parent_id)
            if idx >= 0:
                self.parent_combo.setCurrentIndex(idx)
        finally:
            db.close()

    def _on_save(self) -> None:
        if self._saving:
            return
        self._saving = True
        self.save_btn.setEnabled(False)
        self.error_label.hide()
        try:
            name = self.name_input.text()
            parent_id = self.parent_combo.currentData()
            db = get_spare_session()
            try:
                if self.category_id:
                    parts_service.update_category(
                        db, self.category_id, name=name, parent_id=parent_id
                    )
                else:
                    parts_service.create_category(db, name=name, parent_id=parent_id)
            finally:
                db.close()
            self.accept()
        except SparePartsValidationError as e:
            self.error_label.setText(str(e))
            self.error_label.show()
        except Exception as e:
            logger.error(f"Unexpected error saving category: {e}", exc_info=True)
            self.error_label.setText(f"Unexpected error: {e}")
            self.error_label.show()
        finally:
            self._saving = False
            self.save_btn.setEnabled(True)


class BrandDialog(QDialog):
    def __init__(self, brand_id: int | None = None, parent=None):
        super().__init__(parent)
        self.brand_id = brand_id
        self.setWindowTitle("Edit Brand" if brand_id else "Add Brand")
        self.setMinimumWidth(380)
        self._saving = False

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self.name_input = QLineEdit()
        form.addRow("Name *", self.name_input)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_RESET_BTN)
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        self.save_btn = QPushButton("Save (Ctrl+S)")
        self.save_btn.setStyleSheet(_PRIMARY_BTN)
        self.save_btn.setAutoDefault(False)
        self.save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_save)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.reject)

        if brand_id:
            self._load_brand(brand_id)

    def _load_brand(self, brand_id: int) -> None:
        db = get_spare_session()
        try:
            brand = parts_service.get_brand(db, brand_id)
            if not brand:
                QMessageBox.critical(self, "Error", f"Brand id={brand_id} not found.")
                self.reject()
                return
            self.name_input.setText(brand.name)
        finally:
            db.close()

    def _on_save(self) -> None:
        if self._saving:
            return
        self._saving = True
        self.save_btn.setEnabled(False)
        self.error_label.hide()
        try:
            name = self.name_input.text()
            db = get_spare_session()
            try:
                if self.brand_id:
                    parts_service.update_brand(db, self.brand_id, name=name)
                else:
                    parts_service.create_brand(db, name=name)
            finally:
                db.close()
            self.accept()
        except SparePartsValidationError as e:
            self.error_label.setText(str(e))
            self.error_label.show()
        except Exception as e:
            logger.error(f"Unexpected error saving brand: {e}", exc_info=True)
            self.error_label.setText(f"Unexpected error: {e}")
            self.error_label.show()
        finally:
            self._saving = False
            self.save_btn.setEnabled(True)


class _CategoriesTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.addStretch(1)
        add_btn = QPushButton("+ Add Category")
        add_btn.setStyleSheet(_PRIMARY_BTN)
        add_btn.clicked.connect(self._on_add_clicked)
        toolbar.addWidget(add_btn)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Name", "Parent Category"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_edit_clicked)
        layout.addWidget(self.table, 1)

        action_row = QHBoxLayout()
        edit_btn = QPushButton("Edit Selected")
        edit_btn.setStyleSheet(_RESET_BTN)
        edit_btn.clicked.connect(self._on_edit_clicked)
        action_row.addWidget(edit_btn)

        delete_btn = QPushButton("Delete Selected")
        delete_btn.setStyleSheet(_DANGER_BTN)
        delete_btn.clicked.connect(self._on_delete_clicked)
        action_row.addWidget(delete_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.reload()

    def reload(self) -> None:
        db = get_spare_session()
        try:
            categories = parts_service.list_categories(db)
            by_id = {c.id: c for c in categories}
            self.table.setRowCount(len(categories))
            for row, cat in enumerate(categories):
                self.table.setItem(row, 0, QTableWidgetItem(cat.name))
                parent_name = by_id[cat.parent_id].name if cat.parent_id in by_id else ""
                self.table.setItem(row, 1, QTableWidgetItem(parent_name))
                self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, cat.id)
        finally:
            db.close()

    def _selected_category_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_add_clicked(self) -> None:
        dlg = CategoryDialog(parent=self)
        if dlg.exec():
            self.reload()

    def _on_edit_clicked(self) -> None:
        category_id = self._selected_category_id()
        if not category_id:
            QMessageBox.information(self, "No Selection", "Select a category first.")
            return
        dlg = CategoryDialog(category_id=category_id, parent=self)
        if dlg.exec():
            self.reload()

    def _on_delete_clicked(self) -> None:
        category_id = self._selected_category_id()
        if not category_id:
            QMessageBox.information(self, "No Selection", "Select a category first.")
            return
        db = get_spare_session()
        try:
            category = parts_service.get_category(db, category_id)
            if not category:
                return
            confirm = QMessageBox.question(
                self, "Delete Category", f"Delete category '{category.name}'?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            try:
                parts_service.delete_category(db, category_id)
            except SparePartsValidationError as e:
                QMessageBox.warning(self, "Can't Delete", str(e))
                return
        finally:
            db.close()
        self.reload()


class _BrandsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.addStretch(1)
        add_btn = QPushButton("+ Add Brand")
        add_btn.setStyleSheet(_PRIMARY_BTN)
        add_btn.clicked.connect(self._on_add_clicked)
        toolbar.addWidget(add_btn)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 1)
        self.table.setHorizontalHeaderLabels(["Name"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_edit_clicked)
        layout.addWidget(self.table, 1)

        action_row = QHBoxLayout()
        edit_btn = QPushButton("Edit Selected")
        edit_btn.setStyleSheet(_RESET_BTN)
        edit_btn.clicked.connect(self._on_edit_clicked)
        action_row.addWidget(edit_btn)

        delete_btn = QPushButton("Delete Selected")
        delete_btn.setStyleSheet(_DANGER_BTN)
        delete_btn.clicked.connect(self._on_delete_clicked)
        action_row.addWidget(delete_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        self.reload()

    def reload(self) -> None:
        db = get_spare_session()
        try:
            brands = parts_service.list_brands(db)
            self.table.setRowCount(len(brands))
            for row, brand in enumerate(brands):
                self.table.setItem(row, 0, QTableWidgetItem(brand.name))
                self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, brand.id)
        finally:
            db.close()

    def _selected_brand_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_add_clicked(self) -> None:
        dlg = BrandDialog(parent=self)
        if dlg.exec():
            self.reload()

    def _on_edit_clicked(self) -> None:
        brand_id = self._selected_brand_id()
        if not brand_id:
            QMessageBox.information(self, "No Selection", "Select a brand first.")
            return
        dlg = BrandDialog(brand_id=brand_id, parent=self)
        if dlg.exec():
            self.reload()

    def _on_delete_clicked(self) -> None:
        brand_id = self._selected_brand_id()
        if not brand_id:
            QMessageBox.information(self, "No Selection", "Select a brand first.")
            return
        db = get_spare_session()
        try:
            brand = parts_service.get_brand(db, brand_id)
            if not brand:
                return
            confirm = QMessageBox.question(
                self, "Delete Brand", f"Delete brand '{brand.name}'?",
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            try:
                parts_service.delete_brand(db, brand_id)
            except SparePartsValidationError as e:
                QMessageBox.warning(self, "Can't Delete", str(e))
                return
        finally:
            db.close()
        self.reload()


class CategoriesBrandsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QLabel("Categories & Brands")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(header)

        self.tabs = QTabWidget()
        self.categories_tab = _CategoriesTab()
        self.brands_tab = _BrandsTab()
        self.tabs.addTab(self.categories_tab, "Categories")
        self.tabs.addTab(self.brands_tab, "Brands")
        layout.addWidget(self.tabs, 1)

    def reload(self) -> None:
        self.categories_tab.reload()
        self.brands_tab.reload()
