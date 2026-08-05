from __future__ import annotations

from collections import defaultdict

from PyQt6.QtCore import QEvent, QObject, QPoint, Qt
from PyQt6.QtGui import QAction, QKeySequence, QTextDocument
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QTableView,
    QTextEdit,
    QWidget,
)


def _plain_label_text(label: QLabel) -> str:
    text = label.text() or ""
    if not text:
        return ""

    if label.textFormat() == Qt.TextFormat.PlainText:
        return text

    document = QTextDocument()
    document.setHtml(text)
    plain_text = document.toPlainText().strip()
    return plain_text or text


def copy_text_to_clipboard(text: str) -> bool:
    value = str(text or "")
    if not value:
        return False
    QApplication.clipboard().setText(value)
    return True


def label_selected_or_full_text(label: QLabel) -> str:
    selected = ""
    try:
        selected = label.selectedText()
    except Exception:
        selected = ""
    return selected or _plain_label_text(label)


def select_all_label_text(label: QLabel) -> None:
    text = _plain_label_text(label)
    if not text:
        return
    try:
        label.setSelection(0, len(text))
    except Exception:
        pass


def build_item_view_selection_text(view: QAbstractItemView) -> str:
    selection_model = view.selectionModel()
    model = view.model()
    if selection_model is None or model is None:
        return ""

    indexes = selection_model.selectedIndexes()
    if not indexes:
        current = view.currentIndex()
        indexes = [current] if current.isValid() else []
    if not indexes:
        return ""

    rows: dict[int, dict[int, str]] = defaultdict(dict)
    row_numbers = set()
    col_numbers = set()

    for index in sorted(indexes, key=lambda idx: (idx.row(), idx.column())):
        row_numbers.add(index.row())
        col_numbers.add(index.column())
        rows[index.row()][index.column()] = str(model.data(index, Qt.ItemDataRole.DisplayRole) or "")

    ordered_rows = sorted(row_numbers)
    ordered_cols = sorted(col_numbers)
    lines: list[str] = []
    for row in ordered_rows:
        lines.append("\t".join(rows[row].get(col, "") for col in ordered_cols))
    return "\n".join(lines).strip()


def copy_item_view_selection(view: QAbstractItemView) -> bool:
    return copy_text_to_clipboard(build_item_view_selection_text(view))


def add_item_view_copy_actions(menu: QMenu, view: QAbstractItemView) -> dict[str, QAction]:
    copy_action = menu.addAction("Copy")
    copy_action.setEnabled(bool(build_item_view_selection_text(view)))
    select_all_action = menu.addAction("Select All")
    return {"copy": copy_action, "select_all": select_all_action}


class CopySupportManager(QObject):
    def __init__(self, app: QApplication):
        super().__init__(app)
        self._app = app

    def apply_existing_widgets(self) -> None:
        for widget in self._app.allWidgets():
            self._apply_to_widget(widget)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.ChildAdded, QEvent.Type.Show):
            try:
                self._apply_to_widget(obj)
            except Exception:
                pass

        if isinstance(obj, QLabel):
            if event.type() == QEvent.Type.ContextMenu:
                self._show_label_context_menu(obj, event.globalPos())
                return True
            if event.type() == QEvent.Type.KeyPress:
                return self._handle_label_key_press(obj, event)

        if isinstance(obj, QAbstractItemView):
            if event.type() == QEvent.Type.ContextMenu and obj.contextMenuPolicy() != Qt.ContextMenuPolicy.CustomContextMenu:
                self._show_item_view_context_menu(obj, event.globalPos())
                return True
            if event.type() == QEvent.Type.KeyPress:
                return self._handle_item_view_key_press(obj, event)

        return super().eventFilter(obj, event)

    def _apply_to_widget(self, widget) -> None:
        if not isinstance(widget, QWidget):
            return

        if isinstance(widget, QLabel):
            flags = widget.textInteractionFlags()
            flags |= Qt.TextInteractionFlag.TextSelectableByMouse
            flags |= Qt.TextInteractionFlag.TextSelectableByKeyboard
            widget.setTextInteractionFlags(flags)
            if widget.focusPolicy() == Qt.FocusPolicy.NoFocus:
                widget.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        if isinstance(widget, QLineEdit):
            widget.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

        if isinstance(widget, (QTextEdit, QPlainTextEdit)):
            widget.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

        if isinstance(widget, QTableView) and widget.contextMenuPolicy() == Qt.ContextMenuPolicy.DefaultContextMenu:
            widget.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

    def _handle_label_key_press(self, label: QLabel, event) -> bool:
        if event.matches(QKeySequence.StandardKey.Copy):
            return copy_text_to_clipboard(label_selected_or_full_text(label))
        if event.matches(QKeySequence.StandardKey.SelectAll):
            select_all_label_text(label)
            return True
        return False

    def _handle_item_view_key_press(self, view: QAbstractItemView, event) -> bool:
        if event.matches(QKeySequence.StandardKey.Copy):
            return copy_item_view_selection(view)
        if event.matches(QKeySequence.StandardKey.SelectAll):
            view.selectAll()
            return True
        return False

    def _show_label_context_menu(self, label: QLabel, global_pos: QPoint) -> None:
        menu = QMenu(label)
        selected_text = ""
        try:
            selected_text = label.selectedText()
        except Exception:
            selected_text = ""
        copy_action = menu.addAction("Copy")
        copy_action.setEnabled(bool(selected_text))
        copy_all_action = menu.addAction("Copy All")
        copy_all_action.setEnabled(bool(_plain_label_text(label)))
        select_all_action = menu.addAction("Select All")
        select_all_action.setEnabled(bool(_plain_label_text(label)))

        action = menu.exec(global_pos)
        if action == copy_action:
            copy_text_to_clipboard(selected_text)
        elif action == copy_all_action:
            copy_text_to_clipboard(_plain_label_text(label))
        elif action == select_all_action:
            select_all_label_text(label)

    def _show_item_view_context_menu(self, view: QAbstractItemView, global_pos: QPoint) -> None:
        menu = QMenu(view)
        actions = add_item_view_copy_actions(menu, view)
        action = menu.exec(global_pos)
        if action == actions["copy"]:
            copy_item_view_selection(view)
        elif action == actions["select_all"]:
            view.selectAll()
