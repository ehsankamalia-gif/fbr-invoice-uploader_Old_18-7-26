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
# These hold genuine user customization (captured-form settings, prices,
# feature flags), so an update must never silently overwrite them.
SEED_FILES = (
    "capture_config.json",
    "prices.json",
    "feature_flags.json",
)


def _heal_stale_db_name(env_file: Path) -> None:
    """Corrects a known-bad DB_NAME left over from an older build.

    Installs seeded from a build before this database name was fixed ended
    up with DB_NAME=honda_fbr baked into their per-user .env - a leftover
    from when this app was called "Honda FBR Uploader", never a value any
    real install's actual data lives under (that's "fbr_invoice_uploader").
    Since _seed_env_file only writes .env once and never touches it again,
    those installs would otherwise keep silently connecting to a wrong,
    empty database forever. Only this one specific, unambiguously-wrong
    value is corrected in place; any other DB_NAME (including one the user
    deliberately customized) is left untouched.
    """
    try:
        text = env_file.read_text(encoding="utf-8")
    except Exception:
        return
    if "DB_NAME=honda_fbr" not in text:
        return
    healed = text.replace("DB_NAME=honda_fbr", "DB_NAME=fbr_invoice_uploader")
    try:
        env_file.write_text(healed, encoding="utf-8")
        logger.warning(
            "Self-healed a stale DB_NAME=honda_fbr in %s (leftover from an older build) "
            "to DB_NAME=fbr_invoice_uploader.",
            env_file,
        )
    except Exception as exc:
        logger.error("Could not self-heal stale DB_NAME in %s: %s", env_file, exc)


def _seed_env_file(target_dir: Path) -> None:
    """Ensure a .env exists, preferring a bundled one, else the example."""
    env_file = target_dir / ".env"
    if env_file.exists():
        _heal_stale_db_name(env_file)
        return

    for candidate in (".env", ".env.example"):
        source = resource_dir() / candidate
        if source.exists():
            shutil.copyfile(source, env_file)
            logger.info("Seeded .env from bundled %s", candidate)
            return

    env_file.touch()
    logger.warning("No bundled .env or .env.example found; created an empty .env")


def _sync_version_file(target_dir: Path) -> None:
    """Always refreshes the per-user version.json from the bundle.

    Unlike the SEED_FILES (genuine user data that must survive an update
    untouched), version.json's only job is to say which build is actually
    installed - VersionManager.get_current_version() (and the footer/updater
    that read it) both resolve to this per-user copy, not the bundled one.
    Treating it as "seed once, then leave alone" like the other files meant
    it only ever got written on the very first-ever install: every later
    update correctly replaced the bundled copy but left this one frozen at
    whatever version that first install happened to be, so the app kept
    reporting - and the updater kept "detecting" - the original version
    forever, no matter how many times it was actually updated.
    """
    target = target_dir / "version.json"
    source = resource_dir() / "version.json"
    if not source.exists():
        return
    try:
        if target.exists() and target.read_bytes() == source.read_bytes():
            return
        shutil.copyfile(source, target)
        logger.info("Synced version.json from bundle (%s)", source)
    except Exception as exc:
        logger.error("Could not sync version.json: %s", exc)


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
        _sync_version_file(target_dir)
    except Exception as exc:
        logger.error("First-run setup failed: %s", exc)
