import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QLabel, QTableWidget, QTableWidgetItem

from app.qt_ui.copy_support import CopySupportManager, label_selected_or_full_text


class TestCopySupportManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.manager = CopySupportManager(self.app)
        self.app.clipboard().clear()

    def test_rich_text_labels_copy_visible_text(self) -> None:
        label = QLabel("<b>Status:</b> Running")
        self.manager._apply_to_widget(label)

        copied_text = label_selected_or_full_text(label)

        self.assertEqual(copied_text, "Status: Running")
        self.assertTrue(
            label.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
        )

    def test_ctrl_c_copies_label_text(self) -> None:
        label = QLabel("API server stopped successfully.")
        self.manager._apply_to_widget(label)
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_C,
            Qt.KeyboardModifier.ControlModifier,
        )

        handled = self.manager._handle_label_key_press(label, event)

        self.assertTrue(handled)
        self.assertEqual(self.app.clipboard().text(), "API server stopped successfully.")

    def test_ctrl_c_copies_selected_table_cells(self) -> None:
        table = QTableWidget(2, 2)
        self.manager._apply_to_widget(table)
        table.setItem(0, 0, QTableWidgetItem("Log Entry"))
        table.setItem(0, 1, QTableWidgetItem("Created"))
        table.setItem(1, 0, QTableWidgetItem("Response"))
        table.setItem(1, 1, QTableWidgetItem("OK"))
        table.selectRow(0)
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_C,
            Qt.KeyboardModifier.ControlModifier,
        )

        handled = self.manager._handle_item_view_key_press(table, event)

        self.assertTrue(handled)
        self.assertEqual(self.app.clipboard().text(), "Log Entry\tCreated")


if __name__ == "__main__":
    unittest.main()
