"""The canonical field layer.

The problem this solves is measurable: across the four sample images the
intersection of raw metadata paths is *empty*. The PNG carries XML only
(its INI chunk is present but zero-length), Electron_*.tif carries INI
only with no XML tag at all, and the other two carry both. A literal
reading of "metadata common to all dropped images" therefore shows
nothing the moment a batch is mixed.

Two mechanisms fix that, and they are separate on purpose:

1. Section aliasing, so EBeam and IBeam are recognised as the same slot.
   TFS states the mapping outright — Beam/Beam is 'EBeam' or 'IBeam',
   Beam/Scan is 'EScan' or 'IScan', Detectors/Name is the detector
   section's own name — so this is three lookups, not a heuristic. It
   lifts the INI common set from 121 to 177 of 201 paths.

2. A cross-dialect identity map, so INI EBeam/HV and XML
   Optics/AccelerationVoltage are understood to be the same quantity.

Neither ever alters a value. Fields are reported exactly as stored, so an
image with beam deceleration active reports its real HV and exposes
landing energy as its own separate field rather than quietly swapping one
for the other.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from . import formatting

logger = logging.getLogger(__name__)

# Tree group prefixes.
GROUP_MICROSCOPE = "Microscope"
GROUP_XML = "XML"

# What the user-facing surfaces (tree group rows, status messages) call
# the dialect groups: the ASV Project Explorer's names for the same two
# TIFF tags, so this app and the sibling app read the same way.
GROUP_DISPLAY_TITLES = {
    GROUP_MICROSCOPE: "MicroscopeMetadata",
    GROUP_XML: "ASVXMLMetadata",
}

# Canonical section names for the slots whose real name varies by beam or
# detector. Spelled out rather than "Beam*" because a [Beam] section also
# exists and the two must never be confused.
SECTION_ACTIVE_BEAM = "ActiveBeam"
SECTION_ACTIVE_SCAN = "ActiveScan"
SECTION_ACTIVE_DETECTOR = "ActiveDetector"


@dataclass(frozen=True, slots=True)
class CanonicalField:
    """One logical quantity and where to find it in each dialect."""

    key: str
    label: str
    unit: str = ""
    kind: str = "auto"
    decimals: int | None = None
    ini: tuple[str, ...] = ()
    xml: tuple[str, ...] = ()


# No longer rendered as a tree group — the user chose to show only the
# raw dialect categories, so the synthesized "Common" rows are gone.
# The table stays because it is the curated unit/kind knowledge for the
# label renderer (M8): a checked path like Microscope.ActiveBeam.HV
# resolves here to ("V", "si") for SI formatting. Paths are tried in
# turn and the first one present wins, which is what lets a single
# entry serve the electron and ion variants after aliasing.
CANONICAL_FIELDS: tuple[CanonicalField, ...] = (
    CanonicalField(
        "HV", "Accelerating voltage", "V", "si",
        ini=("Beam.HV", f"{SECTION_ACTIVE_BEAM}.HV"),
        xml=("Optics.AccelerationVoltage",),
    ),
    CanonicalField(
        "BeamCurrent", "Beam current", "A", "si",
        ini=(f"{SECTION_ACTIVE_BEAM}.BeamCurrent",),
        xml=("Optics.BeamCurrent",),
    ),
    CanonicalField(
        "WorkingDistance", "Working distance", "m", "si",
        ini=(f"{SECTION_ACTIVE_BEAM}.WD", "Stage.WorkingDistance"),
        xml=("Optics.WorkingDistance",),
        # Focus tracking reads finer than a micrometre: pin five
        # decimals ("4.10352 mm"), not the default 3 significant figures.
        decimals=5,
    ),
    CanonicalField(
        "HorizontalFieldWidth", "Horizontal field width", "m", "si",
        ini=("Scan.HorFieldsize",),
        xml=("Optics.ScanFieldOfView.X",),
    ),
    CanonicalField(
        "VerticalFieldWidth", "Vertical field width", "m", "si",
        ini=("Scan.VerFieldsize",),
        xml=("Optics.ScanFieldOfView.Y",),
    ),
    CanonicalField(
        "PixelWidth", "Pixel size (X)", "m", "si",
        ini=("Scan.PixelWidth",),
        xml=("BinaryResult.PixelSize.X",),
    ),
    CanonicalField(
        "PixelHeight", "Pixel size (Y)", "m", "si",
        ini=("Scan.PixelHeight",),
        xml=("BinaryResult.PixelSize.Y",),
    ),
    CanonicalField(
        "DwellTime", "Dwell time", "s", "si",
        ini=("Scan.Dwelltime", f"{SECTION_ACTIVE_SCAN}.Dwell"),
        xml=("ScanSettings.DwellTime",),
    ),
    CanonicalField(
        "Detector", "Detector", "", "raw",
        ini=("Detectors.Name",),
        xml=("Detectors.ScanningDetector.DetectorName",),
    ),
    CanonicalField(
        "DetectorMode", "Detector mode", "", "raw",
        ini=("Detectors.Mode",),
        xml=("Detectors.ScanningDetector.Signal",),
    ),
    CanonicalField(
        "BeamType", "Beam", "", "raw",
        ini=("Beam.Beam",),
        xml=("Acquisition.BeamType",),
    ),
    CanonicalField(
        "Magnification", "Magnification", "", "auto",
        ini=(f"{SECTION_ACTIVE_SCAN}.Magnification",),
        xml=("Optics.Magnification",),
    ),
    CanonicalField(
        "SpotSize", "Spot size", "", "auto",
        ini=("Beam.Spot",),
        xml=("Optics.SpotSize",),
    ),
    CanonicalField(
        "StageX", "Stage X", "m", "si",
        ini=("Stage.StageX",), xml=("StageSettings.StagePosition.X",),
    ),
    CanonicalField(
        "StageY", "Stage Y", "m", "si",
        ini=("Stage.StageY",), xml=("StageSettings.StagePosition.Y",),
    ),
    CanonicalField(
        "StageZ", "Stage Z", "m", "si",
        ini=("Stage.StageZ",), xml=("StageSettings.StagePosition.Z",),
    ),
    CanonicalField(
        "StageTilt", "Stage tilt", "", "radians",
        ini=("Stage.StageT",),
        xml=("StageSettings.StagePosition.Alpha",),
    ),
    CanonicalField(
        "StageRotation", "Stage rotation", "", "radians",
        ini=("Stage.StageR",),
        xml=("StageSettings.StagePosition.Rotation",),
    ),
    CanonicalField(
        "ResolutionX", "Resolution (X)", "", "auto",
        ini=("Image.ResolutionX",), xml=("BinaryResult.ImageSize.X",),
    ),
    CanonicalField(
        "ResolutionY", "Resolution (Y)", "", "auto",
        ini=("Image.ResolutionY",), xml=("BinaryResult.ImageSize.Y",),
    ),
    CanonicalField(
        "ChamberPressure", "Chamber pressure", "Pa", "si",
        ini=("Vacuum.ChPressure",), xml=("VacuumProperties.SamplePressure",),
    ),
    CanonicalField(
        "Acquired", "Acquired", "", "datetime",
        ini=("PrivateFei.TimeOfCreation",),
        xml=("Acquisition.AcquisitionDatetime",),
    ),
    CanonicalField(
        "User", "User", "", "raw",
        ini=("User.User",), xml=("Core.UserID",),
    ),
    CanonicalField(
        "System", "System", "", "raw",
        ini=("System.SystemType",), xml=("Instrument.InstrumentClass",),
    ),
    CanonicalField(
        "Software", "Software", "", "raw",
        ini=("System.Software",),
        xml=("Instrument.ControlSoftwareVersion",),
    ),
    # Deceleration is reported as it is stored, never folded into HV. On
    # an image with ModeOn 'On' the two genuinely disagree — HV 3000 with
    # a landing energy of 1000 — and which one belongs on the figure is
    # the operator's call, not the app's.
    CanonicalField(
        "DecelerationMode", "Beam deceleration", "", "raw",
        ini=("EBeamDeceleration.ModeOn",),
    ),
    CanonicalField(
        "LandingEnergy", "Landing energy", "V", "si",
        ini=("EBeamDeceleration.LandingEnergy",),
    ),
    CanonicalField(
        "StageBias", "Stage bias", "V", "si",
        ini=("EBeamDeceleration.StageBias",),
    ),
)

FIELDS_BY_KEY: dict[str, CanonicalField] = {f.key: f for f in CANONICAL_FIELDS}

# Raw dotted path -> the field whose unit/kind formats it. This is how
# the label renderer knows Microscope.ActiveBeam.HV is volts with an SI
# prefix while the tree's checked paths stay raw. setdefault so the
# FIRST field claiming a path wins, mirroring the candidate order above.
_FIELD_BY_PATH: dict[str, CanonicalField] = {}
for _field in CANONICAL_FIELDS:
    for _candidate in _field.ini:
        _FIELD_BY_PATH.setdefault(f"{GROUP_MICROSCOPE}.{_candidate}", _field)
    for _candidate in _field.xml:
        _FIELD_BY_PATH.setdefault(f"{GROUP_XML}.{_candidate}", _field)
del _field, _candidate


def field_for_path(path: str) -> CanonicalField | None:
    """Unit/kind lookup for a checked raw path; None means format auto."""

    return _FIELD_BY_PATH.get(path)


def format_for_path(path: str, value: Any) -> str:
    """One value formatted for display, canonical-aware.

    The single formatter behind every surface — the metadata tree, the
    preview grid cells, the SVG/watermark output and the PowerPoint
    notes — so "3 kV" is "3 kV" everywhere. Unit/kind/decimals come
    from matching the raw path against CANONICAL_FIELDS; unknown paths
    fall through to the plain auto formatter.
    """

    field = field_for_path(path)
    if field is None:
        return formatting.format_value(value)
    return formatting.format_value(
        value, unit=field.unit, kind=field.kind, decimals=field.decimals
    )


def acquisition_datetime(meta) -> datetime | None:
    """When the image was acquired, for chronological ordering.

    Tries the "Acquired" field's dialect candidates in turn — the INI
    PrivateFei.TimeOfCreation (day-first, e.g. "10.07.2026 07:56:18")
    then the XML Acquisition.AcquisitionDatetime (ISO). Measured on the
    samples: the TIFFs answer on the INI path, the PNG on the XML one.
    Returns None when nothing parseable is present, which callers sort
    last rather than guessing an order.
    """

    field = FIELDS_BY_KEY.get("Acquired")
    if field is None:  # pragma: no cover - the table always has it
        return None
    for group, candidates in (
        (GROUP_MICROSCOPE, field.ini),
        (GROUP_XML, field.xml),
    ):
        for candidate in candidates:
            parsed = formatting.parse_datetime(meta.get(f"{group}.{candidate}"))
            if parsed is not None:
                return parsed
    return None


def discover_aliases(sections: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Map canonical section names onto the names this image uses.

    Reads the answer straight out of the metadata rather than guessing:
    Beam/Beam and Beam/Scan name their own sections, and Detectors/Name
    names the detector's. Falls back to whichever candidate section is
    actually present if those keys are missing.
    """

    aliases: dict[str, str] = {}
    beam = sections.get("Beam", {})

    def resolve(stated: Any, candidates: tuple[str, ...]) -> str | None:
        if isinstance(stated, str) and stated in sections:
            return stated
        for candidate in candidates:
            if candidate in sections:
                return candidate
        return None

    active_beam = resolve(beam.get("Beam"), ("EBeam", "IBeam"))
    if active_beam:
        aliases[SECTION_ACTIVE_BEAM] = active_beam

    active_scan = resolve(beam.get("Scan"), ("EScan", "IScan"))
    if active_scan:
        aliases[SECTION_ACTIVE_SCAN] = active_scan

    detector_name = sections.get("Detectors", {}).get("Name")
    if isinstance(detector_name, str) and detector_name in sections:
        aliases[SECTION_ACTIVE_DETECTOR] = detector_name

    return aliases


def canonical_section_name(section: str, aliases: dict[str, str]) -> str:
    """Reverse the alias map: 'EBeam' -> 'ActiveBeam'."""

    for canonical, actual in aliases.items():
        if actual == section:
            return canonical
    return section


def flatten(value: Any, prefix: str, out: dict[str, Any]) -> None:
    """Flatten nested dicts and lists into dotted paths."""

    if isinstance(value, dict):
        for key, child in value.items():
            flatten(child, f"{prefix}.{key}" if prefix else str(key), out)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            flatten(child, f"{prefix}[{index}]", out)
    else:
        out[prefix] = value


def flatten_sections(
    sections: dict[str, dict[str, Any]], aliases: dict[str, str]
) -> dict[str, Any]:
    """Flatten the INI dialect with alias substitution applied."""

    out: dict[str, Any] = {}
    for section, entries in sections.items():
        name = canonical_section_name(section, aliases)
        for key, value in entries.items():
            out[f"{GROUP_MICROSCOPE}.{name}.{key}"] = value
    return out


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def databar_height(
    sections: dict[str, dict[str, Any]],
    actual_width: int,
    actual_height: int,
) -> int:
    """Height of the TFS databar strip in pixels, or 0 if there is none.

    Image/ResolutionX and ResolutionY are the *scan* resolution. When an
    image is saved with its databar the file keeps the scan width but
    gains rows underneath, so the databar is the height difference — and
    it costs no pixel reads at all.

    The width equality is the load-bearing part, not the subtraction. It
    proves the frame was neither cropped nor rescaled, which is the only
    condition under which the height difference means anything:

        Electron_*.tif   3072x2188 vs 3072x2048  width matches -> 140 px
        ROI-2*.tif       4395x2200 vs 6144x4096  cropped ROI   -> none
        FIB Imaging*.tif  409x29   vs  512x442   thumbnail     -> none

    Without that guard the two cropped images report databars of 1896 and
    413 px, the latter on an image only 29 px tall. A pixel scan is no
    safer: ROI-2's bottom 140 rows are genuinely flat, so scanning for a
    uniform band reports a databar there that does not exist.

    PrivateFei/DatabarHeight is only a last resort — it reads 0 on all
    four samples, including the one with a real 140 px databar.
    """

    image = sections.get("Image", {})
    scan_width = _as_int(image.get("ResolutionX"))
    scan_height = _as_int(image.get("ResolutionY"))

    if scan_width and scan_height and actual_width == scan_width:
        return max(0, actual_height - scan_height)

    return max(0, _as_int(sections.get("PrivateFei", {}).get("DatabarHeight")))
