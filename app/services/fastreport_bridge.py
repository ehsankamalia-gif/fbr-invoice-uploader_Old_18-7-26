from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.core.logger import logger


_FR_CANDIDATE_DIR_NAMES = [
    "FastReport Desktop",
    "FastReport",
    "Fast Reports\\FastReport Desktop",
    "Fast Reports\\FastReport",
    "FastReport\\Community",
]

_FR_BUILDER_EXE = "FRBuilder.exe"
_FR_DESIGNER_EXE = "FRDesigner.exe"


class FastReportNotInstalledError(RuntimeError):
    """Raised when FastReport Desktop cannot be located on the system."""


@dataclass
class FastReportInfo:
    builder_exe: Path
    designer_exe: Optional[Path]


def _iter_program_dirs() -> Iterable[Path]:
    candidates: List[str] = []
    for key in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA"):
        value = os.environ.get(key)
        if value:
            candidates.append(value)
    candidates.append(os.path.expandvars(r"%PROGRAMFILES%"))
    candidates.append(os.path.expandvars(r"%PROGRAMFILES(X86)%"))
    candidates.append(os.path.expandvars(r"%LOCALAPPDATA%"))
    candidates.append(r"C:\Program Files")
    candidates.append(r"C:\Program Files (x86)")
    candidates.append(os.path.expandvars(r"%USERPROFILE%") + "\\AppData\\Local")
    seen = set()
    for raw in candidates:
        if not raw:
            continue
        p = Path(raw)
        key = str(p.resolve()) if p.exists() else str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        yield p


def _search_fr_in_paths() -> Optional[Path]:
    """Search common install locations for FRBuilder.exe."""
    for program_dir in _iter_program_dirs():
        for sub in _FR_CANDIDATE_DIR_NAMES:
            base = program_dir / sub
            for candidate in (
                base / _FR_BUILDER_EXE,
                base / "Builder" / _FR_BUILDER_EXE,
                base / "Bin" / _FR_BUILDER_EXE,
                base / "Tools" / _FR_BUILDER_EXE,
            ):
                if candidate.is_file():
                    return candidate
    path_exe = shutil.which(_FR_BUILDER_EXE)
    if path_exe:
        return Path(path_exe)
    return None


def _custom_fr_path_from_env() -> Optional[Path]:
    raw = (os.getenv("FASTREPORT_DESKTOP_DIR") or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if p.is_dir():
        candidate = p / _FR_BUILDER_EXE
        if candidate.is_file():
            return candidate
    if p.is_file() and p.name.lower() == _FR_BUILDER_EXE.lower():
        return p
    return None


_info_lock = threading.Lock()
_cached_info: Optional[FastReportInfo] = None


def find_fastreports(force_refresh: bool = False) -> Optional[FastReportInfo]:
    """Locate the FastReport Desktop installation (FRBuilder.exe).

    Returns None when FastReport Desktop is not available. Callers should
    fall back to Python-native reporting (reportlab/openpyxl/HTML print) in
    that case — FBR upload and other non-reporting features are unaffected.
    """
    global _cached_info
    if not force_refresh and _cached_info is not None:
        return _cached_info
    with _info_lock:
        if not force_refresh and _cached_info is not None:
            return _cached_info
        builder = _custom_fr_path_from_env() or _search_fr_in_paths()
        if builder is None:
            _cached_info = None
            return None
        designer: Optional[Path] = None
        for sibling in (
            builder.parent / _FR_DESIGNER_EXE,
            builder.parent.parent / _FR_DESIGNER_EXE,
            builder.parent.parent / "Designer" / _FR_DESIGNER_EXE,
        ):
            if sibling.is_file():
                designer = sibling
                break
        info = FastReportInfo(builder_exe=builder, designer_exe=designer)
        _cached_info = info
        return info


def is_fastreports_available() -> bool:
    return find_fastreports() is not None


def ensure_templates_dir() -> Path:
    """Return (and create) the directory used to store .frx templates."""
    root = Path(os.getcwd()) if Path.cwd().is_absolute() else Path(__file__).resolve().parent.parent.parent
    target = root / "exports" / "templates_frx"
    target.mkdir(parents=True, exist_ok=True)
    return target


def default_template_path(template_name: str) -> Path:
    name = (template_name or "").strip().lower()
    if not name.endswith(".frx"):
        name = f"{name}.frx"
    return ensure_templates_dir() / name


def _hidden_popen_kwargs() -> Dict[str, Any]:
    if os.name != "nt":
        return {}
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    creation_flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {"creationflags": creation_flags, "startupinfo": startupinfo}


def _to_json_compatible(data: Any) -> Any:
    if isinstance(data, (str, int, float, bool)) or data is None:
        return data
    if isinstance(data, dict):
        return {str(k): _to_json_compatible(v) for k, v in data.items()}
    if hasattr(data, "_asdict"):
        return _to_json_compatible(data._asdict())
    if isinstance(data, (list, tuple, set)):
        return [_to_json_compatible(v) for v in data]
    try:
        iso = getattr(data, "isoformat", None)
        if callable(iso):
            return iso()
    except Exception:
        pass
    return str(data)


def prepare_report_dataset(
    data: Dict[str, Any],
    dataset_name: str = "Data",
) -> Dict[str, Any]:
    """Normalize arbitrary report data into the shape expected by our
    stock FastReport templates (one root object with nested tables).

    This is deliberately generic: every value in ``data`` becomes a JSON
    table/field accessible inside the .frx template via expressions such
    as ``[Data.Invoices.item.TotalAmount]``.
    """
    payload: Dict[str, Any] = {}
    for k, v in (data or {}).items():
        payload[k] = _to_json_compatible(v)
    return {dataset_name: payload}


@dataclass
class BuildResult:
    ok: bool
    output_path: Optional[Path]
    error: Optional[str]
    args_used: List[str]


def _build_args(
    builder_exe: Path,
    template_path: Path,
    output_path: Path,
    data_json_path: Path,
    export_format: str,
) -> List[str]:
    """Build the FRBuilder.exe argument list.

    FastReport Builder command line is of the general form:
      FRBuilder.exe <template> /EXPORT:<format> /OUTPUT:<out> /DATASOURCE:<file> /DATASOURCENAME:<name>
    We also pass /NOSPLASH /SILENT when supported.
    """
    fmt = (export_format or "pdf").upper()
    args = [
        str(builder_exe),
        str(template_path),
        f"/EXPORT:{fmt}",
        f"/OUTPUT:{output_path}",
        f"/DATASOURCE:{data_json_path}",
        "/DATASOURCETYPE:JSON",
        "/SILENT",
        "/NOSPLASH",
    ]
    return args


def build_report(
    template_name_or_path: str | Path,
    data: Dict[str, Any],
    export_format: str = "pdf",
    output_file: Optional[str | Path] = None,
    dataset_name: str = "Data",
    timeout_seconds: int = 120,
) -> BuildResult:
    """Render an .frx template to PDF (or another FastReport export format).

    When FastReport Desktop is not installed this returns a failed
    BuildResult with a helpful error so callers can fall back to their
    Python-native renderer instead.
    """
    info = find_fastreports()
    if info is None:
        return BuildResult(
            ok=False,
            output_path=None,
            error=(
                "FastReport Desktop is not installed. Set FASTREPORT_DESKTOP_DIR "
                "if FRBuilder.exe is installed in a non-default location. "
                "Falling back to legacy Python renderer."
            ),
            args_used=[],
        )

    if isinstance(template_name_or_path, Path) and template_name_or_path.is_file():
        template_path = template_name_or_path
    else:
        template_path = default_template_path(str(template_name_or_path))

    if not template_path.is_file():
        return BuildResult(
            ok=False,
            output_path=None,
            error=f"FastReport template not found: {template_path}",
            args_used=[],
        )

    dataset = prepare_report_dataset(data, dataset_name=dataset_name)
    tmpdir = Path(tempfile.mkdtemp(prefix="frb_"))
    data_json_path = tmpdir / "dataset.json"
    data_json_path.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    export_format = (export_format or "pdf").lower()
    if export_format == "htm":
        export_format = "html"
    suffix_map = {"pdf": ".pdf", "html": ".html", "xlsx": ".xlsx", "excel": ".xlsx", "csv": ".csv", "docx": ".docx", "rtf": ".rtf", "pptx": ".pptx", "image": ".png", "png": ".png", "jpg": ".jpg"}
    suffix = suffix_map.get(export_format, f".{export_format}")

    if output_file is None:
        out_path = tmpdir / f"{template_path.stem}_output{suffix}"
    else:
        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)

    args = _build_args(
        info.builder_exe,
        template_path,
        out_path,
        data_json_path,
        export_format,
    )

    try:
        proc = subprocess.run(
            args,
            cwd=str(tmpdir),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            **_hidden_popen_kwargs(),
        )
    except FileNotFoundError as exc:
        return BuildResult(ok=False, output_path=None, error=f"FRBuilder.exe not found: {exc}", args_used=args)
    except subprocess.TimeoutExpired as exc:
        return BuildResult(ok=False, output_path=None, error=f"FastReport Builder timed out after {timeout_seconds}s", args_used=args)
    except Exception as exc:
        return BuildResult(ok=False, output_path=None, error=f"FastReport build failed: {exc}", args_used=args)

    if proc.returncode != 0:
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        message = (combined.strip()[:4000]) or f"FRBuilder.exe returned code {proc.returncode}"
        return BuildResult(ok=False, output_path=None, error=message.strip(), args_used=args)

    if not out_path.is_file():
        return BuildResult(
            ok=False,
            output_path=None,
            error=f"FRBuilder did not create the expected output file at {out_path}",
            args_used=args,
        )

    logger.info(
        "FastReport render OK | template=%s | format=%s | size=%s bytes",
        template_path.name,
        export_format,
        out_path.stat().st_size,
    )
    return BuildResult(ok=True, output_path=out_path, error=None, args_used=args)


def open_designer(template_name_or_path: Optional[str | Path] = None) -> Tuple[bool, str]:
    """Open the FastReport Designer for the given template (optional)."""
    info = find_fastreports()
    if info is None:
        return False, "FastReport Desktop is not installed."
    if info.designer_exe is None:
        return False, "FRDesigner.exe not found near FRBuilder.exe."
    args: List[str] = [str(info.designer_exe)]
    if template_name_or_path is not None:
        if isinstance(template_name_or_path, Path) and template_name_or_path.is_file():
            template_path = template_name_or_path
        else:
            template_path = default_template_path(str(template_name_or_path))
        args.append(str(template_path))
    try:
        subprocess.Popen(args, **_hidden_popen_kwargs())
        return True, ""
    except Exception as exc:
        return False, f"Could not launch FRDesigner.exe: {exc}"
