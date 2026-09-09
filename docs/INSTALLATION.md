# Installing on a New Windows Computer

## What happens automatically

On first start the application:

1. Creates its data folder at `%APPDATA%\EhsanTraderFBR`.
2. Copies the bundled configuration into it (`.env`, `capture_config.json`,
   `prices.json`, `feature_flags.json`, `version.json`).
3. Checks whether a MySQL server (Laragon or XAMPP) is reachable at the
   `DB_SERVER`/`DB_PORT` from `.env` (default `localhost:3306`).
   - **MySQL found** - creates the database (`honda_fbr` by default) if it does
     not exist, then creates all 40 tables and applies every migration.
   - **No MySQL** - uses a local database file at
     `%APPDATA%\EhsanTraderFBR\fbr_invoices.db`, created the same way.
4. Creates `logs`, `backups`, `exports`, and `temp` inside the data folder.

No manual database setup is required in either case.

## Building the installer

Run these on a machine that has the project and its virtual environment:

```bat
venv\Scripts\python.exe -m pip install pyinstaller
venv\Scripts\python.exe build_exe.py
```

Output: `dist\EhsanTraderFBR\`

To bundle this machine's credentials (FBR tokens, portal login, database
settings) so target machines work with no manual configuration:

```bat
venv\Scripts\python.exe build_exe.py --with-credentials
```

Only do this for installers you give to your own trusted computers - the
resulting installer contains those secrets in readable form.

Then compile `installer_setup.iss` with Inno Setup (right-click the file and
choose *Compile*, or use the Inno Setup IDE). The result is:

```
installer_output\EhsanTraderFBR_Setup.exe
```

Copy that single file to any Windows computer and run it.

## On the target computer

1. Run `EhsanTraderFBR_Setup.exe` (accepts the UAC prompt to install into
   Program Files).
2. The installer reports whether it found Laragon/XAMPP and what the
   application will do about the database.
3. Launch from the Start menu or desktop shortcut.

If you install Laragon or XAMPP *later*, the application picks it up on the
next start - but see the note below.

## Where things are stored

| Location | Contents |
|---|---|
| `C:\Program Files\EhsanTraderFBR` | Application program files (read-only) |
| `%APPDATA%\EhsanTraderFBR` | `.env`, capture config, logs, exports, backups, browser profile |
| MySQL database `honda_fbr` | All business data, when MySQL is available |
| `%APPDATA%\EhsanTraderFBR\fbr_invoices.db` | All business data, when it is not |

Uninstalling removes the program files but **keeps** `%APPDATA%\EhsanTraderFBR`,
so configuration and any local database survive a reinstall.

## Switching a machine to MySQL later

Once a computer has successfully used MySQL, it keeps using MySQL. This is
deliberate: if the server is simply stopped, the application shows a connection
error rather than silently opening an empty local database and letting you enter
invoices into the wrong place.

A machine that started on the local file database will move to MySQL the next
time it starts with the server running. Existing local data is **not** migrated
automatically - export or copy it first if it matters.

## Running from source: automatic Python detection

The installer build needs no Python on the target machine. When running from
source instead (`run.bat`, the desktop shortcut, or `setup.bat`), the launchers
locate Python themselves.

A virtual environment records the absolute path of the Python that created it.
If that Python is upgraded or uninstalled, or the project folder is copied to
another computer, launching used to fail with:

> did not find executable at
> `...\Python314\pythonw.exe`: The system cannot find the path specified.

Now the launchers check the environment first and, if it cannot start, search
for Python in this order: the Windows `py` launcher, `PATH`,
`%LOCALAPPDATA%\Programs\Python`, `Program Files`, and `C:\Python*`. The
Microsoft Store placeholder is skipped, and virtual environments are never
mistaken for a base installation.

Having found Python, they either:

- **repair** the environment in place, when the version matches - installed
  packages are kept and startup is immediate; or
- **rebuild** it and reinstall dependencies, when the version differs; or
- **run with the system Python directly**, if it already has the dependencies.

A healthy environment is left untouched, so nothing changes on a working
machine. If no suitable Python exists, the launcher explains what to install
rather than showing the error above.

Relevant files: `scripts/ensure_python.bat`, `scripts/ensure_venv.py`,
`launch_app.bat`.

## Requirements on the target computer

- Windows 10 or later, 64-bit
- About 600 MB free disk space
- Google Chrome - required only for the Honda portal capture/import features
- Laragon or XAMPP - optional; only needed if you want MySQL instead of the
  built-in local database

## Troubleshooting

**"Database connection failed" on startup**
The machine previously used MySQL but the server is not running. Start
Laragon/XAMPP MySQL and reopen the application.

**Capture or import not working**
Confirm Google Chrome is installed. Check
`%APPDATA%\EhsanTraderFBR\capture_debug.log`.

**Need to change database or FBR settings**
Edit `%APPDATA%\EhsanTraderFBR\.env` and restart the application.
