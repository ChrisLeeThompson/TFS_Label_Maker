"""export_report.json — what a run produced, per image.

Exists chiefly because TIFF tag 34665 (the Exif IFD) cannot ride into a
watermarked copy — its four bytes are a file-relative offset. The
ImageUniqueID it pointed at is preserved here instead, alongside enough
per-image detail to audit a run after the fact.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REPORT_NAME = "export_report.json"


def write_report(
    run_dir: Path,
    output_mode_name: str,
    entries: list[dict[str, Any]],
    stopped: bool,
) -> Path | None:
    """Write the run summary. Failures are logged, never raised — a
    report must not turn a successful export into a failed one."""

    payload = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "output_mode": output_mode_name,
        "stopped": stopped,
        "images": entries,
    }
    target = run_dir / REPORT_NAME
    try:
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        logger.exception("Could not write %s", str(target))
        return None
    return target
