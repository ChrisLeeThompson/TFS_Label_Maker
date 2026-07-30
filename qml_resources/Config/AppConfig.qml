pragma Singleton
import QtQuick
import QtQuick.Controls.Universal

QtObject {

    // Theme colors
    readonly property int universalTheme: Universal.Dark
    readonly property color universalAccent: "#2ea2ec"
    readonly property color universalForeground: "#ffffff"
    readonly property color universalBackground: "#1e2c36"
    readonly property color textDisabledColor: "#8498a4"
    readonly property color placeholderTextColor: "#9CBBD2"
    readonly property color errorColor: "#e0594f"
    readonly property color successColor: "#33ff33"
    readonly property color warningColor: "#ffc633"

    // Main window
    readonly property int mainWindowWidth: 910
    readonly property int mainWindowHeight: 1040
    readonly property int mainWindowMinimumWidth: 700
    readonly property int mainWindowMinimumHeight: 700

    // Tooltip durations
    readonly property int toolTipDelayMs: 1500
    readonly property int toolTipTimeoutMs: 10000

    // Buttons
    readonly property int buttonRadius: 4
    readonly property int buttonPadding: 16

    // Status Bar
    readonly property int statusBarLabelFontSize: 16
    readonly property int statusBarHorizontalMargin: 12
    readonly property int statusBarProgressWidth: 300
    readonly property int statusBarMessageDurationMs: 10000
    readonly property int statusBarButtonSpacing: 8
    readonly property int statusBarButtonPadding: 10
    readonly property int statusBarHeight: 40
    readonly property int statusBarProgressResetMs: 3000

    // Container — colors
    readonly property color containerBackground: "#263640"
    readonly property color containerIdleBorder: "#2e3e49"

    // Container - layout
    readonly property int containerBorderRadius: 4
    readonly property int containerBorderWidth: 1

    // Pages / typography
    readonly property int pageMargin: 12
    readonly property int pageBodyFontSize: 16
    readonly property int pageHeadingFontSize: 20
    readonly property int pageSectionSpacing: 12

    // Form layout (label | control pairs inside group boxes)
    readonly property int formRowSpacing: 8
    readonly property int formColumnSpacing: 16

    // Row heights.
    readonly property int topRowHeight: 400
    readonly property int topRowMinimumHeight: 240
    readonly property int topRowMaximumHeight: 480
    readonly property int labelPreviewMinimumHeight: 140
    readonly property int metadataTreeMinimumHeight: 220

    readonly property int topRowRightColumnWidth: 300

    // PowerPoint. Mirrors SLIDE_INDEX_MIN/MAX in tfs_lm/defaults.py.
    readonly property int pptSlideIndexMin: 1
    readonly property int pptSlideIndexMax: 200

    // Drop zone
    readonly property int dropZoneMinimumWidth: 220
    readonly property int dropZoneMinimumHeight: 120
    readonly property int dropZoneIconMargin: 8
    readonly property int dropZoneHoverDurationMs: 120
    readonly property color dropZoneActiveBorder: "#2ea2ec"

    // Label preview (the Excel-like slot grid on the styled plate)
    readonly property int labelPreviewCellSpacing: 6
    readonly property int labelPreviewCellHeight: 36
    readonly property int labelPreviewPlatePadding: 10
    // The Card's title band + margins around the preview content:
    // pageMargin (title top) + ~21 px title + formRowSpacing + pageMargin
    // (bottom). Static token, not derived from live heights — same
    // binding-loop rationale as topRowMaximumHeight above.
    readonly property int labelPreviewCardChrome: 56
    // The editor has no image to scale against, so the cell font is
    // capped rather than scaled; the output renders the real size.
    readonly property int labelPreviewFontSizeCap: 24
    // Gap between the plate's fixed frame and the batch nav row.
    readonly property int labelPreviewNavSpacing: 8
    // Ghosted metadata texts on cells the current image's label will
    // omit. Distinct from the drag dims (0.7 / 0.35) so the three
    // states stay tellable apart.
    readonly property real labelPreviewCellOmittedOpacity: 0.45

    // Metadata tree. The key/value divider sits at half the row width,
    // matching the reference Project Explorers' half-viewport divider.
    readonly property int treeIndentWidth: 18
    readonly property int treeRowHeight: 26
    readonly property int treeChevronSize: 12
    readonly property int treeChevronRotateDurationMs: 125
    readonly property real treeKeyColumnRatio: 0.5
    readonly property real treeKeyColumnRatioMin: 0.15
    readonly property real treeKeyColumnRatioMax: 0.85
    readonly property int treeDividerHitWidth: 10
    readonly property int treeCellSpacing: 8
    // The "n/m" presence badge on partial fields.
    readonly property int treeBadgeFontSize: 12
    readonly property int treeBadgeHeight: 16
    readonly property int treeBadgeHPadding: 6

    // Colour picker
    readonly property int colorSwatchSize: 32
    readonly property int colorSwatchSpacing: 4
    readonly property int colorPickerColumns: 6
    readonly property int contrastStripHeight: 34
    // colorPickerColumns * colorSwatchSize + (columns - 1) * spacing,
    // plus pageMargin padding on both sides: 6*32 + 5*4 + 24 = 236.
    readonly property int colorPickerPopupWidth: 236
    readonly property int colorPickerWidth: 150
    readonly property int comboBoxWidth: 190
    // The PowerPoint card's narrow column cannot host a spin box at its
    // natural width (the Universal background floors it at ~200 px), so
    // its spin boxes are pinned to what three digits + arrows need.
    readonly property int pptSpinBoxWidth: 116

    // Icon paths.
    readonly property url iconCatbugColor: "../assets/catbug_color_2.png"
    readonly property url iconCatbugGrayscale: "../assets/catbug_grayscale_2.png"
    readonly property url iconCatbugWaiting: "../assets/catbug_waiting_color.svg"

    // The Project Explorers hard-swap the pixmap because they are Qt
    // Widgets apps; a cross-fade is free in QML, so the two images are
    // stacked and their opacity animated instead.
    readonly property int dropZoneCrossfadeMs: 140
    // Full opacity: the desaturation already signals "idle", and dimming
    // on top of it only muddies the artwork against the dark card.
    readonly property real dropZoneIdleOpacity: 1.0
    readonly property url iconChevronRight: "../assets/chevron-right.svg"
    readonly property url iconDownArrow: "../assets/down_arrow_white.svg"

    // --- Label style bounds -------------------------------------------
    // Mirrors tfs_lm/defaults.py. Keep the two in step: these drive the
    // spin boxes, those drive the renderer and the QSettings round trip.
    readonly property int backgroundOpacityMin: 0
    readonly property int backgroundOpacityMax: 100

    readonly property int cornerRadiusMin: 0
    readonly property int cornerRadiusMax: 64

    readonly property int borderThicknessMin: 0
    readonly property int borderThicknessMax: 16

    readonly property int fontSizeMin: 6
    readonly property int fontSizeMax: 200

    readonly property int labelMarginMin: 0
    readonly property int labelMarginMax: 256

    readonly property int labelColumnsMin: 1
    readonly property int labelColumnsMax: 4

    readonly property int labelRowsMin: 1
    readonly property int labelRowsMax: 4

}
