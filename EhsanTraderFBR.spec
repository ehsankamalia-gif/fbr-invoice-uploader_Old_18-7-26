# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('G:/LARAGON_INSTALLATION10-8-2025/laragon/www/fbr-invoice-uploader_Old_18-7-26/version.json', '.'), ('G:/LARAGON_INSTALLATION10-8-2025/laragon/www/fbr-invoice-uploader_Old_18-7-26/capture_config.json', '.'), ('G:/LARAGON_INSTALLATION10-8-2025/laragon/www/fbr-invoice-uploader_Old_18-7-26/prices.json', '.'), ('G:/LARAGON_INSTALLATION10-8-2025/laragon/www/fbr-invoice-uploader_Old_18-7-26/feature_flags.json', '.'), ('G:/LARAGON_INSTALLATION10-8-2025/laragon/www/fbr-invoice-uploader_Old_18-7-26/.env.example', '.'), ('G:/LARAGON_INSTALLATION10-8-2025/laragon/www/fbr-invoice-uploader_Old_18-7-26/assets', 'assets'), ('G:/LARAGON_INSTALLATION10-8-2025/laragon/www/fbr-invoice-uploader_Old_18-7-26/app/updater', 'app/updater'), ('G:/LARAGON_INSTALLATION10-8-2025/laragon/www/fbr-invoice-uploader_Old_18-7-26/app/static', 'app/static'), ('G:/LARAGON_INSTALLATION10-8-2025/laragon/www/fbr-invoice-uploader_Old_18-7-26/app/assets', 'app/assets')]
binaries = []
hiddenimports = ['PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'PyQt6.QtWebEngineWidgets', 'PyQt6.sip', 'sqlite3', 'pymysql', 'sqlalchemy', 'sqlalchemy.dialects.mysql', 'sqlalchemy.dialects.sqlite', 'tzdata', 'playwright', 'playwright.sync_api', 'app.core.paths', 'app.core.provision', 'app.services.credit_book_service', 'app.services.scraper_service', 'app.services.form_capture_service', 'app.qt_ui.credit_book_page', 'reporting.server', 'reporting.main', 'PIL.SpiderImagePlugin']
tmp_ret = collect_all('PyQt6')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('tzdata')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('fastapi')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('uvicorn')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('playwright')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('jinja2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['G:/LARAGON_INSTALLATION10-8-2025/laragon/www/fbr-invoice-uploader_Old_18-7-26/app/qt_main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EhsanTraderFBR',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='EhsanTraderFBR',
)
