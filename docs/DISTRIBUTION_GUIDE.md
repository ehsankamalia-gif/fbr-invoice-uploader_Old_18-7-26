# Ehsan Trader FBR System - Professional Software Distribution Package

This package contains everything needed to transform the FBR Invoice Uploader into a professional, customer-ready Windows installation.

## 1. Distribution Package Components
- **[build_exe.py](file:///c:/laragon/www/Python/fbr-invoice-uploader/build_exe.py)**: A Python script that uses PyInstaller to generate a single-file executable (`dist/EhsanTraderFBR.exe`).
- **[installer_setup.iss](file:///c:/laragon/www/Python/fbr-invoice-uploader/installer_setup.iss)**: An Inno Setup script that generates a professional Windows installer (`installer_output/EhsanTraderFBR_Setup.exe`).
- **[LICENSE.txt](file:///c:/laragon/www/Python/fbr-invoice-uploader/LICENSE.txt)**: A formal software license agreement for the user to accept during installation.

## 2. Key Installer Features
- **Professional Branding**: Custom icon (`app_icon.ico`) and installer theme support.
- **System Validation**: Pre-installation checks for disk space and runtime dependencies.
- **Customized UI**: Modern wizard-style interface with license agreement acceptance.
- **Silent & Interactive Modes**: Support for `/SILENT` and `/VERYSILENT` command-line flags for enterprise deployment.
- **Desktop & Start Menu**: Automatic creation of shortcuts and Start Menu entries.
- **Secure Uninstallation**: Clean removal of all files, shortcuts, and registry entries.
- **Platform Support**: Optimized for Windows 10/11 with 64-bit architecture support.

## 3. Deployment Workflow

### Step A: Build the Application Executable
1. Open your terminal in the project root.
2. Ensure `pyinstaller` is installed: `pip install pyinstaller`.
3. Run the build script: `python build_exe.py`.
4. The standalone `.exe` will be created in the `dist/` folder.

### Step B: Generate the Windows Installer
1. Install [Inno Setup 6+](https://jrsoftware.org/isdl.php) if you haven't already.
2. Open `installer_setup.iss` in Inno Setup Compiler.
3. Click **Compile** (Ctrl+F9).
4. The professional setup file will be created in `installer_output/EhsanTraderFBR_Setup.exe`.

### Step C: Distribution Options
- **Network-Based**: Upload `EhsanTraderFBR_Setup.exe` to your Bitbucket server or any web hosting.
- **Offline**: Distribute the setup file via USB or any other physical storage.

## 4. System Requirements
- **OS**: Windows 10 or Windows 11 (64-bit).
- **RAM**: Minimum 4GB (8GB recommended).
- **Disk Space**: 200MB available space.
- **Connectivity**: Internet connection required for FBR API and automatic updates.
- **Permissions**: Administrator rights required for installation.

## 5. Security & Verification
To ensure maximum security and prevent "Unknown Publisher" warnings:
1. **Code Signing**: Purchase a code-signing certificate (e.g., Sectigo, DigiCert).
2. **Digital Signature**: Sign both the `EhsanTraderFBR.exe` and the `EhsanTraderFBR_Setup.exe` using `signtool.exe`.
   ```bash
   signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a dist/EhsanTraderFBR.exe
   ```

Copyright (c) 2026 Ehsan Trader. All rights reserved.
