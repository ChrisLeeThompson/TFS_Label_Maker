"""INI parsing for the FEI key=value dialect.

Only used for a PNG MetadataAsINI chunk. TIFF tag 34682 never reaches
here: tifffile already parses it, and re-doing that by hand would be
slower and would drift from tifffile's typing.

configparser is deliberately avoided — the FEI dialect has bare
`Key=` lines with no value, which configparser reads as None rather than
the empty string tifffile produces, and it lowercases nothing while
mangling duplicate keys.
"""

from __future__ import annotations

from typing import Any


def coerce(text: str) -> Any:
    """Match tifffile's typing of tag 34682 so both dialects agree.

    tifffile yields int, float or str, and an empty string for a key with
    nothing after the '='.
    """

    stripped = text.strip()
    if not stripped:
        return ""
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        return float(stripped)
    except ValueError:
        pass
    return stripped


def parse_ini(text: str) -> dict[str, dict[str, Any]]:
    """Parse `[Section]` / `Key=Value` text into {section: {key: value}}."""

    sections: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("﻿")
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip()
            current = sections.setdefault(name, {})
            continue
        if current is None:
            # Key before any section header — skip rather than invent one.
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        current[key.strip()] = coerce(value)

    return sections
