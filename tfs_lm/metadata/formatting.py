"""Turn raw metadata values into label-ready display strings.

Nothing in the reference codebases does this — their trees render values
with str(), so they show 1.25e-11 and 2.1975000000000002e-05. Labels that
go on a published figure need "12.5 pA" and "21.98 µm", so this module is
written from scratch.

Values are never altered, only presented: 3000 volts formats as "3.00 kV"
and stays 3000 underneath.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Micro sign U+00B5, the one Windows fonts and TFS filenames use. The
# Greek mu U+03BC looks identical and appears in some TFS payloads; it is
# accepted on input (see MICRO_SIGNS) but never emitted.
MICRO = "µ"
MICRO_SIGNS = ("µ", "μ", "u")

# Ordered small-to-large so the index arithmetic below is a lookup.
_PREFIXES = ("f", "p", "n", MICRO, "m", "", "k", "M", "G", "T")
_PREFIX_MIN_EXP = -15  # exponent of _PREFIXES[0]
_PREFIX_MAX_EXP = 12   # exponent of _PREFIXES[-1]

# Units that take SI prefixes. Anything else is printed as-is.
SI_UNITS = frozenset({"V", "A", "m", "s", "Pa", "Hz", "W", "F", "C/s"})

EMPTY_DISPLAY = "—"

_DATETIME_PATTERNS = (
    # Acquisition/AcquisitionDatetime — ISO 8601.
    ("%Y-%m-%dT%H:%M:%S", "iso"),
    ("%Y-%m-%d %H:%M:%S", "iso"),
    # PrivateFei/TimeOfCreation — European day-first, dot separated.
    ("%d.%m.%Y %H:%M:%S", "eu"),
    # User/Date + User/Time — US month-first.
    ("%m/%d/%Y %I:%M:%S %p", "us"),
    ("%m/%d/%Y %H:%M:%S", "us"),
    ("%m/%d/%Y", "us"),
    ("%d.%m.%Y", "eu"),
    ("%Y-%m-%d", "iso"),
)

DISPLAY_DATETIME = "%Y-%m-%d %H:%M:%S"
DISPLAY_DATE = "%Y-%m-%d"


def is_empty(value: Any) -> bool:
    """tifffile returns '' for INI keys with no value after the '='."""

    return value is None or (isinstance(value, str) and not value.strip())


def _trim(text: str) -> str:
    """Drop trailing zeros, but only past a decimal point.

    Guards the trap that makes this worth a function: "200".rstrip("0")
    is "2", which would silently turn 200 pA into 2 pA.
    """

    if "." not in text:
        return text
    return text.rstrip("0").rstrip(".")


def _round_significant(value: float, sig_figs: int) -> str:
    """Format to a number of significant figures, then trim.

    Total over all floats: real metadata contains NaN (measured — one
    of the sample TIFFs carries one in its INI), and log10 of it raises.
    """

    if not math.isfinite(value):
        return str(value)
    if value == 0:
        return "0"
    magnitude = math.floor(math.log10(abs(value)))
    decimals = max(0, sig_figs - 1 - magnitude)
    return _trim(f"{value:.{decimals}f}")


def format_si(
    value: float,
    unit: str = "",
    decimals: int | None = None,
    sig_figs: int = 3,
) -> str:
    """Format a number with an SI prefix chosen from its magnitude.

    2.5e-11 A -> "25 pA";  1200 V -> "1.2 kV";  1.93e-05 m -> "19.3 µm".

    `decimals` pins the digits after the point when a field wants a fixed
    presentation (1.20 kV rather than 1.2 kV); otherwise `sig_figs`
    significant figures are shown and trailing zeros trimmed.
    """

    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    if not math.isfinite(number):
        return str(value)

    if number == 0:
        head = f"{0:.{decimals}f}" if decimals is not None else "0"
        return f"{head} {unit}".strip()

    if unit not in SI_UNITS:
        # No prefix to apply — present the number sensibly and stop.
        head = (
            f"{number:.{decimals}f}"
            if decimals is not None
            else _round_significant(number, sig_figs)
        )
        return f"{head} {unit}".strip()

    exponent = math.floor(math.log10(abs(number)))
    group = int(math.floor(exponent / 3.0) * 3)
    group = max(_PREFIX_MIN_EXP, min(_PREFIX_MAX_EXP, group))

    scaled = number / (10.0**group)
    prefix = _PREFIXES[(group - _PREFIX_MIN_EXP) // 3]

    head = (
        f"{scaled:.{decimals}f}"
        if decimals is not None
        else _round_significant(scaled, sig_figs)
    )
    return f"{head} {prefix}{unit}".strip()


def format_radians(value: Any, decimals: int = 2) -> str:
    """Radians as degrees — the form a microscopist reads off the stage."""

    try:
        radians = float(value)
    except (TypeError, ValueError):
        return str(value)
    degrees = math.degrees(radians)
    # A tiny negative angle would otherwise print as "-0.00°".
    if abs(degrees) < 0.5 * 10**-decimals:
        degrees = 0.0
    return f"{degrees:.{decimals}f}°"


def format_temperature_k(value: Any, decimals: int = 1) -> str:
    """Kelvin with the Celsius equivalent, for cryo stage readings."""

    try:
        kelvin = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{kelvin:.{decimals}f} K ({kelvin - 273.15:.{decimals}f} °C)"


def parse_datetime(value: Any) -> datetime | None:
    """Parse any of the timestamp shapes TFS writes.

    The same instant appears in one file as "07/10/2026" (US, month
    first), "10.07.2026 07:56:18" (European, day first) and
    "2026-07-10T07:56:18" (ISO). Order matters: ISO and European are tried
    before US so an unambiguous format is never read with the wrong one.
    """

    if is_empty(value):
        return None
    text = str(value).strip()
    for pattern, _dialect in _DATETIME_PATTERNS:
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def format_datetime(value: Any) -> str:
    parsed = parse_datetime(value)
    if parsed is None:
        return str(value)
    if parsed.hour or parsed.minute or parsed.second:
        return parsed.strftime(DISPLAY_DATETIME)
    return parsed.strftime(DISPLAY_DATE)


_NUMERIC = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def coerce_number(value: Any) -> float | None:
    """Best-effort numeric read of a metadata value.

    XML leaves arrive as strings, and some arrive as attribute dicts such
    as {'unit': 'm', 'unitPrefixPower': '1', '_text': '5.0E-09'}, so the
    text has to be dug out before it can be parsed.
    """

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("_text", "value"):
            if key in value:
                return coerce_number(value[key])
        return None
    if isinstance(value, str):
        text = value.strip()
        if _NUMERIC.match(text):
            try:
                return float(text)
            except ValueError:
                return None
    return None


def format_value(
    value: Any,
    unit: str = "",
    kind: str = "auto",
    decimals: int | None = None,
) -> str:
    """Format one metadata value for display.

    `kind` selects the presentation: "si", "radians", "kelvin",
    "datetime", "raw", or "auto" to infer from the unit and the value.
    """

    if is_empty(value):
        return EMPTY_DISPLAY

    if kind == "raw":
        return str(value)
    if kind == "datetime":
        return format_datetime(value)
    if kind == "radians":
        return format_radians(value, decimals if decimals is not None else 2)
    if kind == "kelvin":
        return format_temperature_k(value, decimals if decimals is not None else 1)
    if kind == "si":
        number = coerce_number(value)
        if number is None:
            return str(value)
        return format_si(number, unit, decimals)

    # auto
    number = coerce_number(value)
    if number is None:
        return str(value)
    if unit:
        return format_si(number, unit, decimals)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if float(number).is_integer() and abs(number) < 1e6:
        return str(int(number))
    return _round_significant(number, 3) if decimals is None else f"{number:.{decimals}f}"
