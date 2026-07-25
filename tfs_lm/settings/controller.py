"""Label styling and output settings, persisted through QSettings."""

from __future__ import annotations

import logging

from PySide6.QtCore import Property, QObject, QSettings, Signal, Slot
from PySide6.QtGui import QColor, QFontDatabase

from .. import defaults
from ..label.spec import LabelStyle

logger = logging.getLogger(__name__)


def _key(name: str) -> str:
    return defaults.SCHEMA_PREFIX + name


class SettingsController(QObject):
    """Live styling state, written through to QSettings on every change.

    Every setter returns early when the value is unchanged. That is not
    just an optimisation: QML two-way bindings re-enter the setter on the
    change notification, and without the guard the property ping-pongs
    and Qt eventually reports a binding loop.

    Colours are stored as #AARRGGBB strings rather than QColor variants.
    They round-trip identically, and the registry stays readable.
    """

    backgroundColorChanged = Signal()
    backgroundOpacityChanged = Signal()
    cornerRadiusChanged = Signal()
    borderThicknessChanged = Signal()
    borderColorChanged = Signal()
    fontFamilyChanged = Signal()
    fontSizeChanged = Signal()
    fontColorChanged = Signal()
    labelPositionChanged = Signal()
    labelMarginChanged = Signal()
    outputModeChanged = Signal()
    labelColumnsChanged = Signal()
    labelRowsChanged = Signal()
    alignColumnsChanged = Signal()
    keyAlignmentChanged = Signal()
    valueAlignmentChanged = Signal()
    keySeparatorChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = QSettings()
        # Windows lists vertical-writing variants with an "@" prefix;
        # they render text rotated 90° and are never what a label wants.
        self._families = [
            f for f in QFontDatabase.families() if not f.startswith("@")
        ]
        self._load()

    # --- Persistence -----------------------------------------------------

    def _load(self) -> None:
        s = self._settings

        def as_int(name: str, fallback: int, low: int, high: int) -> int:
            try:
                value = int(s.value(_key(name), fallback))
            except (TypeError, ValueError):
                logger.warning("Setting %r was not an integer; using default", name)
                return fallback
            return max(low, min(high, value))

        def as_bool(name: str, fallback: bool) -> bool:
            value = s.value(_key(name), fallback)
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("true", "1", "yes")

        def as_color(name: str, fallback: str) -> str:
            value = str(s.value(_key(name), fallback))
            color = QColor(value)
            if not color.isValid():
                logger.warning("Setting %r was not a colour; using default", name)
                return fallback
            return value

        self._background_color = as_color(
            "backgroundColor", defaults.BACKGROUND_COLOR_DEFAULT
        )
        self._background_opacity = as_int(
            "backgroundOpacity",
            defaults.BACKGROUND_OPACITY_DEFAULT,
            defaults.BACKGROUND_OPACITY_MIN,
            defaults.BACKGROUND_OPACITY_MAX,
        )
        self._corner_radius = as_int(
            "cornerRadius",
            defaults.CORNER_RADIUS_DEFAULT,
            defaults.CORNER_RADIUS_MIN,
            defaults.CORNER_RADIUS_MAX,
        )
        self._border_thickness = as_int(
            "borderThickness",
            defaults.BORDER_THICKNESS_DEFAULT,
            defaults.BORDER_THICKNESS_MIN,
            defaults.BORDER_THICKNESS_MAX,
        )
        self._border_color = as_color("borderColor", defaults.BORDER_COLOR_DEFAULT)
        self._font_family = self._valid_family(
            str(s.value(_key("fontFamily"), defaults.FONT_FAMILY_DEFAULT))
        )
        self._font_size = as_int(
            "fontSize",
            defaults.FONT_SIZE_DEFAULT,
            defaults.FONT_SIZE_MIN,
            defaults.FONT_SIZE_MAX,
        )
        self._font_color = as_color("fontColor", defaults.FONT_COLOR_DEFAULT)
        self._label_position = as_int(
            "labelPosition", defaults.POSITION_DEFAULT, 0, len(defaults.POSITION_NAMES) - 1
        )
        self._label_margin = as_int(
            "labelMargin",
            defaults.LABEL_MARGIN_DEFAULT,
            defaults.LABEL_MARGIN_MIN,
            defaults.LABEL_MARGIN_MAX,
        )
        self._output_mode = as_int(
            "outputMode", defaults.OUTPUT_DEFAULT, 0, len(defaults.OUTPUT_NAMES) - 1
        )
        self._label_columns = as_int(
            "labelColumns", defaults.COLUMNS_DEFAULT, 1, defaults.MAX_COLUMNS
        )
        self._label_rows = as_int(
            "labelRows", defaults.ROWS_DEFAULT, 1, defaults.MAX_ROWS
        )
        self._align_columns = as_bool(
            "alignColumns", defaults.ALIGN_COLUMNS_DEFAULT
        )
        self._key_alignment = as_int(
            "keyAlignment",
            defaults.KEY_ALIGNMENT_DEFAULT,
            0,
            len(defaults.ALIGNMENT_NAMES) - 1,
        )
        self._value_alignment = as_int(
            "valueAlignment",
            defaults.VALUE_ALIGNMENT_DEFAULT,
            0,
            len(defaults.ALIGNMENT_NAMES) - 1,
        )
        self._key_separator = as_int(
            "keySeparator",
            defaults.KEY_SEPARATOR_DEFAULT,
            0,
            len(defaults.SEPARATOR_NAMES) - 1,
        )

    def _store(self, name: str, value: object) -> None:
        self._settings.setValue(_key(name), value)

    def _valid_family(self, name: str) -> str:
        """A family that actually exists on this machine.

        A stale registry entry (font uninstalled since) or a settings
        file copied from another machine must not put a nonexistent name
        into the SVG output, where it would silently font-substitute.
        """

        if name in self._families:
            return name
        logger.warning("Font %r is not installed; falling back", name)
        if defaults.FONT_FAMILY_DEFAULT in self._families:
            return defaults.FONT_FAMILY_DEFAULT
        return self._families[0] if self._families else defaults.FONT_FAMILY_DEFAULT

    @Slot()
    def flush(self) -> None:
        """Force queued writes out to the backing store.

        QSettings buffers writes in a per-application cache and only
        commits them on a timer or at destruction. Re-reading in the same
        process hits that cache, so a lost write looks like a successful
        one — the loss is only visible from a fresh process. Anything that
        must survive an abrupt exit has to sync explicitly.
        """

        self._settings.sync()

    # --- Colours ---------------------------------------------------------

    @Property(QColor, notify=backgroundColorChanged)
    def backgroundColor(self) -> QColor:
        return QColor(self._background_color)

    @backgroundColor.setter
    def backgroundColor(self, value: QColor) -> None:
        name = QColor(value).name(QColor.NameFormat.HexArgb)
        if name == self._background_color:
            return
        self._background_color = name
        self._store("backgroundColor", name)
        self.backgroundColorChanged.emit()

    @Property(QColor, notify=borderColorChanged)
    def borderColor(self) -> QColor:
        return QColor(self._border_color)

    @borderColor.setter
    def borderColor(self, value: QColor) -> None:
        name = QColor(value).name(QColor.NameFormat.HexArgb)
        if name == self._border_color:
            return
        self._border_color = name
        self._store("borderColor", name)
        self.borderColorChanged.emit()

    @Property(QColor, notify=fontColorChanged)
    def fontColor(self) -> QColor:
        return QColor(self._font_color)

    @fontColor.setter
    def fontColor(self, value: QColor) -> None:
        name = QColor(value).name(QColor.NameFormat.HexArgb)
        if name == self._font_color:
            return
        self._font_color = name
        self._store("fontColor", name)
        self.fontColorChanged.emit()

    # --- Integers --------------------------------------------------------

    @Property(int, notify=backgroundOpacityChanged)
    def backgroundOpacity(self) -> int:
        return self._background_opacity

    @backgroundOpacity.setter
    def backgroundOpacity(self, value: int) -> None:
        value = max(
            defaults.BACKGROUND_OPACITY_MIN,
            min(defaults.BACKGROUND_OPACITY_MAX, int(value)),
        )
        if value == self._background_opacity:
            return
        self._background_opacity = value
        self._store("backgroundOpacity", value)
        self.backgroundOpacityChanged.emit()

    @Property(int, notify=cornerRadiusChanged)
    def cornerRadius(self) -> int:
        return self._corner_radius

    @cornerRadius.setter
    def cornerRadius(self, value: int) -> None:
        value = max(
            defaults.CORNER_RADIUS_MIN, min(defaults.CORNER_RADIUS_MAX, int(value))
        )
        if value == self._corner_radius:
            return
        self._corner_radius = value
        self._store("cornerRadius", value)
        self.cornerRadiusChanged.emit()

    @Property(int, notify=borderThicknessChanged)
    def borderThickness(self) -> int:
        return self._border_thickness

    @borderThickness.setter
    def borderThickness(self, value: int) -> None:
        value = max(
            defaults.BORDER_THICKNESS_MIN,
            min(defaults.BORDER_THICKNESS_MAX, int(value)),
        )
        if value == self._border_thickness:
            return
        self._border_thickness = value
        self._store("borderThickness", value)
        self.borderThicknessChanged.emit()

    @Property(str, notify=fontFamilyChanged)
    def fontFamily(self) -> str:
        return self._font_family

    @fontFamily.setter
    def fontFamily(self, value: str) -> None:
        value = self._valid_family(str(value))
        if value == self._font_family:
            return
        self._font_family = value
        self._store("fontFamily", value)
        self.fontFamilyChanged.emit()

    @Property(int, notify=fontSizeChanged)
    def fontSize(self) -> int:
        return self._font_size

    @fontSize.setter
    def fontSize(self, value: int) -> None:
        value = max(defaults.FONT_SIZE_MIN, min(defaults.FONT_SIZE_MAX, int(value)))
        if value == self._font_size:
            return
        self._font_size = value
        self._store("fontSize", value)
        self.fontSizeChanged.emit()

    @Property(int, notify=labelPositionChanged)
    def labelPosition(self) -> int:
        return self._label_position

    @labelPosition.setter
    def labelPosition(self, value: int) -> None:
        value = max(0, min(len(defaults.POSITION_NAMES) - 1, int(value)))
        if value == self._label_position:
            return
        self._label_position = value
        self._store("labelPosition", value)
        self.labelPositionChanged.emit()

    @Property(int, notify=labelMarginChanged)
    def labelMargin(self) -> int:
        return self._label_margin

    @labelMargin.setter
    def labelMargin(self, value: int) -> None:
        value = max(
            defaults.LABEL_MARGIN_MIN, min(defaults.LABEL_MARGIN_MAX, int(value))
        )
        if value == self._label_margin:
            return
        self._label_margin = value
        self._store("labelMargin", value)
        self.labelMarginChanged.emit()

    @Property(int, notify=outputModeChanged)
    def outputMode(self) -> int:
        return self._output_mode

    @outputMode.setter
    def outputMode(self, value: int) -> None:
        value = max(0, min(len(defaults.OUTPUT_NAMES) - 1, int(value)))
        if value == self._output_mode:
            return
        self._output_mode = value
        self._store("outputMode", value)
        self.outputModeChanged.emit()

    @Property(int, notify=labelColumnsChanged)
    def labelColumns(self) -> int:
        return self._label_columns

    @labelColumns.setter
    def labelColumns(self, value: int) -> None:
        value = max(1, min(defaults.MAX_COLUMNS, int(value)))
        if value == self._label_columns:
            return
        self._label_columns = value
        self._store("labelColumns", value)
        self.labelColumnsChanged.emit()

    @Property(int, notify=labelRowsChanged)
    def labelRows(self) -> int:
        return self._label_rows

    @labelRows.setter
    def labelRows(self, value: int) -> None:
        value = max(1, min(defaults.MAX_ROWS, int(value)))
        if value == self._label_rows:
            return
        self._label_rows = value
        self._store("labelRows", value)
        self.labelRowsChanged.emit()

    @Property(bool, notify=alignColumnsChanged)
    def alignColumns(self) -> bool:
        return self._align_columns

    @alignColumns.setter
    def alignColumns(self, value: bool) -> None:
        value = bool(value)
        if value == self._align_columns:
            return
        self._align_columns = value
        self._store("alignColumns", value)
        self.alignColumnsChanged.emit()

    @Property(int, notify=keyAlignmentChanged)
    def keyAlignment(self) -> int:
        return self._key_alignment

    @keyAlignment.setter
    def keyAlignment(self, value: int) -> None:
        value = max(0, min(len(defaults.ALIGNMENT_NAMES) - 1, int(value)))
        if value == self._key_alignment:
            return
        self._key_alignment = value
        self._store("keyAlignment", value)
        self.keyAlignmentChanged.emit()

    @Property(int, notify=valueAlignmentChanged)
    def valueAlignment(self) -> int:
        return self._value_alignment

    @valueAlignment.setter
    def valueAlignment(self, value: int) -> None:
        value = max(0, min(len(defaults.ALIGNMENT_NAMES) - 1, int(value)))
        if value == self._value_alignment:
            return
        self._value_alignment = value
        self._store("valueAlignment", value)
        self.valueAlignmentChanged.emit()

    @Property(int, notify=keySeparatorChanged)
    def keySeparator(self) -> int:
        return self._key_separator

    @keySeparator.setter
    def keySeparator(self, value: int) -> None:
        value = max(0, min(len(defaults.SEPARATOR_NAMES) - 1, int(value)))
        if value == self._key_separator:
            return
        self._key_separator = value
        self._store("keySeparator", value)
        self.keySeparatorChanged.emit()

    # --- Derived, read-only ----------------------------------------------

    @Property(bool, notify=borderThicknessChanged)
    def hasBorder(self) -> bool:
        """Gates the border colour picker. Thickness 0 means no border."""

        return self._border_thickness > 0

    @Property(str, notify=keySeparatorChanged)
    def keySeparatorSuffix(self) -> str:
        """The literal suffix ("", ":", " -") — the preview appends this
        to key texts so QML never hand-syncs the index->string map."""

        return defaults.SEPARATOR_SUFFIXES[self._key_separator]

    @Property(bool, notify=outputModeChanged)
    def outputIsPptOnly(self) -> bool:
        """Gates the send checkbox: this mode IS a send, so the box shows
        checked and refuses interaction without touching the stored flag."""

        return self._output_mode == defaults.OUTPUT_PPT_ONLY

    @Property(list, constant=True)
    def fontFamilies(self) -> list:
        return list(self._families)

    @Property(list, constant=True)
    def positionNames(self) -> list:
        return list(defaults.POSITION_NAMES)

    @Property(list, constant=True)
    def outputNames(self) -> list:
        return list(defaults.OUTPUT_NAMES)

    @Property(list, constant=True)
    def alignmentNames(self) -> list:
        return list(defaults.ALIGNMENT_NAMES)

    @Property(list, constant=True)
    def separatorNames(self) -> list:
        return list(defaults.SEPARATOR_NAMES)

    # --- Slots -----------------------------------------------------------

    @Slot()
    def restoreDefaults(self) -> None:
        logger.info("Restoring default label settings")
        self.backgroundColor = QColor(defaults.BACKGROUND_COLOR_DEFAULT)
        self.backgroundOpacity = defaults.BACKGROUND_OPACITY_DEFAULT
        self.cornerRadius = defaults.CORNER_RADIUS_DEFAULT
        self.borderThickness = defaults.BORDER_THICKNESS_DEFAULT
        self.borderColor = QColor(defaults.BORDER_COLOR_DEFAULT)
        self.fontFamily = defaults.FONT_FAMILY_DEFAULT
        self.fontSize = defaults.FONT_SIZE_DEFAULT
        self.fontColor = QColor(defaults.FONT_COLOR_DEFAULT)
        self.labelPosition = defaults.POSITION_DEFAULT
        self.labelMargin = defaults.LABEL_MARGIN_DEFAULT
        self.outputMode = defaults.OUTPUT_DEFAULT
        self.labelColumns = defaults.COLUMNS_DEFAULT
        self.labelRows = defaults.ROWS_DEFAULT
        self.alignColumns = defaults.ALIGN_COLUMNS_DEFAULT
        self.keyAlignment = defaults.KEY_ALIGNMENT_DEFAULT
        self.valueAlignment = defaults.VALUE_ALIGNMENT_DEFAULT
        self.keySeparator = defaults.KEY_SEPARATOR_DEFAULT
        self.flush()

    # --- Snapshot for workers --------------------------------------------

    def label_style(self) -> LabelStyle:
        """Immutable copy safe to hand to a worker thread."""

        return LabelStyle(
            background_color=self._background_color,
            background_opacity=self._background_opacity,
            corner_radius=self._corner_radius,
            border_thickness=self._border_thickness,
            border_color=self._border_color,
            font_family=self._font_family,
            font_size=self._font_size,
            font_color=self._font_color,
            position=self._label_position,
            margin=self._label_margin,
            align_columns=self._align_columns,
            key_alignment=self._key_alignment,
            value_alignment=self._value_alignment,
            key_separator=self._key_separator,
        )
