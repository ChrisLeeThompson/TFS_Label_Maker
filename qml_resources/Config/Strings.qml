pragma Singleton
import QtQuick
import "."

QtObject {

    // Main window. The version comes from the Python package
    // (tfs_lm.__version__) via the appVersion context property,
    // so the title always matches the actual release number.
    readonly property string mainWindowTitle:
        "TFS Label Maker " + appVersion

    // Group box titles
    readonly property string settingsGroupTitle: "Settings"
    readonly property string labelPreviewGroupTitle: "Label Preview"
    readonly property string metadataGroupTitle: "Metadata"
    readonly property string outputGroupTitle: "Output"

    readonly property string pptTransitionLabel: "Transition slide"
    readonly property string pptTransitionTooltip:
        "Insert a divider slide before the images, using this layout " +
        "number from your template. If the layout is missing, a blank " +
        "slide is used instead."
    readonly property string pptImageSlideLabel: "Image slide"
    readonly property string pptImageSlideTooltip:
        "Which layout number from your template each image slide uses. " +
        "If the layout is missing, plain blank slides are used instead."
    readonly property string pptSendLabel: "Send to active PPT"
    readonly property string pptSendTooltip:
        "On Start, add every loaded image to the presentation that is " +
        "already open, oldest first. The original image is sent, and the " +
        "chosen metadata goes into the slide notes. With no " +
        "metadata selected this sends the images only."
    readonly property string pptUnavailableTooltip:
        "Sending to PowerPoint needs Windows with pywin32 installed."
    readonly property string pptSendImpliedTooltip:
        "PowerPoint Only output always sends — pick another output " +
        "mode to make sending optional."
    readonly property string pptAddLabelObjectLabel: "Add label object"
    readonly property string pptAddLabelObjectTooltip:
        "Also place the label on each slide as a native PowerPoint " +
        "object — a plate behind key and value text boxes — so you can " +
        "move, resize, restyle and edit it in PowerPoint."

    readonly property string dropZoneTooltip:
        "Drop TFS images here (.tif, .tiff, .png). " +
        "Drop several at once to label a batch."

    // Status bar
    readonly property string loadButtonText: "Load"
    readonly property string startButtonText: "Start"
    readonly property string stopButtonText: "Stop"
    readonly property string clearButtonText: "Clear"
    readonly property string loadButtonTooltip:
        "Choose image files to load. Select several at once to label a batch."
    readonly property string clearButtonTooltip:
        "Remove every loaded image, emptying the metadata tree and the " +
        "label. Field selections are kept for this session and return " +
        "when a later batch shares them; use \"Deselect all\" to forget them."
    readonly property string loadDialogTitle: "Select TFS images"
    readonly property string startButtonTooltip:
        "Generate the selected output for every loaded image."
    readonly property string stopButtonTooltip:
        "Stop after the current image finishes."

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

    // Settings — tooltips
    readonly property string backgroundColorTooltip:
        "Fill colour of the label plate."
    readonly property string backgroundOpacityTooltip:
        "0 is fully transparent, 100 is fully opaque."
    readonly property string cornerRadiusTooltip:
        "Rounds the corners of the label plate. Applies whether or not a " +
        "border is drawn; 0 gives square corners."
    readonly property string borderThicknessTooltip:
        "Outline width in pixels. Set to 0 for no border."
    readonly property string borderColorTooltip:
        "Outline colour. Only used when border thickness is above 0."
    readonly property string fontFamilyTooltip:
        "Typeface for the label text, from the fonts installed on this " +
        "machine. SVG output references the font by name, so a viewer " +
        "without it will substitute another."
    readonly property string fontSizeTooltip:
        "Font size relative to a 1536 px wide image. Labels scale with " +
        "image resolution, so this keeps the same relative size on every image."
    readonly property string fontColorTooltip:
        "Colour of the label text."
    readonly property string labelPositionTooltip:
        "Which corner of the image the label sits in. Labels placed on the " +
        "bottom edge shift up automatically when a databar is detected."
    readonly property string labelMarginTooltip:
        "Inset between the label and the edge of the image."
    readonly property string labelColumnsTooltip:
        "How many columns the label grid has. Rows times " +
        "columns is how many cells the label holds."
    readonly property string labelRowsTooltip:
        "How many rows the label grid has. Rows times " +
        "columns is how many cells the label holds."
    readonly property string keyAlignmentTooltip:
        "How field names sit inside the key zone of their cell. Keys in " +
        "a column share one zone, so they stay lined up vertically."
    readonly property string valueAlignmentTooltip:
        "How values sit inside the value zone of their cell. Right keeps " +
        "numbers flush against the cell edge; values in a column stay " +
        "lined up."
    readonly property string keySeparatorTooltip:
        "Punctuation after each key. Applies to the whole label."
    readonly property string alignColumnsTooltip:
        "Give every column the widest column's key and value zone " +
        "widths, so keys and values line up across columns. Off means " +
        "each column fits its own content."
    readonly property string outputTooltip:
        "Watermarked images burn the label into a copy. SVG labels write " +
        "the label on its own for use in PowerPoint or figure software. " +
        "PowerPoint Only writes no files and just sends the images to " +
        "the open presentation."

    // Colour picker
    readonly property string colorPickerMoreText: "More…"
    readonly property string colorPickerDoneText: "Done"
    readonly property string colorPickerHexLabel: "Hex"
    readonly property string colorPickerContrastTooltip:
        "The candidate colour drawn over a black-to-white ramp — the tonal " +
        "range of a greyscale micrograph."

    // Metadata tree. The capacity-reached message ("The label grid is
    // full…") is emitted by the Python side through the status bar, so
    // it lives in tfs_lm/defaults.py (STATUS_LABEL_FULL) next to the
    // grid constants it reflects.
    readonly property string treeSearchPlaceholder: "Search metadata"
    readonly property string treeSearchTooltip:
        "Filter by key or value. A matching category shows everything " +
        "inside it."
    readonly property string treeExpandAllText: "Expand all"
    readonly property string treeExpandAllTooltip:
        "Show every category expanded. Searching always expands the matches."
    readonly property string treeDeselectAllText: "Deselect all"
    readonly property string treeDeselectAllTooltip:
        "Uncheck every selected metadata field. Custom text cells " +
        "stay; drag one out of the grid to remove it."

    // Label preview — custom text cells
    readonly property string customCellPlaceholder: "Custom text"
    readonly property string customCellEmptyTooltip:
        "Double-click to add your own text — a note that appears on " +
        "every image's label."
    readonly property string customCellEditTooltip:
        "Double-click to edit. Drag out of the grid to remove."
    readonly property string treeEmptyText:
        "Load images to select metadata."
    readonly property string treeNoSharedText:
        "The loaded images share no metadata categories. Images saved " +
        "in different formats carry different metadata — label them as " +
        "separate batches."
}
