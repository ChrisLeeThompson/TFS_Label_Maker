"""Immutable descriptions of a label and how it should look.

These are plain frozen dataclasses with no Qt object ownership, so a
snapshot can be handed to a worker thread and used while the GUI thread
keeps mutating the live settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import defaults


@dataclass(frozen=True, slots=True)
class LabelStyle:
    """Everything the renderer needs that is not per-image."""

    background_color: str = defaults.BACKGROUND_COLOR_DEFAULT
    background_opacity: int = defaults.BACKGROUND_OPACITY_DEFAULT

    corner_radius: int = defaults.CORNER_RADIUS_DEFAULT
    border_thickness: int = defaults.BORDER_THICKNESS_DEFAULT
    border_color: str = defaults.BORDER_COLOR_DEFAULT

    # Uniform column widths (everything as wide as the widest column)
    # versus per-column autofit. Some users want keys/values aligned
    # across columns, some want the tightest plate.
    align_columns: bool = defaults.ALIGN_COLUMNS_DEFAULT

    # Where key and value text sits inside its zone (defaults.ALIGN_*).
    # Zones are per-column, so texts line up vertically regardless.
    key_alignment: int = defaults.KEY_ALIGNMENT_DEFAULT
    value_alignment: int = defaults.VALUE_ALIGNMENT_DEFAULT

    # Punctuation after every key (index into defaults.SEPARATOR_*):
    # none, colon, or dash — label-wide.
    key_separator: int = defaults.KEY_SEPARATOR_DEFAULT

    font_family: str = defaults.FONT_FAMILY_DEFAULT
    font_size: int = defaults.FONT_SIZE_DEFAULT
    font_color: str = defaults.FONT_COLOR_DEFAULT

    position: int = defaults.POSITION_DEFAULT
    margin: int = defaults.LABEL_MARGIN_DEFAULT

    @property
    def has_border(self) -> bool:
        """Thickness is the sole on/off control; radius is independent."""

        return self.border_thickness > 0

    def scale_for(self, image_width: int) -> float:
        """Multiplier so a label covers the same fraction of any image."""

        if image_width <= 0:
            return 1.0
        return image_width / defaults.REFERENCE_WIDTH_PX


@dataclass(frozen=True, slots=True)
class CellSpec:
    """One key/value pair occupying a slot in the label matrix."""

    path: str          # canonical dotted path, the cell's stable identity
    key_text: str      # display name, e.g. "HV"
    value_text: str    # already formatted, e.g. "3.00 kV"
    # PREVIEW-ONLY ghost state: the current image lacks this path AND
    # the missing-field policy is Omit, so this image's label will drop
    # the cell. Export builders never construct omitted cells — they
    # filter or dash per policy, per image, at task-build time.
    omitted: bool = False


@dataclass(frozen=True, slots=True)
class CustomCellSpec:
    """A user-typed free string occupying a slot — no path, no key/value
    split, identical on every image; never derived from metadata. Renders
    as one text spanning the cell's full width."""

    text: str


@dataclass(frozen=True, slots=True)
class PlacedCell:
    """A cell pinned to the grid position the user arranged it into."""

    cell: CellSpec | CustomCellSpec
    row: int
    column: int


@dataclass(frozen=True, slots=True)
class LabelSpec:
    """A complete label for one image, ready to measure and paint.

    Geometry comes from the placements: the layout trims rows and
    columns that hold no cell, preserving the user's arrangement of the
    occupied ones (their explicit design decision).
    """

    cells: tuple[PlacedCell, ...] = field(default_factory=tuple)
    style: LabelStyle = field(default_factory=LabelStyle)

    image_width: int = 0
    image_height: int = 0
    databar_height: int = 0

    @property
    def has_databar(self) -> bool:
        return self.databar_height > 0

    @property
    def bottom_offset(self) -> int:
        """Extra clearance needed above the bottom edge, in image pixels."""

        if not self.has_databar:
            return 0
        if not defaults.position_is_bottom(self.style.position):
            return 0
        return self.databar_height
