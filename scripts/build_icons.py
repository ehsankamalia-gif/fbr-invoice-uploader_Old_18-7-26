"""Export the UI icons to real SVG files inside the repository.

WHY: the icons used to be drawn at runtime from a font that lives in the `qtawesome` pip
package (inside venv/, which git ignores), so no icon file was ever part of the repository.
This script reads each icon's outline from that font ONCE and writes it to
app/assets/icons/fa5-solid/<name>.svg. Those files are committed, so a fresh clone (and the
packaged EXE, which bundles app/assets) shows every icon without needing qtawesome.

Run it only when you ADD an icon name to the code:

    venv\\Scripts\\python.exe scripts\\build_icons.py

It scans the source for "fa5s.<name>" references, so the set of files always matches what the
code uses (a test checks this). It also writes the two dropdown chevrons.

Icons: Font Awesome Free 5.15.4 (https://fontawesome.com) - see app/assets/icons/fa5-solid/LICENSE.txt
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

OUT_DIR = ROOT / "app" / "assets" / "icons" / "fa5-solid"
UI_DIR = ROOT / "app" / "assets" / "icons" / "ui"
SOURCES = [ROOT / "app", ROOT / "spare_parts", ROOT / "whatsplay_pro", ROOT / "credit_portal_integration"]
NAME_RE = re.compile(r"fa5s\.([a-z0-9-]+)")
EM = 512  # Font Awesome 5's em box


def used_icon_names() -> list[str]:
    names: set[str] = set()
    for base in SOURCES:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            names.update(NAME_RE.findall(path.read_text(encoding="utf-8", errors="ignore")))
    return sorted(names)


def path_to_svg_d(path) -> str:
    from PyQt6.QtGui import QPainterPath

    E = QPainterPath.ElementType
    parts: list[str] = []
    n = path.elementCount()
    i = 0
    open_subpath = False
    while i < n:
        el = path.elementAt(i)
        if el.type == E.MoveToElement:
            if open_subpath:
                parts.append("Z")
            parts.append(f"M{el.x:.2f} {el.y:.2f}")
            open_subpath = True
            i += 1
        elif el.type == E.LineToElement:
            parts.append(f"L{el.x:.2f} {el.y:.2f}")
            i += 1
        elif el.type == E.CurveToElement:
            c1, c2 = path.elementAt(i + 1), path.elementAt(i + 2)
            parts.append(f"C{el.x:.2f} {el.y:.2f} {c1.x:.2f} {c1.y:.2f} {c2.x:.2f} {c2.y:.2f}")
            i += 3
        else:  # stray CurveToData - already consumed above
            i += 1
    if open_subpath:
        parts.append("Z")
    return "".join(parts)


def main() -> int:
    from PyQt6.QtGui import QFont, QFontDatabase, QGuiApplication, QRawFont
    import qtawesome

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    fonts = Path(qtawesome.__file__).parent / "fonts"
    ttf = fonts / "fontawesome5-solid-webfont-5.15.4.ttf"
    charmap = json.loads((fonts / "fontawesome5-solid-webfont-charmap-5.15.4.json").read_text())
    font_id = QFontDatabase.addApplicationFont(str(ttf))
    family = QFontDatabase.applicationFontFamilies(font_id)[0]
    font = QFont(family)
    font.setPixelSize(EM)
    raw = QRawFont.fromFont(font)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    UI_DIR.mkdir(parents=True, exist_ok=True)
    names = used_icon_names()
    missing = []
    for name in names:
        code = charmap.get(name)
        if not code:
            missing.append(name)
            continue
        glyphs = raw.glyphIndexesForString(chr(int(code, 16)))
        path = raw.pathForGlyph(glyphs[0])
        box = path.boundingRect()
        if box.isEmpty():
            missing.append(name)
            continue
        # A square box big enough for the glyph (some are wider than the em), centred on it,
        # so every icon scales consistently - the same way the font renders them.
        side = max(EM, box.width(), box.height())
        x = box.center().x() - side / 2
        y = box.center().y() - side / 2
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:.2f} {y:.2f} {side:.2f} {side:.2f}">'
            f'<path fill="currentColor" fill-rule="nonzero" d="{path_to_svg_d(path)}"/></svg>\n'
        )
        (OUT_DIR / f"{name}.svg").write_text(svg, encoding="utf-8")

    # the two dropdown chevrons (stroke icons used as QSS images)
    for chev, d in (("down", "M5 7.5l5 5 5-5"), ("up", "M5 12.5l5-5 5 5")):
        (UI_DIR / f"chevron-{chev}.svg").write_text(
            "<svg xmlns='http://www.w3.org/2000/svg' width='20' height='20' viewBox='0 0 20 20' fill='none' "
            "stroke='#7f8c8d' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>"
            f"<path d='{d}'/></svg>\n", encoding="utf-8")

    print(f"wrote {len(names) - len(missing)} icons to {OUT_DIR.relative_to(ROOT)} + 2 chevrons")
    if missing:
        print("NOT FOUND in the font:", ", ".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
