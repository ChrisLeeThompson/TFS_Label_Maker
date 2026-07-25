"""Turn dropped or chosen URLs into a validated list of image paths.

Everything here runs on the GUI thread and must stay cheap: it only looks
at names and stat results, never opens an image. Parsing happens later on
a worker thread.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QUrl

from .. import defaults

logger = logging.getLogger(__name__)

# "C:\..." or "C:/...". Checked before QUrl gets a look in, because QUrl
# parses the drive letter as a scheme — QUrl("C:\\x.tif").scheme() is "c"
# — so a bare Windows path is neither a local file nor scheme-less and
# would otherwise be rejected outright.
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")

# Rejection reasons, kept as constants so the status bar and the tests
# agree on the wording.
REASON_NOT_LOCAL = "not a local file"
REASON_MISSING = "does not exist"
REASON_UNSUPPORTED = "unsupported file type"
REASON_DUPLICATE = "already loaded"
REASON_EMPTY_DIR = "no supported images in folder"


@dataclass(slots=True)
class DiscoveryResult:
    accepted: list[Path] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)

    @property
    def accepted_count(self) -> int:
        return len(self.accepted)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)


def url_to_path(url: str) -> Path | None:
    """Convert a file:// URL string to a local path.

    QUrl.toLocalFile handles percent-encoding (spaces, the micro sign in
    TFS filenames) and UNC shares. Stripping the scheme by hand gets both
    wrong, which is why the QML side passes the URL through untouched.
    """

    text = str(url).strip()
    if not text:
        return None

    # Bare paths first: a drive letter or a UNC share must not reach QUrl.
    if _WINDOWS_DRIVE.match(text) or text.startswith("\\\\"):
        return Path(text)

    qurl = QUrl(text)
    if qurl.isLocalFile():
        local = qurl.toLocalFile()
        return Path(local) if local else None
    # Scheme-less relative path — accept it so the API is forgiving of
    # callers that already converted.
    if not qurl.scheme():
        return Path(text)
    return None


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in defaults.SUPPORTED_EXTENSIONS


def images_in_directory(directory: Path) -> list[Path]:
    """Supported images directly inside a folder, sorted by name.

    Deliberately not recursive: a microscopist dropping a session folder
    means that folder, and silently pulling in every subdirectory of a
    large project tree would be a surprise that is hard to undo.
    """

    try:
        entries = sorted(
            child
            for child in directory.iterdir()
            if child.is_file() and is_supported(child)
        )
    except OSError:
        logger.exception("Could not list directory %r", str(directory))
        return []
    return entries


def resolve_urls(
    urls: list[str], already_loaded: set[Path] | None = None
) -> DiscoveryResult:
    """Validate URLs into loadable image paths.

    Directories are expanded. Duplicates are dropped both against the
    already-loaded set and within this batch, so dragging the same file
    twice cannot load it twice.
    """

    already = already_loaded or set()
    result = DiscoveryResult()
    seen: set[Path] = set()

    for url in urls:
        path = url_to_path(url)
        if path is None:
            result.rejected.append((url, REASON_NOT_LOCAL))
            continue

        if path.is_dir():
            found = images_in_directory(path)
            if not found:
                result.rejected.append((path.name, REASON_EMPTY_DIR))
                continue
            candidates = found
        else:
            candidates = [path]

        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                result.rejected.append((candidate.name, REASON_MISSING))
                continue

            if not resolved.is_file():
                result.rejected.append((candidate.name, REASON_MISSING))
                continue
            if not is_supported(resolved):
                result.rejected.append((candidate.name, REASON_UNSUPPORTED))
                continue
            if resolved in already or resolved in seen:
                result.rejected.append((candidate.name, REASON_DUPLICATE))
                continue

            seen.add(resolved)
            result.accepted.append(resolved)

    logger.info(
        "Discovery: %d accepted, %d rejected from %d URL(s)",
        result.accepted_count,
        result.rejected_count,
        len(urls),
    )
    return result


def summarize(result: DiscoveryResult, total_loaded: int) -> str:
    """One-line status bar summary of a load."""

    if result.accepted_count == 0 and result.rejected_count == 0:
        return "Nothing to load"

    parts: list[str] = []
    if result.accepted_count:
        parts.append(
            f"Loaded {result.accepted_count} "
            f"image{'' if result.accepted_count == 1 else 's'}"
        )
    if result.rejected_count:
        # Name the reason when every rejection shares one; a mixed batch
        # gets the count only, with the detail in the log.
        reasons = {reason for _, reason in result.rejected}
        detail = reasons.pop() if len(reasons) == 1 else "skipped"
        parts.append(f"{result.rejected_count} {detail}")

    summary = ", ".join(parts)
    if total_loaded:
        summary += f" — {total_loaded} total"
    return summary
