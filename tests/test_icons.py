"""The UI icons must be real files in the repository (so a git push carries them)."""
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("PyQt6.QtSvg")
from PyQt6.QtWidgets import QApplication

from app.qt_ui import icons

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_every_referenced_icon_has_a_committed_svg():
    names = icons.referenced_icon_names([ROOT / "app", ROOT / "spare_parts"])
    assert names, "no icon references found"
    missing = [n for n in sorted(names) if icons.icon_file(n) is None]
    assert not missing, f"run scripts/build_icons.py; missing SVGs for: {missing}"


def test_chevrons_exist():
    assert icons.ui_asset("chevron-down.svg").exists()
    assert icons.ui_asset("chevron-up.svg").exists()


def test_icon_renders_in_requested_colour(qapp):
    pm = icons.icon("fa5s.check", "#ff0000").pixmap(32, 32).toImage()
    reds = sum(
        1 for x in range(pm.width()) for y in range(pm.height())
        if pm.pixelColor(x, y).alpha() > 200 and pm.pixelColor(x, y).red() > 200 and pm.pixelColor(x, y).green() < 60
    )
    assert reds > 20


def test_unknown_icon_is_null_not_error(qapp, monkeypatch):
    monkeypatch.setattr(icons, "_qtawesome", None)
    assert icons.icon("fa5s.no-such-icon-xyz", "#000").isNull()


def test_works_without_qtawesome(qapp, monkeypatch):
    monkeypatch.setattr(icons, "_qtawesome", None)
    icons._cache.clear()
    assert not icons.icon("fa5s.trash-alt", "#2c3e50").isNull()
    assert not icons.IconBackend.icon("fa5s.save", color="#123456").isNull()


def test_theme_arrows_use_repo_files():
    from app.qt_ui import theme
    files = theme._arrow_files()
    assert files, "no arrow files"
    assert any("assets" in str(f).replace("\\", "/") for f in (files if isinstance(files, (list, tuple)) else files.values()))


def test_icon_files_are_not_git_ignored():
    paths = [str(p.relative_to(ROOT)) for p in (ROOT / "app/assets/icons").rglob("*.svg")]
    assert paths
    res = subprocess.run(["git", "check-ignore", *paths], cwd=ROOT, capture_output=True, text=True)
    assert res.stdout.strip() == "", f"git-ignored icons: {res.stdout}"
