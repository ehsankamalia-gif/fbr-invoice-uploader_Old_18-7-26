"""The Dashboard's new building blocks (cards, chart, attention panel, quick actions)."""
import datetime as dt
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication

from app.qt_ui import dashboard_widgets as dw
from app.services import dashboard_insights as di


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.qt_ui.theme import apply_theme

    apply_theme(app)
    return app


def _points(n=7, amounts=None):
    today = dt.date(2026, 11, 27)
    amounts = amounts or [100000 * (i % 4 + 1) for i in range(n)]
    return [di.DayPoint(today - dt.timedelta(days=n - 1 - i), (1 + i % 3) if amounts[i] else 0, float(amounts[i]))
            for i in range(n)]


# ---- pure helpers -----------------------------------------------------------------------------------
def test_format_helpers():
    assert dw.format_money(1234567.4) == "Rs. 1,234,567"
    assert dw.format_short(0) == "0" and dw.format_short(999) == "999"
    assert dw.format_short(1500) == "1.5K" and dw.format_short(250000) == "250K"
    assert dw.format_short(2_000_000) == "2M" and dw.format_short(1_250_000) == "1.2M" or dw.format_short(1_250_000) == "1.3M"


@pytest.mark.parametrize("value,expected", [(0, 1), (-5, 1), (1, 1), (7, 8), (11, 15), (190000, 200000),
                                            (394500, 400000), (999999, 1000000), (1_000_001, 1_500_000)])
def test_nice_ceiling_is_a_round_number_above_the_value(value, expected):
    ceiling = dw.nice_ceiling(value)
    assert ceiling == expected and ceiling >= value


def test_trend_chip_texts_and_colours():
    assert dw.trend_chip(di.Trend("up", 12.5))[0] == "▲ 12%" or dw.trend_chip(di.Trend("up", 12.5))[0] == "▲ 13%"
    assert dw.trend_chip(di.Trend("up", 5.25))[0] == "▲ 5.2%" or dw.trend_chip(di.Trend("up", 5.25))[0] == "▲ 5.3%"
    down = dw.trend_chip(di.Trend("down", -40.0))
    assert down[0] == "▼ 40%" and down[1] == dw.BAD
    assert dw.trend_chip(di.Trend("up", 40.0))[1] == dw.GOOD
    assert "new" in dw.trend_chip(di.Trend("new"))[0]
    assert "no change" in dw.trend_chip(di.Trend("flat", 0.0))[0] and "no change" in dw.trend_chip(None)[0]


# ---- KPI card / glance tile ---------------------------------------------------------------------------
def test_kpi_card_keeps_the_label_api_the_window_uses(qapp):
    card = dw.build_kpi_card("TOTAL INVOICES", "fa5s.file-alt", "#2578b5", clickable=True)
    card.value_label.setText("125")
    card.subtitle_label.setText("All saved invoices")
    assert card.value_label.text() == "125" and card.subtitle_label.text() == "All saved invoices"
    assert ":hover" in card.styleSheet()
    assert ":hover" not in dw.build_kpi_card("X", "fa5s.file-alt", "#2578b5").styleSheet()
    card.deleteLater()


def test_glance_tile_shows_value_and_trend(qapp):
    tile = dw.GlanceTile("SALES TODAY", "fa5s.coins", "#17934d")
    tile.show()
    tile.set_value("Rs. 394,500")
    tile.set_trend(di.Trend("up", 150.0), "vs yesterday")
    assert tile.value_label.text() == "Rs. 394,500"
    assert "150%" in tile.trend_label.text() and tile.compare_label.text() == "vs yesterday"
    assert tile.trend_label.isVisible()
    tile.set_trend(None, "")
    assert not tile.trend_label.isVisible()
    tile.deleteLater()


# ---- chart -------------------------------------------------------------------------------------------------
def test_chart_axis_and_bars_scale_to_the_data(qapp):
    chart = dw.TrendChart()
    chart.resize(700, 260)
    chart.set_points(_points(7, [0, 100000, 250000, 0, 394500, 50000, 120000]))
    assert chart.axis_max() == 400000
    tallest = chart.bar_rect(4)
    shorter = chart.bar_rect(2)
    assert tallest.height() > shorter.height() > chart.bar_rect(1).height() > 0
    assert chart.bar_rect(0).height() == 0                         # a zero day has no bar
    assert chart.bar_rect(5).height() >= 3                         # a tiny day is still visible
    chart.deleteLater()


def test_chart_hover_index_follows_the_mouse_and_tooltip_text(qapp):
    chart = dw.TrendChart()
    chart.resize(700, 260)
    chart.set_points(_points(7))
    for i in range(7):
        rect = chart.bar_rect(i)
        assert chart.index_at(rect.center().x()) == i
    assert chart.index_at(2) == -1 and chart.index_at(10_000) == -1
    text = chart.label_for(6)
    assert "27 Nov 2026" in text and "invoice" in text and "Rs." in text
    chart.deleteLater()


def test_chart_paints_data_empty_and_hovered_states_without_error(qapp):
    chart = dw.TrendChart()
    chart.resize(700, 260)
    chart.show()
    for points in (_points(7), _points(30), [], _points(7, [0] * 7)):
        chart.set_points(points)
        assert not chart.grab().isNull()
    chart.set_points(_points(30))
    chart._hover = 3
    assert not chart.grab().isNull()
    chart.deleteLater()


def test_chart_empty_state_is_reported(qapp):
    chart = dw.TrendChart()
    chart.set_points(_points(7, [0] * 7))
    assert not chart.has_sales()
    chart.set_points(_points(7))
    assert chart.has_sales()
    chart.deleteLater()


def test_chart_mouse_move_does_not_raise(qapp):
    chart = dw.TrendChart()
    chart.resize(700, 260)
    chart.set_points(_points(7))
    chart.show()
    event = QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(chart.bar_rect(2).center()), QPointF(0, 0),
                        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    chart.mouseMoveEvent(event)
    assert chart._hover == 2
    chart.deleteLater()


# ---- trend card ------------------------------------------------------------------------------------------------
def test_trend_card_switch_emits_the_chosen_range_once(qapp):
    card = dw.TrendCard()
    spy = QSignalSpy(card.days_changed)
    assert card.days() == 7 and card.btn_7.isChecked()
    card.btn_30.click()
    card.btn_30.click()                                           # clicking the active one again does nothing
    card.btn_7.click()
    assert [args[0] for args in spy] == [30, 7] and card.days() == 7
    card.deleteLater()


def test_trend_card_summary_totals_the_period(qapp):
    card = dw.TrendCard()
    card.set_series(_points(7, [100000, 0, 0, 0, 0, 0, 94500]))
    assert "Rs. 194,500" in card.summary_label.text() and "last 7 days" in card.summary_label.text()
    assert card.chart.points()[-1].amount == 94500
    card.deleteLater()


# ---- attention panel -----------------------------------------------------------------------------------------------
def _row(i, status="PENDING", message="Network Error"):
    return di.AttentionRow(i, f"RE-{i:04d}", "ALI KHAN", 150000.0, status, message, 2, dt.datetime(2026, 11, 20))


def test_attention_panel_all_clear(qapp):
    panel = dw.AttentionPanel()
    panel.show()
    panel.set_attention(0, 0, [])
    assert panel.row_count() == 0
    assert not panel.failed_badge.isVisible() and not panel.pending_btn.isVisible()
    panel.deleteLater()


def test_attention_panel_lists_rows_badges_and_links(qapp):
    panel = dw.AttentionPanel()
    panel.show()
    panel.set_attention(1, 2, [_row(1, "FAILED"), _row(2), _row(3)])
    assert panel.row_count() == 3
    assert panel.failed_badge.text() == "1 failed" and panel.pending_badge.text() == "2 pending"
    assert panel.failed_btn.isVisible() and panel.pending_btn.isVisible()
    panel.set_attention(0, 2, [_row(2), _row(3)])
    assert not panel.failed_badge.isVisible() and not panel.failed_btn.isVisible() and panel.row_count() == 2
    panel.deleteLater()


def test_attention_panel_retry_button_emits_that_invoice_id(qapp):
    panel = dw.AttentionPanel()
    panel.set_attention(0, 2, [_row(11), _row(22)])
    spy = QSignalSpy(panel.retry_requested)
    rows = [panel.rows_host.itemAt(i).widget() for i in range(panel.rows_host.count())]
    rows[1].retry_button.click()
    rows[0].retry_button.click()
    assert [args[0] for args in spy] == [22, 11]
    panel.deleteLater()


def test_attention_panel_shows_at_most_six_rows_and_a_more_line(qapp):
    panel = dw.AttentionPanel()
    panel.set_attention(0, 9, [_row(i) for i in range(1, 10)])
    assert panel.row_count() == 6
    last = panel.rows_host.itemAt(panel.rows_host.count() - 1).widget()
    assert last.text() == "+ 3 more"
    panel.deleteLater()


def test_attention_link_buttons_emit_their_signals(qapp):
    panel = dw.AttentionPanel()
    panel.show()
    panel.set_attention(1, 1, [_row(1, "FAILED"), _row(2)])
    pending, failed = QSignalSpy(panel.view_pending_requested), QSignalSpy(panel.view_failed_requested)
    panel.pending_btn.click()
    panel.failed_btn.click()
    assert len(pending) == 1 and len(failed) == 1
    panel.deleteLater()


def test_elided_label_cuts_long_text_with_an_ellipsis_and_never_widens(qapp):
    label = dw.ElidedLabel("ALI KHAN  ·  " + "Network Error (Max Retries) - Queued for retry: " * 4)
    label.resize(200, 18)
    assert label.elided_text().endswith("…") and len(label.elided_text()) < len(label.full_text())
    assert label.minimumSizeHint().width() <= 10
    label.show()
    assert not label.grab().isNull()
    label.deleteLater()


def test_attention_panel_with_long_text_paints(qapp):
    panel = dw.AttentionPanel()
    panel.resize(420, 400)
    panel.show()
    panel.set_attention(0, 1, [_row(1, message="x" * 400)])
    assert not panel.grab().isNull()
    panel.deleteLater()


# ---- quick actions ---------------------------------------------------------------------------------------------------
def test_quick_actions_emit_the_page_key(qapp):
    qa = dw.QuickActions()
    qa.show()
    spy = QSignalSpy(qa.triggered)
    assert list(qa.tiles) == ["invoice", "print_document", "credit_ledger", "spare_parts"]
    for key, tile in qa.tiles.items():
        QTest.mouseClick(tile, Qt.MouseButton.LeftButton)
    assert [args[0] for args in spy] == ["invoice", "print_document", "credit_ledger", "spare_parts"]
    qa.deleteLater()


def test_quick_actions_keyboard_and_right_click(qapp):
    qa = dw.QuickActions()
    qa.show()
    spy = QSignalSpy(qa.triggered)
    tile = qa.tiles["invoice"]
    QTest.keyClick(tile, Qt.Key.Key_Return)
    QTest.keyClick(tile, Qt.Key.Key_Space)
    QTest.keyClick(tile, Qt.Key.Key_A)
    QTest.mouseClick(tile, Qt.MouseButton.RightButton)
    assert [args[0] for args in spy] == ["invoice", "invoice"]
    assert tile.cursor().shape() == Qt.CursorShape.PointingHandCursor and tile.focusPolicy() == Qt.FocusPolicy.StrongFocus
    qa.deleteLater()


def test_quick_actions_hide_shortcuts_the_user_may_not_open(qapp):
    qa = dw.QuickActions(allowed=lambda key: key in ("invoice", "print_document"))
    assert list(qa.tiles) == ["invoice", "print_document"]
    qa.deleteLater()
