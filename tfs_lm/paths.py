"""Filesystem locations for the app and its output."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from . import defaults

logger = logging.getLogger(__name__)


def base_dir() -> Path:
    """Directory holding the entry script, whether run from source or frozen."""

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def qml_dir() -> Path:
    return base_dir() / "qml_resources"


def assets_dir() -> Path:
    return qml_dir() / "assets"


def make_run_dir(when: datetime | None = None) -> Path:
    """Create and return labelled_images_<datetime>/ under the script root.

    A same-second collision gets a _2, _3, ... suffix rather than writing
    into an existing run's directory.
    """

    stamp = (when or datetime.now()).strftime(defaults.RUN_DIR_TIMESTAMP_FORMAT)
    root = base_dir()
    candidate = root / f"{defaults.RUN_DIR_PREFIX}{stamp}"

    suffix = 2
    while candidate.exists():
        candidate = root / f"{defaults.RUN_DIR_PREFIX}{stamp}_{suffix}"
        suffix += 1

    candidate.mkdir(parents=True)
    logger.info("Created run directory %r", str(candidate))
    return candidate


def output_root_is_writable() -> bool:
    """Probe whether run directories can be created at all."""

    root = base_dir()
    try:
        probe = root / ".tfs_lm_write_probe"
        probe.touch()
        probe.unlink()
        return True
    except OSError:
        logger.warning("Script root %r is not writable", str(root))
        return False
