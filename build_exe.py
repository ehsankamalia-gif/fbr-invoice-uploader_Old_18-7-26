"""Builds the distributable Windows application.

Usage:
    python build_exe.py                     # build without embedded credentials
    python build_exe.py --with-credentials  # also bundle the local .env

--with-credentials embeds this machine's .env (FBR tokens, portal password,
database settings) into the installer so target machines work immediately.
Only use it for installers you distribute to your own trusted machines.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# (source, destination inside the bundle). Missing entries are skipped so the
# build never fails because an optional file is absent.
DATA_FILES = [
    ("version.json", "."),
    ("capture_config.json", "."),
    ("prices.json", "."),
    ("feature_flags.json", "."),
    (".env.example", "."),
    ("assets", "assets"),
    ("app/updater", "app/updater"),
    ("app/static", "app/static"),
    ("app/assets", "app/assets"),
]

COLLECT_ALL = [
    "PyQt6",
    "customtkinter",
    "tzdata",
    "fastapi",
    "uvicorn",
    "playwright",
    "jinja2",
]

HIDDEN_IMPORTS = [
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.sip",
    "sqlite3",
    "pymysql",
    "sqlalchemy",
    "sqlalchemy.dialects.mysql",
    "sqlalchemy.dialects.sqlite",
    "tzdata",
    "playwright",
    "playwright.sync_api",
    "app.core.paths",
    "app.core.provision",
    "app.services.credit_book_service",
    "app.services.scraper_service",
    "app.services.form_capture_service",
    "app.qt_ui.credit_book_page",
    "reporting.server",
    "reporting.main",
    "PIL.SpiderImagePlugin",
]


def clean_previous_builds() -> None:
    if sys.platform == "win32":
        try:
            print("Stopping any running EhsanTraderFBR.exe...")
            subprocess.run(
                ["taskkill", "/F", "/IM", "EhsanTraderFBR.exe", "/T"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    for folder in (PROJECT_ROOT / "dist", PROJECT_ROOT / "build"):
        if folder.exists():
            print(f"Cleaning {folder}...")
            try:
                shutil.rmtree(folder)
            except PermissionError:
                print(
                    f"\nERROR: Permission denied cleaning '{folder}'.\n"
                    "Close the application and any Explorer window on that folder, then retry."
                )
                sys.exit(1)


def build(with_credentials: bool) -> None:
    clean_previous_builds()

    entry_point = PROJECT_ROOT / "app" / "qt_main.py"
    icon_file = PROJECT_ROOT / "app_icon.ico"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        # onedir starts faster and is far more reliable than onefile for a
        # build this size (Qt WebEngine + Playwright).
        "--onedir",
        "--windowed",
        "--name",
        "EhsanTraderFBR",
        "--clean",
    ]

    if icon_file.exists():
        cmd.extend(["--icon", str(icon_file)])

    data_entries = list(DATA_FILES)
    if with_credentials:
        if (PROJECT_ROOT / ".env").exists():
            data_entries.append((".env", "."))
            print("Bundling local .env (credentials will ship with the installer).")
        else:
            print("WARNING: --with-credentials given but no .env found; skipping.")

    for source, dest in data_entries:
        source_path = PROJECT_ROOT / source
        if not source_path.exists():
            print(f"Skipping missing data file: {source}")
            continue
        cmd.extend(["--add-data", f"{source_path}{os.pathsep}{dest}"])

    for package in COLLECT_ALL:
        cmd.extend(["--collect-all", package])

    for module in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", module])

    cmd.append(str(entry_point))

    print(f"\nExecuting:\n  {' '.join(cmd)}\n")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"\nBuild failed: {exc}")
        sys.exit(1)

    print("\nBuild successful. Output: dist/EhsanTraderFBR/")
    print("Next: compile installer_setup.iss with Inno Setup to produce the installer.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the Windows application bundle.")
    parser.add_argument(
        "--with-credentials",
        action="store_true",
        help="Bundle this machine's .env so installs work without manual setup.",
    )
    args = parser.parse_args()
    build(args.with_credentials)
