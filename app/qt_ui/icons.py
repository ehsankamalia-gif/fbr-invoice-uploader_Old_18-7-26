"""The app's icons, loaded from SVG files that live IN THE REPOSITORY.

Icons used to be drawn at runtime from a font inside the `qtawesome` pip package (in venv/,
which git ignores), so no icon file was ever pushed with the code. They are now real files:

    app/assets/icons/fa5-solid/<name>.svg    the glyph icons (Font Awesome Free 5.15.4)
    app/assets/icons/ui/chevron-*.svg        the dropdown / spin-box arrows

`app/assets` is already bundled into the packaged EXE (build_exe.py DATA_FILES), so the
installed app has them too. They are regenerated with scripts/build_icons.py, only needed
when a new icon name is added to the code.

Order of lookup for `icon("fa5s.trash-alt", "#2c3e50")`:
  1. the bundled SVG file (always present in a clone / the EXE);
  2. only if that file is missing: qtawesome, when it happens to be installed;
  3. otherwise a null QIcon (callers already treat that as "no icon").
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

from app.core.paths import resource_dir

_PREFIX = "fa5s."
_RENDER_SIZE = 96          # rendered large once; Qt scales it down smoothly (crisp on HiDPI too)
_cache: dict[tuple[str, str], QIcon] = {}

try:  # optional last-resort fallback only
    import qtawesome as _qtawesome
except Exception:  # pragma: no cover
    _qtawesome = None


def icon_dir() -> Path:
    return resource_dir() / "app" / "assets" / "icons"


def ui_asset(name: str) -> Path:
    """A static UI image such as chevron-down.svg (used as a QSS image)."""
    return icon_dir() / "ui" / name


def icon_file(name: str) -> Optional[Path]:
    """The bundled SVG for an icon name like 'fa5s.trash-alt', or None."""
    if not name.startswith(_PREFIX):
        return None
    path = icon_dir() / "fa5-solid" / f"{name[len(_PREFIX):]}.svg"
    return path if path.exists() else None


def _render(svg_text: str, colour: str) -> QPixmap:
    from PyQt6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(QByteArray(svg_text.replace("currentColor", colour).encode("utf-8")))
    image = QImage(_RENDER_SIZE, _RENDER_SIZE, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return QPixmap.fromImage(image)


def icon(name: str, color: str = "#000000") -> QIcon:
    """A QIcon for `name` in `color`. Never raises: an unknown icon is a null QIcon."""
    colour = QColor(color).name() if QColor(color).isValid() else "#000000"
    key = (name, colour)
    if key in _cache:
        return _cache[key]
    result = QIcon()
    path = icon_file(name)
    if path is not None:
        try:
            result = QIcon(_render(path.read_text(encoding="utf-8"), colour))
        except Exception:
            result = QIcon()
    if result.isNull() and _qtawesome is not None:
        try:
            result = _qtawesome.icon(name, color=colour)
        except Exception:
            result = QIcon()
    _cache[key] = result
    return result


def referenced_icon_names(source_roots: list[Path]) -> set[str]:
    """Every 'fa5s.<name>' the given source trees refer to (used by the test that keeps the
    committed SVGs in step with the code)."""
    names: set[str] = set()
    for base in source_roots:
        if base.exists():
            for path in base.rglob("*.py"):
                names.update(f"{_PREFIX}{n}" for n in re.findall(r"fa5s\.([a-z0-9-]+)", path.read_text(encoding="utf-8", errors="ignore")))
    return names


class IconBackend:
    """Drop-in for the `qtawesome` module as the rest of the UI code uses it
    (`backend.icon(name, color=...)`), backed by the bundled SVG files."""

    @staticmethod
    def icon(name: str, color: str = "#000000", **_ignored) -> QIcon:
        return icon(name, color)
