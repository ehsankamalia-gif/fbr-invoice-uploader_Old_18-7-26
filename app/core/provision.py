"""First-run provisioning for installed copies of the application.

An installed EXE starts with an empty per-user data folder. This module seeds
that folder from the files bundled with the build, so a fresh machine gets a
working configuration instead of silently running with defaults - notably
capture_config.json, whose absence previously disabled customer data capture.

Runs before anything imports app.core.config, so it must not import it.
"""

import logging
import shutil
from pathlib import Path

from app.core.paths import (
    data_dir,
    ensure_runtime_dirs,
    is_frozen,
    resource_dir,
)

logger = logging.getLogger("provision")

# Files copied into the writable data folder on first run, if missing there.
SEED_FILES = (
    "capture_config.json",
    "prices.json",
    "feature_flags.json",
    "version.json",
)


def _seed_env_file(target_dir: Path) -> None:
    """Ensure a .env exists, preferring a bundled one, else the example."""
    env_file = target_dir / ".env"
    if env_file.exists():
        return

    for candidate in (".env", ".env.example"):
        source = resource_dir() / candidate
        if source.exists():
            shutil.copyfile(source, env_file)
            logger.info("Seeded .env from bundled %s", candidate)
            return

    env_file.touch()
    logger.warning("No bundled .env or .env.example found; created an empty .env")


def _seed_data_files(target_dir: Path) -> None:
    for name in SEED_FILES:
        target = target_dir / name
        if target.exists():
            continue
        source = resource_dir() / name
        if source.exists():
            shutil.copyfile(source, target)
            logger.info("Seeded %s", name)


def ensure_first_run_setup() -> None:
    """Prepare the writable data folder. Safe to call on every start."""
    try:
        target_dir = data_dir()
        ensure_runtime_dirs()

        # Running from source, config already lives in the project root and is
        # managed by the developer; only installed copies need seeding.
        if not is_frozen():
            return

        _seed_env_file(target_dir)
        _seed_data_files(target_dir)
    except Exception as exc:
        logger.error("First-run setup failed: %s", exc)
