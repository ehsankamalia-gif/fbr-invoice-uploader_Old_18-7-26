"""Finds a usable Python for this project and repairs the virtual environment.

A virtual environment records the absolute path of the Python that created it.
If that interpreter is upgraded, uninstalled, or the project is copied to
another computer, every launcher fails with:

    did not find executable at '...\\pythonw.exe': The system cannot find the
    path specified.

This script detects the Python actually installed on the current machine and
repairs the environment, so the application starts without manual setup.

Prints the interpreter the launchers should use, and exits non-zero if none
could be prepared. Kept compatible with older Python 3 releases, because it may
run under whichever interpreter happens to be present.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

MIN_VERSION = (3, 10)


def log(message):
    sys.stderr.write("%s\n" % message)
    sys.stderr.flush()


def project_dir():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parent.parent


def venv_dir(root):
    return root / "venv"


def venv_python(root):
    return venv_dir(root) / "Scripts" / "python.exe"


def interpreter_works(python_path):
    """True if the interpreter actually runs.

    Uses the console executable, never pythonw.exe: a broken venv stub shows a
    blocking message box instead of failing quietly.
    """
    if not python_path or not Path(python_path).exists():
        return False
    try:
        result = subprocess.run(
            [str(python_path), "-c", "import sys; print(sys.version_info[0])"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        return result.returncode == 0
    except Exception:
        return False


def interpreter_version(python_path):
    try:
        result = subprocess.run(
            [str(python_path), "-c",
             "import sys; print('%d.%d' % sys.version_info[:2])"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        if result.returncode == 0:
            parts = result.stdout.decode("utf-8", "ignore").strip().split(".")
            return (int(parts[0]), int(parts[1]))
    except Exception:
        pass
    return None


def is_store_stub(path):
    """The WindowsApps 'python.exe' is a stub that opens the Microsoft Store."""
    return "windowsapps" in str(path).lower()


def is_virtual_env(python_path):
    """True for an interpreter inside a virtual environment.

    A venv is laid out as <env>/Scripts/python.exe with <env>/pyvenv.cfg
    alongside. Such an interpreter must never be used as a base: pointing one
    environment at another just moves the broken reference somewhere else.
    """
    try:
        return (Path(python_path).parent.parent / "pyvenv.cfg").exists()
    except Exception:
        return False


def base_interpreter_of_current_process():
    """The real installation behind the interpreter running this script."""
    try:
        if sys.prefix != getattr(sys, "base_prefix", sys.prefix):
            base = getattr(sys, "_base_executable", None)
            if base and Path(base).exists():
                return Path(base)
            candidate = Path(sys.base_prefix) / "python.exe"
            if candidate.exists():
                return candidate
            return None
    except Exception:
        pass
    return Path(sys.executable)


def candidate_pythons(root):
    """Every plausible interpreter on this machine, best first."""
    candidates = []

    def add(path):
        if not path:
            return
        path = Path(str(path).strip())
        if is_store_stub(path):
            return
        # Only real installations qualify as a base interpreter.
        if is_virtual_env(path):
            return
        try:
            if venv_dir(root) in path.parents:
                return
        except Exception:
            pass
        if path not in candidates:
            candidates.append(path)

    # The installation behind the interpreter running this script.
    add(base_interpreter_of_current_process())

    # The Windows Python launcher knows every registered installation.
    for args in (["py", "-3", "-c"], ["py", "-c"]):
        try:
            result = subprocess.run(
                args + ["import sys; print(sys.executable)"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
            )
            if result.returncode == 0:
                add(result.stdout.decode("utf-8", "ignore").strip())
        except Exception:
            pass

    # Anything on PATH.
    for exe in ("python.exe", "python3.exe"):
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            if not directory:
                continue
            try:
                candidate = Path(directory) / exe
                if candidate.exists():
                    add(candidate)
            except Exception:
                continue

    # Standard installation locations, newest version first.
    roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
        Path(os.environ.get("PROGRAMFILES", "")),
        Path(os.environ.get("PROGRAMFILES(X86)", "")),
        Path("C:/"),
    ]
    for base in roots:
        try:
            if not base or not base.exists():
                continue
            matches = sorted(base.glob("Python3*"), reverse=True)
            for folder in matches:
                add(folder / "python.exe")
        except Exception:
            continue

    return candidates


def find_system_python(root):
    """First working interpreter that meets the minimum version."""
    for candidate in candidate_pythons(root):
        version = interpreter_version(candidate)
        if version and version >= MIN_VERSION:
            log("Found Python %d.%d at %s" % (version[0], version[1], candidate))
            return candidate, version
    return None, None


def repair_pyvenv_cfg(root, system_python, system_version):
    """Point the existing environment at the interpreter found on this machine.

    Only safe when the versions match: installed packages may include compiled
    extensions built for that exact version.
    """
    cfg_path = venv_dir(root) / "pyvenv.cfg"
    if not cfg_path.exists():
        return False

    recorded = None
    try:
        for line in cfg_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.lower().startswith("version"):
                parts = line.split("=", 1)[1].strip().split(".")
                recorded = (int(parts[0]), int(parts[1]))
                break
    except Exception:
        recorded = None

    if recorded and recorded != system_version:
        log("Environment was built for Python %d.%d but this machine has %d.%d."
            % (recorded[0], recorded[1], system_version[0], system_version[1]))
        return False

    home = Path(system_python).parent
    try:
        cfg_path.write_text(
            "home = %s\n"
            "include-system-site-packages = false\n"
            "version = %d.%d\n"
            "executable = %s\n"
            % (home, system_version[0], system_version[1], system_python),
            encoding="utf-8",
        )
        log("Repaired %s" % cfg_path)
        return True
    except Exception as exc:
        log("Could not repair pyvenv.cfg: %s" % exc)
        return False


def recreate_venv(root, system_python):
    log("Rebuilding the virtual environment. This can take a few minutes...")
    try:
        subprocess.check_call([str(system_python), "-m", "venv", "--clear", str(venv_dir(root))])
    except Exception as exc:
        log("Could not create the virtual environment: %s" % exc)
        return False

    new_python = venv_python(root)
    requirements = root / "requirements.txt"
    if requirements.exists():
        log("Installing dependencies...")
        try:
            subprocess.check_call([str(new_python), "-m", "pip", "install", "--upgrade", "pip"])
            subprocess.check_call([str(new_python), "-m", "pip", "install", "-r", str(requirements)])
        except Exception as exc:
            log("Dependency installation failed: %s" % exc)
            return False
    return interpreter_works(new_python)


def has_app_dependencies(python_path):
    """Whether an interpreter can already run the application as-is."""
    try:
        result = subprocess.run(
            [str(python_path), "-c", "import PyQt6, sqlalchemy"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
        )
        return result.returncode == 0
    except Exception:
        return False


def main():
    root = project_dir()
    existing = venv_python(root)

    # 1. A working environment needs no attention.
    if interpreter_works(existing):
        print(existing)
        return 0

    if existing.exists():
        log("The virtual environment cannot start (its Python was moved or removed).")
    else:
        log("No virtual environment found.")

    # 2. Locate Python on this machine.
    system_python, system_version = find_system_python(root)
    if not system_python:
        log("")
        log("ERROR: No suitable Python installation was found on this computer.")
        log("Install Python %d.%d or newer from https://www.python.org/downloads/"
            % (MIN_VERSION[0], MIN_VERSION[1]))
        log("and tick 'Add Python to PATH' during installation.")
        return 1

    # 3. Re-point the existing environment when versions line up; its installed
    #    packages are then reused and startup is immediate.
    if repair_pyvenv_cfg(root, system_python, system_version) and interpreter_works(existing):
        log("Virtual environment repaired.")
        print(existing)
        return 0

    # 4. Otherwise rebuild it.
    if recreate_venv(root, system_python):
        log("Virtual environment rebuilt.")
        print(venv_python(root))
        return 0

    # 5. Last resort: run directly with the system interpreter, if it already
    #    has the dependencies (useful when offline).
    if has_app_dependencies(system_python):
        log("Using the system Python installation directly.")
        print(system_python)
        return 0

    log("")
    log("ERROR: Python was found, but the environment could not be prepared.")
    log("Run setup.bat with an internet connection to install dependencies.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
