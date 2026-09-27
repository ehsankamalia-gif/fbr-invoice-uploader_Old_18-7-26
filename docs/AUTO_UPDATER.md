# Auto-Update System (GitHub Releases)

This document describes the update system implemented in `app/updater/`, and
how it's wired into the live app in `app/qt_ui/main_window.py`.

## 1. Directory Structure
```text
app/
└── updater/
    ├── __init__.py
    ├── version_manager.py      # Semantic versioning: parsing & comparison
    ├── update_checker.py       # Fetches the latest GitHub Release
    ├── downloader.py           # Secure chunked download + SHA-256 verification
    ├── installer_launcher.py   # App hand-off to the downloaded installer
    ├── notification_ui.py      # Detailed update dialog (PyQt6)
    ├── toast_notification.py   # Non-intrusive toast alert (PyQt6)
    └── updater_manager.py      # High-level orchestration
```

## 2. Update Source: GitHub Releases

The updater checks **one central GitHub repo's Releases** - this is a
vendor-level update channel, not a per-company setting. Every installation
of this software, for every company it's deployed to, checks the same repo
for new versions, exactly like any commercial desktop app's updater.

Configured via (`app/core/config.py`):
- `APP_UPDATE_GITHUB_REPO` - `"owner/repo"`, e.g.
  `ehsankamalia-gif/fbr-invoice-uploader_Old_18-7-26`. Defaults to that
  repo; override with the `APP_UPDATE_GITHUB_REPO` environment variable if
  it's ever renamed or moved.
- `APP_UPDATE_GITHUB_TOKEN` - only needed if the repo is ever made
  **private**. A fine-grained Personal Access Token with "Contents: read"
  (or the classic `repo` scope) is enough. Public repos need no token.

If `APP_UPDATE_GITHUB_REPO` is empty, the updater doesn't initialize at all
(no background check, no network calls).

## 3. How a Release Is Read

The updater calls `GET https://api.github.com/repos/<repo>/releases/latest`
and expects:
- `tag_name` - the version, e.g. `v1.2.0` (a leading `v`/`V` is stripped
  automatically; the version parser also tolerates extra trailing segments
  like `1.2.0.beta.1`, taking just the first three numeric parts).
- An **asset** whose filename ends in `.exe` - this is the installer that
  gets downloaded and launched. The first `.exe` asset found is used, so a
  release should only attach one.
- `body` - used as the changelog text shown to the user.
- `published_at` - shown as the release date.

**Checksum verification** (optional but recommended): the downloaded
installer is checked against a SHA-256 hash if one can be found, in this
order:
1. GitHub's own asset `digest` field (present automatically on newer
   uploads - nothing extra to do).
2. A sidecar asset named `<installer-filename>.exe.sha256` containing just
   the hash (optionally followed by the filename, `sha256sum` style).
3. A shared `checksums.txt` asset listing multiple files, one per line.

If no checksum is found anywhere, the download still proceeds (a warning is
logged) rather than being blocked - but publishing one closes a real
security gap, since otherwise nothing verifies the installer wasn't
corrupted or tampered with in transit.

**No releases published yet** is treated as "you're up to date", not an
error - GitHub returns a 404 for `/releases/latest` in exactly this case,
and it's a completely normal state before your first release exists. Any
*other* failure (network error, HTTP error other than that specific 404, a
release missing a usable `.exe` asset) is treated as a real error and
reported distinctly - it is never silently reported as "up to date". This
was the actual bug in the previous (Bitbucket-based) version of this
system: every failure, for any reason, was silently swallowed and reported
as a successful "up to date" check.

## 4. Update Workflow

1. **Startup**: `MainWindow._init_updater()` creates a `UpdaterManager` and
   kicks off a background check (also re-checked every 4 hours via a timer).
2. **Check**: `UpdateChecker` fetches the latest release and compares it to
   the locally-recorded version (`app/core/version_manager.py`'s
   `version.json`).
3. **Notify**: if newer, a toast appears bottom-right; clicking it opens the
   detailed dialog with the changelog.
4. **Download**: clicking "Download and Install Now" streams the `.exe` to
   the system TEMP folder with a progress bar, then verifies its checksum
   if one was published.
5. **Hand-off**: `InstallerLauncher` launches the installer and exits the
   app immediately, so the installer can overwrite the running files.
6. **Install**: the installer (built via `build_exe.py` + Inno Setup - see
   `docs/DISTRIBUTION_GUIDE.md`) takes over from there.

## 5. Publishing a Release (do this to actually ship an update)

1. Build the installer as usual: `python build_exe.py`, then compile
   `installer_setup.iss` in Inno Setup - see `docs/DISTRIBUTION_GUIDE.md`.
2. (Optional but recommended) Generate a checksum file next to the
   installer:
   ```bash
   certutil -hashfile installer_output\EhsanTraderFBR_Setup.exe SHA256 > EhsanTraderFBR_Setup.exe.sha256
   ```
3. Tag and publish a GitHub Release, e.g. via the `gh` CLI:
   ```bash
   gh release create v1.1.0 \
     installer_output/EhsanTraderFBR_Setup.exe \
     EhsanTraderFBR_Setup.exe.sha256 \
     --title "v1.1.0" \
     --notes "Changelog goes here."
   ```
   (or use the GitHub web UI: Releases -> Draft a new release -> attach
   both files.)
4. Every running installation will pick this up on its next check (within
   4 hours, or immediately via Settings -> System Updates -> "Check for
   Updates Now").

## 6. Security & Reliability
- **HTTPS only**, with TLS verification enforced on every request.
- **SHA-256 verification** of the downloaded installer when a checksum is
  published with the release (see section 3).
- **Failed checks are never mistaken for "up to date"** - see section 3.
- **Thread-safe**: all UI updates happen via Qt signals from the background
  check/download threads.
- **Timeout protection**: network requests time out after 15-30 seconds
  rather than hanging indefinitely.
- Still recommended, not yet done: **code-signing** the installer (see
  `docs/DISTRIBUTION_GUIDE.md` section 5) so Windows doesn't show an
  "Unknown Publisher" warning during install.
