"""Module-specific logger, independent of the main app's logging setup.

Writes to its own file under the app's writable data directory. Uses
app.core.paths.data_path only - a generic filesystem-location helper, not
a table/model - so this does not violate the module's independence rules
(see spare_parts/__init__.py). Resolving the writable directory this way
(instead of a path relative to this file) also means the log still ends
up somewhere writable in a packaged/frozen build, where the install
directory itself is typically read-only.
"""
from __future__ import annotations

import logging

from app.core.paths import data_path

_configured_loggers: set[str] = set()


def get_logger(name: str = "spare_parts") -> logging.Logger:
    logger = logging.getLogger(name)
    if name in _configured_loggers:
        return logger

    logger.setLevel(logging.DEBUG)
    log_file = data_path("spare_parts", "logs", "spare_parts.log")
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False
    _configured_loggers.add(name)
    return logger
