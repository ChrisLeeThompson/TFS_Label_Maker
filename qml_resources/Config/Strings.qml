pragma Singleton
import QtQuick
import "."

// Every string the user reads, in one place. House rules, so the app
// reads as one voice: sentence case; tooltips are full sentences ending
// in a period, status messages are clauses without one; one term per
// concept (border, not outline; field name, not key; metadata list, not
// tree); no internal vocabulary (plate, zone, pixel constants, package
// names); and the ellipsis character, never three dots.
//
// Metadata field names and category titles are the exception: those come
// from the file verbatim (canonical.display_key, GROUP_DISPLAY_TITLES)
// so what the app shows is what the microscope wrote.
QtObject {

    // Main window. The version comes from the Python package
    // (tfs_lm.__version__) via the appVersion context property,
    // so the title always matches the actual release number.
    readonly property string mainWindowTitle:
        "TFS Label Maker " + appVersion

    // Group box titles
    readonly property string settingsGroupTitle: "Settings"
    readonly property string labelPreviewGroupTitle: "Label preview"
    readonly property string metadataGroupTitle: "Metadata"
    readonly property string outputGroupTitle: "Output"

    readonly property string pptTransitionLabel: "Transition slide"
    readonly property string pptTransitionTooltip:
        "Insert a transition slide before the images, using this layout " +
        "number from your template. If the layout is missing, a blank " +
        "slide is used instead."
    readonly property string pptImageSlideLabel: "Image slide"
    readonly property string pptImageSlideTooltip:
        "The layout number from your template each image slide uses. " +
        "If the layout is missing, blank slides are used instead."
    readonly property string pptSendLabel: "Send to active PPT"
    readonly property string pptSendTooltip:
        "On Start, add every loaded image to the open presentation, " +
        "oldest first by acquisition time. The original image is sent, " +
        "with the selected metadata in the slide notes."
    readonly property string pptUnavailableTooltip:
        "Sending to PowerPoint is only available on Windows with " +
        "PowerPoint installed."
    readonly property string pptSendImpliedTooltip:
        "The PowerPoint only output mode always sends. Pick another " +
        "output mode to make sending optional."
    readonly property string pptAddLabelObjectLabel: "Add label object"
    readonly property string pptAddLabelObjectTooltip:
        "Place the label on each slide as a PowerPoint object, so " +
        "you can move, resize, restyle and edit its text in PowerPoint."

    readonly property string dropZoneTooltip:
        "Drop TFS images here (.tif, .tiff, .png), several at once to " +
        "label a batch. Only images from SEM and FIB instruments are " +
        "supported."

    // Status bar
    readonly property string loadButtonText: "Load"
    readonly property string startButtonText: "Start"
    readonly property string stopButtonText: "Stop"
    readonly property string clearButtonText: "Clear"
    readonly property string loadButtonTooltip:
        "Choose images from your computer. Select several at once to " +
        "label a batch."
    readonly property string clearButtonTooltip:
        "Remove every loaded image, emptying the metadata list and the " +
        "label. Field selections are kept for this session and return " +
        "with the next batch that has them; use \"Deselect all\" to " +
        "forget them."
    readonly property string loadDialogTitle: "Select TFS SEM or FIB images"
    readonly property var loadDialogFilters: [
        "TFS images (*.tif *.tiff *.png)",
        "TIFF images (*.tif *.tiff)",
        "PNG images (*.png)",
        "All files (*)"
    ]
    readonly property string startButtonTooltip:
        "Generate the selected output for every loaded image."
    readonly property string stopButtonTooltip:
        "Stop after the current image finishes."
    readonly property string errorDialogTitle: "Error"

    // Settings — labels
    readonly property string backgroundColorLabel: "Background colour"
    readonly property string backgroundOpacityLabel: "Background opacity"
    readonly property string cornerRadiusLabel: "Corner radius"
    readonly property string borderThicknessLabel: "Border thickness"
    readonly property string borderColorLabel: "Border colour"
    readonly property string fontFamilyLabel: "Font"
    readonly property string fontSizeLabel: "Font size"
    readonly property string fontColorLabel: "Font colour"
    readonly property string labelPositionLabel: "Label position"
    readonly property string labelMarginLabel: "Label margin"
    readonly property string labelColumnsLabel: "Label columns"
    readonly property string labelRowsLabel: "Label rows"
    readonly property string keyAlignmentLabel: "Key alignment"
    readonly property string valueAlignmentLabel: "Value alignment"
    readonly property string keySeparatorLabel: "Key separator"
    readonly property string alignColumnsLabel: "Align columns"
    readonly property string outputLabel: "Output"
    readonly property string restoreDefaultsText: "Restore defaults"

    // Settings — tooltips
    readonly property string backgroundColorTooltip:
        "Fill colour of the label background."
    readonly property string backgroundOpacityTooltip:
        "0 is fully transparent, 100 is fully opaque."
    readonly property string cornerRadiusTooltip:
        "Rounds the corners of the label background. 0 gives square corners."
    readonly property string borderThicknessTooltip:
        "Border width in pixels. Set to 0 for no border."
    readonly property string borderColorTooltip:
        "Border colour. Only used when border thickness is above 0."
    readonly property string fontFamilyTooltip:
        "Typeface for the label text, from the fonts installed on this " +
        "machine. SVG labels name the font rather than embedding it, so " +
        "opening one where that font is missing shows a substitute."
    readonly property string fontSizeTooltip:
        "Text size on the label. Labels scale with the image, so one " +
        "setting looks the same on small and large images."
    readonly property string fontColorTooltip:
        "Colour of the label text."
    readonly property string labelPositionTooltip:
        "Which corner of the image the label sits in. Labels in the lower " +
        "corners shift up automatically when a databar is detected."
    readonly property string labelMarginTooltip:
        "Gap between the label and the edge of the image."
    readonly property string labelColumnsTooltip:
        "How many columns the label grid has. Rows times " +
        "columns is how many cells the label holds."
    readonly property string labelRowsTooltip:
        "How many rows the label grid has."
    readonly property string keyAlignmentTooltip:
        "How field names sit inside their half of the cell. Field names " +
        "in a column share one area, so they stay lined up."
    readonly property string valueAlignmentTooltip:
        "How values sit inside their half of the cell. Values in a column " +
        "stay lined up, so aligning right keeps numbers flush."
    readonly property string keySeparatorTooltip:
        "Punctuation after each field name. Applies to the whole label."
    readonly property string alignColumnsTooltip:
        "Line field names and values up across every column, using the " +
        "widest column's spacing. Off lets each column fit its own content."
    readonly property string outputTooltip:
        "Watermarked images write a copy with the label drawn into it. " +
        "SVG labels write the label on its own, for PowerPoint or figure " +
        "software. Both writes each. PowerPoint only writes no files and " +
        "sends the images to the open presentation."

    // Colour picker
    readonly property string colorPickerMoreText: "More…"
    readonly property string colorPickerDoneText: "Done"
    readonly property string colorPickerHexLabel: "Hex"
    readonly property string colorPickerHexPlaceholder: "#RRGGBB"
    readonly property string colorPickerSampleText: "1.00 kV   25 pA   19.3 µm"
    readonly property string colorPickerContrastTooltip:
        "The chosen colour over a black-to-white ramp, the tonal range " +
        "of a greyscale micrograph."

    // Metadata tree. The capacity-reached message ("The label grid is
    // full…") is emitted by the Python side through the status bar, so
    // it lives in tfs_lm/defaults.py (STATUS_LABEL_FULL) next to the
    // grid constants it reflects.
    // No tooltip: the placeholder text already says what the field does.
    readonly property string treeSearchPlaceholder: "Search metadata"
    readonly property string treeExpandAllText: "Expand all"
    readonly property string treeExpandAllTooltip:
        "Show every category expanded. Searching always expands the matches."
    readonly property string treeDeselectAllText: "Deselect all"
    readonly property string treeDeselectAllTooltip:
        "Deselect every metadata field. Custom text cells stay; drag one " +
        "out of the grid to remove it."

    // Label preview — custom text cells
    readonly property string customCellPlaceholder: "Custom text"
    readonly property string customCellEmptyTooltip:
        "Double-click to add your own text — a note that appears on " +
        "every image's label."
    readonly property string customCellEditTooltip:
        "Double-click to edit. Drag out of the grid to remove."
    readonly property string treeEmptyText:
        "Load images to select metadata."
    readonly property string treeNoMetadataText:
        "No readable metadata in the loaded images. The label can still " +
        "carry custom text — double-click an empty cell in the preview."
    readonly property string treeStoppedText:
        "Loading was stopped, so no fields are listed. Press Clear, then " +
        "load the images again."
    readonly property string treeBadgeTooltip:
        "Present in %1 of %2 images. Images without this field follow " +
        "the Missing metadata setting."

    // Batch nav row (under the label preview plate). The buttons carry
    // no tooltips — their captions say it. The ComboBox keeps one.
    readonly property string batchNavPreviousText: "Previous"
    readonly property string batchNavNextText: "Next"
    readonly property string batchNavFileTooltip:
        "The image the metadata list and label preview are showing. " +
        "Pick another image to jump straight to it."
    readonly property string batchNavPositionSeparator: " / "
    // Keyed on the field being absent, not on an empty value: a field
    // that is present but blank shows a dash and is never omitted.
    readonly property string cellOmittedTooltip:
        "This image does not have this field, so its label omits this " +
        "cell. Images that have the field keep it."

    // Missing metadata policy (Settings).
    readonly property string missingFieldLabel: "Missing metadata"
    readonly property string missingFieldTooltip:
        "What a label shows when its image does not have a selected " +
        "field. \"Omit from label\" drops the cell; \"Show as —\" keeps " +
        "the cell with a dash. Cells that will be omitted appear dimmed " +
        "in the preview."
}
