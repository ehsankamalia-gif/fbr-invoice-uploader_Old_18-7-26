
from PyQt6.QtCore import (
    Qt, QPoint, QTimer, QEvent, QObject
)
from PyQt6.QtGui import (
    QCursor
)
from PyQt6.QtWidgets import (
    QScrollArea, QTableView, QTableWidget, QTextEdit, QWidget, QAbstractScrollArea
)
import math


class AutoScrollManager(QObject):
    """
    Reusable Auto Scroll Manager class for scrollable widgets
    Features:
    - Activates on middle mouse button
    - Cursor changes to auto-scroll indicator
    - Vertical and horizontal scrolling
    - Speed depends on distance from activation point
    - Smooth scrolling with timer
    """
    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self._is_active = False
        self._activation_point = QPoint()  # Where auto-scroll was activated (in viewport coords)
        self._target_widget = None  # The widget to scroll (could be viewport's parent)
        self._watched_widget = None  # The widget we installed event filter on
        self._scroll_timer = QTimer(self)
        self._scroll_timer.timeout.connect(self._do_auto_scroll)
        self._last_mouse_pos = QPoint()  # Last known mouse position (in viewport coords)
        
    def install_on_widget(self, widget: QWidget):
        """
        Install auto-scroll functionality on a widget
        Works with QScrollArea, QTableView, QTextEdit, QTableWidget, and other scrollable widgets
        """
        # Figure out which widget is the actual scrollable one and which is the viewport
        if isinstance(widget, QAbstractScrollArea):  # This includes QScrollArea, QTableView, QTextEdit, QTableWidget
            self._target_widget = widget
            self._watched_widget = widget.viewport()
        else:
            self._target_widget = widget
            self._watched_widget = widget
            
        self._watched_widget.installEventFilter(self)
        
    def uninstall_from_widget(self):
        """Remove auto-scroll functionality from the widget"""
        if self._watched_widget:
            self._watched_widget.removeEventFilter(self)
            self._watched_widget = None
            self._target_widget = None
            self._stop_auto_scroll()
            
    def eventFilter(self, watched: QWidget, event: QEvent):
        """Handle events for the watched widget"""
        try:
            if event.type() == QEvent.Type.MouseButtonPress:
                # Check for middle mouse button press
                if hasattr(event, 'button') and event.button() == Qt.MouseButton.MiddleButton:
                    self._toggle_auto_scroll(event.pos())
                    return True
                    
            elif event.type() == QEvent.Type.MouseMove and self._is_active:
                # Update mouse position when auto-scroll is active
                self._last_mouse_pos = event.pos()
                
            elif event.type() == QEvent.Type.MouseButtonRelease and self._is_active:
                # Deactivate on middle mouse button release or click
                if hasattr(event, 'button') and event.button() == Qt.MouseButton.MiddleButton:
                    self._stop_auto_scroll()
                    return True
                    
            elif event.type() == QEvent.Type.KeyPress:
                # Deactivate on any key press
                self._stop_auto_scroll()
                
        except Exception as e:
            print(f"AutoScroll error: {e}")
            
        return False  # Let other handlers process the event too
        
    def _toggle_auto_scroll(self, local_pos: QPoint):
        """Toggle auto-scroll mode"""
        if self._is_active:
            self._stop_auto_scroll()
        else:
            self._start_auto_scroll(local_pos)
            
    def _start_auto_scroll(self, activation_pos: QPoint):
        """Activate auto-scroll mode"""
        self._is_active = True
        self._activation_point = activation_pos
        self._last_mouse_pos = activation_pos
        
        # Change cursor to auto-scroll indicator (on the watched widget)
        if self._watched_widget:
            self._watched_widget.setCursor(Qt.CursorShape.SizeAllCursor)
        
        # Start the auto-scroll timer
        self._scroll_timer.start(16)  # ~60fps for smooth scrolling
        
    def _stop_auto_scroll(self):
        """Deactivate auto-scroll mode"""
        if not self._is_active:
            return
            
        self._is_active = False
        self._scroll_timer.stop()
        
        # Restore cursor to normal
        if self._watched_widget:
            self._watched_widget.unsetCursor()
            
    def _do_auto_scroll(self):
        """
        Perform actual auto-scroll
        Scrolls both horizontally and vertically based on mouse distance from activation point
        """
        if not self._is_active or not self._target_widget:
            return
            
        # Calculate distance from activation point
        dx = self._last_mouse_pos.x() - self._activation_point.x()
        dy = self._last_mouse_pos.y() - self._activation_point.y()
        
        # Calculate scroll speed
        scroll_x = self._calculate_scroll_speed(dx)
        scroll_y = self._calculate_scroll_speed(dy)
        
        # Perform scrolling
        self._scroll_widget(scroll_x, scroll_y)
        
    def _calculate_scroll_speed(self, distance: int) -> int:
        """
        Calculate scroll speed based on distance from activation point
        Uses dead zone and non-linear scaling for better feel
        """
        threshold = 15  # Dead zone around activation point
        if abs(distance) < threshold:
            return 0
            
        speed_multiplier = 0.4
        max_speed = 40
        
        speed = int(distance * speed_multiplier)
        
        if speed > max_speed:
            speed = max_speed
        elif speed < -max_speed:
            speed = -max_speed
            
        return speed
        
    def _scroll_widget(self, dx: int, dy: int):
        """Scroll the target widget by given amount"""
        try:
            if isinstance(self._target_widget, QTableView):
                self._scroll_table_view(self._target_widget, dx, dy)
            elif isinstance(self._target_widget, QTableWidget):
                self._scroll_table_widget(self._target_widget, dx, dy)
            elif isinstance(self._target_widget, QTextEdit):
                self._scroll_text_edit(self._target_widget, dx, dy)
            elif isinstance(self._target_widget, QScrollArea):
                self._scroll_scroll_area(self._target_widget, dx, dy)
            elif isinstance(self._target_widget, QAbstractScrollArea):
                self._scroll_abstract_scroll_area(self._target_widget, dx, dy)
            else:
                self._scroll_generic_widget(self._target_widget, dx, dy)
        except Exception as e:
            print(f"Scroll error: {e}")
            
    def _scroll_scroll_area(self, scroll_area: QScrollArea, dx: int, dy: int):
        """Scroll a QScrollArea"""
        h_bar = scroll_area.horizontalScrollBar()
        v_bar = scroll_area.verticalScrollBar()
        
        if h_bar:
            h_bar.setValue(h_bar.value() + dx)
        if v_bar:
            v_bar.setValue(v_bar.value() + dy)
            
    def _scroll_table_view(self, table_view: QTableView, dx: int, dy: int):
        """Scroll a QTableView"""
        h_bar = table_view.horizontalScrollBar()
        v_bar = table_view.verticalScrollBar()
        
        if h_bar:
            h_bar.setValue(h_bar.value() + dx)
        if v_bar:
            v_bar.setValue(v_bar.value() + dy)
            
    def _scroll_table_widget(self, table_widget: QTableWidget, dx: int, dy: int):
        """Scroll a QTableWidget"""
        h_bar = table_widget.horizontalScrollBar()
        v_bar = table_widget.verticalScrollBar()
        
        if h_bar:
            h_bar.setValue(h_bar.value() + dx)
        if v_bar:
            v_bar.setValue(v_bar.value() + dy)
            
    def _scroll_text_edit(self, text_edit: QTextEdit, dx: int, dy: int):
        """Scroll a QTextEdit"""
        h_bar = text_edit.horizontalScrollBar()
        v_bar = text_edit.verticalScrollBar()
        
        if h_bar:
            h_bar.setValue(h_bar.value() + dx)
        if v_bar:
            v_bar.setValue(v_bar.value() + dy)
            
    def _scroll_abstract_scroll_area(self, area: QAbstractScrollArea, dx: int, dy: int):
        """Scroll any QAbstractScrollArea subclass"""
        h_bar = area.horizontalScrollBar()
        v_bar = area.verticalScrollBar()
        
        if h_bar:
            h_bar.setValue(h_bar.value() + dx)
        if v_bar:
            v_bar.setValue(v_bar.value() + dy)
            
    def _scroll_generic_widget(self, widget: QWidget, dx: int, dy: int):
        """Try to scroll any widget with scroll bars"""
        try:
            h_bar = widget.horizontalScrollBar() if hasattr(widget, 'horizontalScrollBar') else None
            v_bar = widget.verticalScrollBar() if hasattr(widget, 'verticalScrollBar') else None
            
            if h_bar:
                h_bar.setValue(h_bar.value() + dx)
            if v_bar:
                v_bar.setValue(v_bar.value() + dy)
        except Exception as e:
            print(f"Generic scroll error: {e}")
