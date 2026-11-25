"""The professional result / notice dialogs (presentation only)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")
from PyQt6.QtCore import Qt, qInstallMessageHandler
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from app.qt_ui import notice_dialog
from app.qt_ui.notice_dialog import KINDS, NoticeDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    from app.qt_ui.theme import apply_theme

    apply_theme(app)
    return app


@pytest.fixture()
def captured(monkeypatch):
    """Replace exec() so dialogs are recorded instead of blocking."""
    shown = []
    monkeypatch.setattr(NoticeDialog, "exec", lambda self: shown.append(self) or 0)
    return shown


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    ch = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        ch.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


# ---- the dialog itself --------------------------------------------------------------
def test_all_four_kinds_exist_and_have_readable_headers():
    assert set(KINDS) == {"success", "warning", "error", "info"}
    for name, c in KINDS.items():
        for end in ("start", "end"):
            # white title text on the header: at least 3:1 (it is large, bold text)
            assert 1.05 / (_luminance(c[end]) + 0.05) >= 3.0, (name, end)


def test_minimal_dialog_hides_the_optional_parts(qapp):
    d = NoticeDialog(None, "success", "Saved", "All good.")
    d.show()
    qapp.processEvents()
    assert d.title_label.text() == "Saved"
    assert d.message_label.text() == "All good."
    assert not d.details_frame.isVisible()
    assert not d.callout_frame.isVisible()
    assert not d.hint_label.isVisible()
    assert d.copy_button is None
    assert d.ok_button.text() == "OK" and d.ok_button.isDefault()


def test_details_callout_and_hint_appear_when_given(qapp):
    d = NoticeDialog(None, "warning", "T", "m", details=[("Invoice No.", "RE-1"), ("Empty", "")],
                     callout=("Reason", "Because."), hint="Try later.")
    d.show()
    qapp.processEvents()
    assert d.details_frame.isVisible() and list(d.detail_values) == ["Invoice No."]   # blank values are dropped
    assert d.callout_frame.isVisible() and d.callout_text.text() == "Because."
    assert d.hint_label.isVisible() and d.hint_label.text() == "Try later."


def test_html_in_a_message_is_shown_as_text_not_interpreted(qapp):
    d = NoticeDialog(None, "error", "T", "<b>bold</b> & <i>x</i>", details=[("k", "<u>v</u>")],
                     callout=("c", "<script>alert(1)</script>"))
    assert d.message_label.textFormat() == Qt.TextFormat.PlainText
    assert d.message_label.text() == "<b>bold</b> & <i>x</i>"
    assert d.detail_values["k"].textFormat() == Qt.TextFormat.PlainText
    assert d.callout_text.textFormat() == Qt.TextFormat.PlainText


def test_ok_button_closes_the_dialog(qapp):
    d = NoticeDialog(None, "info", "T", "m")
    d.show()
    d.ok_button.click()
    assert d.result() == d.DialogCode.Accepted


def test_copy_button_puts_the_text_on_the_clipboard(qapp):
    d = NoticeDialog(None, "success", "T", "m", copy_button=("Copy FBR ID", "966416FKNU37578229"))
    d.show()
    d.copy_button.click()
    assert QApplication.clipboard().text() == "966416FKNU37578229"
    assert "Copied" in d.copy_button.text()


def test_stylesheet_parses_without_errors_for_every_kind(qapp):
    seen = []
    previous = qInstallMessageHandler(lambda mode, ctx, msg: seen.append(msg))
    try:
        for kind in KINDS:
            d = NoticeDialog(None, kind, "T", "m", details=[("a", "b")], callout=("c", "d"), hint="h",
                             copy_button=("Copy", "x"))
            d.show()
            qapp.processEvents()
    finally:
        qInstallMessageHandler(previous)
    assert [m for m in seen if "parse" in m.lower() and "stylesheet" in m.lower()] == []


def test_dialog_works_without_qtawesome(qapp, monkeypatch):
    monkeypatch.setattr(notice_dialog, "_qta", None)          # falls back to a text glyph in the badge
    d = NoticeDialog(None, "success", "T", "m")
    d.show()
    badge = d.findChild(QLabel, "noticeBadge")
    assert badge.text() == KINDS["success"]["glyph"]


# ---- the invoice result dialog (the one shown right after submit) ----------------------
def test_uploaded_invoice_shows_the_green_dialog_with_the_fbr_id(qapp, captured):
    notice_dialog.show_invoice_result(None, "RE-0050", "966416FKNU37578229", "Success")
    d = captured[0]
    assert d.kind == "success" and d.windowTitle() == "Submission Success"
    assert d.title_label.text() == "Invoice Uploaded to FBR"
    assert "RE-0050" in d.message_label.text()
    assert d.detail_values["FBR Invoice ID"].text() == "966416FKNU37578229"
    assert d.copy_button is not None and d.copy_button.text() == "Copy FBR ID"
    assert d.callout_frame.isHidden() and d.callout_text.text() == ""      # a success has no failure callout


def test_failed_upload_shows_the_amber_saved_locally_dialog_with_fbrs_reason(qapp, captured):
    notice_dialog.show_invoice_result(None, "RE-0051", None, "Invalid data received.Invalid Invoice Type")
    d = captured[0]
    assert d.kind == "warning" and d.windowTitle() == "Local Save Success"     # same window title as before
    assert "Saved Locally" in d.title_label.text()
    assert "RE-0051" in d.message_label.text() and "saved on this computer" in d.message_label.text()
    assert d.detail_values["FBR Status"].text() == "Not uploaded"
    assert d.callout_text.text() == "Invalid data received.Invalid Invoice Type"      # FBR's reason, verbatim
    assert "Reports section" in d.hint_label.text()                                     # same retry advice as before
    assert d.copy_button.text() == "Copy reason"


def test_failed_upload_with_no_reason_still_says_something_useful(qapp, captured):
    notice_dialog.show_invoice_result(None, "RE-0052", None, "   ")
    assert captured[0].callout_text.text() == "No reason was returned by FBR."
    notice_dialog.show_invoice_result(None, "RE-0053", None, None)
    assert captured[1].callout_text.text() == "No reason was returned by FBR."


def test_long_fbr_reason_wraps_instead_of_stretching_the_dialog(qapp, captured):
    long_reason = "Invalid data received. " + "Field X is not valid. " * 30
    notice_dialog.show_invoice_result(None, "RE-0054", None, long_reason)
    d = captured[0]
    d.show()
    qapp.processEvents()
    assert d.callout_text.wordWrap()
    assert d.width() <= d.maximumWidth()


# ---- the app's two generic helpers now use it -------------------------------------------
def test_show_success_and_show_error_use_the_new_dialog(qapp, captured):
    import app.qt_ui.main_window as mw

    parent = QWidget()
    mw.MainWindow._show_success(parent, "Export Complete", "Exported 12 prices.")
    mw.MainWindow._show_error(parent, "Submission Error", "Could not connect.")
    ok, err = captured
    assert (ok.kind, ok.title_label.text(), ok.message_label.text()) == ("success", "Export Complete", "Exported 12 prices.")
    assert (err.kind, err.title_label.text(), err.message_label.text()) == ("error", "Submission Error", "Could not connect.")
