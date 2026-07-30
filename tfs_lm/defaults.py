"""All tunable constants and persisted-setting defaults.

Bounds live here rather than in QML so the spin boxes, the QSettings
round trip and the renderer cannot drift apart.
"""

from __future__ import annotations

# --- QSettings -----------------------------------------------------------
# Every persisted key is written as SCHEMA_PREFIX + name, so bumping this
# one string re-namespaces all stored state in a single edit.
SCHEMA_PREFIX = "v1/"

ORGANIZATION_NAME = "TFS_AutoScript"
APPLICATION_NAME = "TFS_AutoScript_LabelMaker_v1"

# --- Input ---------------------------------------------------------------
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".tif", ".tiff", ".png"})

# --- Status messages -----------------------------------------------------
# The status bar is the app's only message channel, so the opening
# instruction lives here rather than as a caption under the drop zone.
#
# Length is load-bearing: at the 700 px minimum window width, with the
# progress bar collapsed and the Load/Stop/Start row taking 173 px, the
# message has 471 px. This string measures 434 px in Segoe UI at 16 px.
# Anything much longer elides on a narrow window.
STATUS_READY = "Drop a file or batch of files onto Catbug, or click Load, to begin."

# --- Label matrix --------------------------------------------------------
# The user configures an explicit rows x columns grid (Excel-like slot
# matrix); its size IS the check capacity.
MAX_COLUMNS = 4
MAX_ROWS = 4
MAX_CELLS = MAX_COLUMNS * MAX_ROWS  # 16

COLUMNS_DEFAULT = 2
ROWS_DEFAULT = 4

# Column widths in the output: per-column autofit by default; aligned
# means every column takes the widest column's width so cells line up
# across columns.
ALIGN_COLUMNS_DEFAULT = False

# Shown when a check would exceed the grid's slot count. The check is
# refused outright, not queued. Status text a Python controller emits
# lives here, not in Strings.qml — one source of truth per string.
# "Remove a cell", not "uncheck a field": with custom text cells in the
# grid, unchecking is no longer the only remedy.
STATUS_LABEL_FULL = "The label grid is full. Remove a cell or enlarge the grid."

# --- Label styling -------------------------------------------------------
# Font size is expressed against REFERENCE_WIDTH_PX and scaled per image,
# so a label occupies the same fraction of a 768 px and a 4395 px image.
REFERENCE_WIDTH_PX = 1536.0

BACKGROUND_COLOR_DEFAULT = "#1e2c36"

BACKGROUND_OPACITY_DEFAULT = 60
BACKGROUND_OPACITY_MIN = 0
BACKGROUND_OPACITY_MAX = 100

# Radius shapes the background rounded rect and is independent of the
# border; a rounded label with no outline is a valid combination.
CORNER_RADIUS_DEFAULT = 4
CORNER_RADIUS_MIN = 0
CORNER_RADIUS_MAX = 64

# Thickness 0 means "no border" — it is the only on/off control for the
# stroke, which is why the minimum is 0 rather than 1.
BORDER_THICKNESS_DEFAULT = 0
BORDER_THICKNESS_MIN = 0
BORDER_THICKNESS_MAX = 16

BORDER_COLOR_DEFAULT = "#ffffff"

FONT_SIZE_DEFAULT = 18
FONT_SIZE_MIN = 6
FONT_SIZE_MAX = 200

FONT_COLOR_DEFAULT = "#ffffff"

# Default only — the user picks from the installed families at runtime.
FONT_FAMILY_DEFAULT = "Arial"

# --- Cell text alignment -------------------------------------------------
# Keys and values are separate texts, each aligned inside its own zone of
# the cell; zones are shared per column so the texts line up vertically.
ALIGN_LEFT = 0
ALIGN_CENTER = 1
ALIGN_RIGHT = 2

ALIGNMENT_NAMES: tuple[str, ...] = ("Left", "Center", "Right")

KEY_ALIGNMENT_DEFAULT = ALIGN_LEFT
VALUE_ALIGNMENT_DEFAULT = ALIGN_RIGHT

# Punctuation appended to every key text, label-wide. Index-paired with
# SEPARATOR_NAMES: the name feeds the combobox, the suffix feeds the
# renderer ("HV", "HV:", "HV -").
SEPARATOR_NAMES: tuple[str, ...] = ("None", "Colon", "Dash")
SEPARATOR_SUFFIXES: tuple[str, ...] = ("", ":", " -")

KEY_SEPARATOR_DEFAULT = 0  # None — the zone gap already separates

# --- Missing-field policy ------------------------------------------------
# What a label shows when its image lacks a CHECKED field entirely (the
# path is absent from that image's metadata — e.g. an ICD image and the
# TLD-only SuctionTube). Omit drops the cell from that image's label
# (an emptied row/column collapses); Dash keeps the cell as "Key: —".
# Keys on PATH ABSENCE, never on formatted emptiness: a present-but-blank
# value renders its em dash under both policies. Index-paired with the
# combobox, same contract as SEPARATOR_NAMES.
MISSING_FIELD_OMIT = 0
MISSING_FIELD_DASH = 1

MISSING_FIELD_NAMES: tuple[str, ...] = ("Omit from label", "Show as —")

MISSING_FIELD_DEFAULT = MISSING_FIELD_OMIT

# --- Label geometry ------------------------------------------------------
LABEL_MARGIN_DEFAULT = 16
LABEL_MARGIN_MIN = 0
LABEL_MARGIN_MAX = 256

CELL_PADDING_PX = 6
COLUMN_GAP_PX = 18
ROW_GAP_PX = 4

# Gap between a cell's key zone and value zone. Replaces the ": " the
# joined string used to carry (~10 px at the default 18 px font); kept
# well below COLUMN_GAP_PX so a key/value pair still reads as one cell.
KEY_VALUE_GAP_PX = 10

# --- Label position ------------------------------------------------------
POSITION_UPPER_LEFT = 0
POSITION_UPPER_RIGHT = 1
POSITION_LOWER_LEFT = 2
POSITION_LOWER_RIGHT = 3

POSITION_NAMES: tuple[str, ...] = (
    "Upper left",
    "Upper right",
    "Lower left",
    "Lower right",
)

POSITION_DEFAULT = POSITION_LOWER_LEFT


def position_is_bottom(position: int) -> bool:
    """True when a position sits on the bottom edge and needs the databar shift."""

    return position in (POSITION_LOWER_LEFT, POSITION_LOWER_RIGHT)


# --- Output --------------------------------------------------------------
OUTPUT_WATERMARK = 0
OUTPUT_SVG = 1
OUTPUT_BOTH = 2
# Sends to the open presentation and writes nothing — no files, no run
# directory. Appended so stored indices from older versions keep their
# meaning; the index IS the persisted value and the combo box position.
OUTPUT_PPT_ONLY = 3

OUTPUT_NAMES: tuple[str, ...] = (
    "Watermarked images",
    "SVG labels",
    "Both",
    "PowerPoint Only",
)

OUTPUT_DEFAULT = OUTPUT_BOTH


def output_writes_watermark(mode: int) -> bool:
    return mode in (OUTPUT_WATERMARK, OUTPUT_BOTH)


def output_writes_svg(mode: int) -> bool:
    return mode in (OUTPUT_SVG, OUTPUT_BOTH)


def outputs_per_image(mode: int) -> int:
    """Progress-bar units contributed by one image under this output mode."""

    return int(output_writes_watermark(mode)) + int(output_writes_svg(mode))


# --- PowerPoint ----------------------------------------------------------
# The two indices are positions in the OPEN PRESENTATION'S TEMPLATE
# (Designs(1).SlideMaster.CustomLayouts), not slide numbers and not
# animations — the same meaning Images_To_PPT_v3 gives them, which is
# why the defaults are its defaults. When a deck has no such layout the
# send falls back to a plain blank slide.
TRANSITION_ENABLED_DEFAULT = True
TRANSITION_SLIDE_INDEX_DEFAULT = 24
IMAGE_SLIDE_INDEX_DEFAULT = 8

SLIDE_INDEX_MIN = 1
SLIDE_INDEX_MAX = 200

SEND_TO_ACTIVE_PPT_DEFAULT = False
ADD_LABEL_OBJECT_DEFAULT = False

# Fraction of the slide a placed image may occupy.
PPT_IMAGE_FIT = 0.92

# Internal TextFrame margin of the native label text boxes, in points.
# Boxes are grown by the same amount so the text stays on the layout's
# zone geometry while remaining comfortable to edit.
PPT_TEXT_MARGIN_PT = 2.0

# Status text the PowerPoint controller emits. Lives here, not in
# Strings.qml — one source of truth for strings only Python sets.
STATUS_PPT_CONNECTING = "Connecting to PowerPoint…"
STATUS_PPT_NO_PRESENTATION = (
    "PowerPoint send failed — open a presentation, then press Start again"
)
STATUS_PPT_CLOSED = "PowerPoint closed during the send"
STATUS_PPT_UNAVAILABLE = "PowerPoint sending needs Windows with pywin32 installed"
STATUS_PPT_NOTHING = "Nothing to send — no image parsed successfully"

# --- Run directory -------------------------------------------------------
RUN_DIR_PREFIX = "labelled_images_"
RUN_DIR_TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"

# --- Threading -----------------------------------------------------------
THREAD_JOIN_TIMEOUT_MS = 5000
