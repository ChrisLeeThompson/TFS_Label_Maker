import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Universal
import "../Config"

// The label matrix as an Excel-like slot grid: rows x columns of fixed,
// clearly-bounded cells (per the Label rows / Label columns settings),
// each empty, holding one checked field, or holding user-typed custom
// text. Checking fills the first empty cell column-wise (down column 1,
// then column 2); dragging moves a cell's item to an empty cell or
// swaps it with the occupant; dropping outside the plate deletes the
// cell (uncheck / remove); double-clicking an empty cell types a
// custom note that appears on every image's label.
//
// The grid is an overlay on the label plate: the rectangle behind it
// shows the label's real background colour, opacity, corner radius and
// border styling live, so arranging and styling happen on one surface.
// This grid is the editor, not the renderer: cells split into key/value
// halves that follow the alignment settings, while the output lays true
// per-column zones. (The output still trims empty rows/columns; the
// plate here frames the full grid because the grid is the editor.)
Item {

    id: root

    // --- Public state ---
    required property var label     // LabelController: matrix, moveCell, removeCell, setCustomText
    required property var settings  // SettingsController: plate + font styling
    required property var images    // ImageSetController: batch cycling
    property bool interactive: true

    // The card sizes itself from this — a fixed frame: the largest
    // grid (4 rows) plus a permanently reserved nav strip, so changing
    // Label rows/columns (or a batch loading) never resizes the card
    // or the window. The plate grows and shrinks centred inside.
    // Math.max is the safety valve: content that genuinely exceeds
    // the frame grows the card rather than clipping, because clipped
    // rows silently stop receiving drag hover (the regression a
    // fixed-height card caused once already).
    readonly property real _maxPlateHeight:
        AppConfig.labelRowsMax * AppConfig.labelPreviewCellHeight
        + (AppConfig.labelRowsMax - 1) * AppConfig.labelPreviewCellSpacing
        + 2 * AppConfig.labelPreviewPlatePadding
    readonly property real _navReserve:
        navRow.implicitHeight + AppConfig.labelPreviewNavSpacing

    implicitHeight: Math.max(_maxPlateHeight, plate.height) + _navReserve
    implicitWidth: Math.max(plate.width, navRow.implicitWidth)

    readonly property var _hAlign: [Text.AlignLeft, Text.AlignHCenter,
                                    Text.AlignRight]

    readonly property real _cellWidth: {
        const cols = Math.max(1, root.label.columns)
        const avail = width - 2 * AppConfig.labelPreviewPlatePadding
                      - (cols - 1) * AppConfig.labelPreviewCellSpacing
        return Math.max(60, avail / cols)
    }

    // Root coordinates — the dragged chip is reparented to root, so its
    // x/y compare directly against the (centred) plate's frame.
    function _insidePlate(px, py) {
        return px >= plate.x && px <= plate.x + plate.width
            && py >= plate.y && py <= plate.y + plate.height
    }

    Rectangle {
        id: plate
        anchors.centerIn: parent
        // Centred in the space above the reserved nav strip. Layout
        // only — plate stays a direct child of root, so _insidePlate's
        // coordinate comparison is untouched.
        anchors.verticalCenterOffset: -root._navReserve / 2
        width: cellGrid.implicitWidth + 2 * AppConfig.labelPreviewPlatePadding
        height: cellGrid.implicitHeight + 2 * AppConfig.labelPreviewPlatePadding
        radius: root.settings.cornerRadius
        color: Qt.rgba(root.settings.backgroundColor.r,
                       root.settings.backgroundColor.g,
                       root.settings.backgroundColor.b,
                       root.settings.backgroundOpacity / 100)
        border.width: root.settings.borderThickness
        border.color: root.settings.borderColor

    Grid {
        id: cellGrid
        anchors.centerIn: parent
        columns: root.label.columns
        rows: root.label.rows
        columnSpacing: AppConfig.labelPreviewCellSpacing
        rowSpacing: AppConfig.labelPreviewCellSpacing

        Repeater {
            id: slotRepeater
            model: root.label.matrix

            delegate: Rectangle {
                id: slotRect

                required property int index
                required property string path
                required property string keyText
                required property string valueText
                required property bool occupied
                required property bool custom
                required property bool omitted

                property bool editing: false

                function startEdit() {
                    if (!root.interactive) {
                        return
                    }
                    if (occupied && !custom) {
                        return  // metadata cells belong to the tree
                    }
                    editing = true
                }

                // A drop landing in the slot mid-edit means the text
                // field is now covering someone else's cell — cancel.
                onOccupiedChanged: {
                    if (editing && occupied && !custom) {
                        editing = false
                    }
                }

                width: root._cellWidth
                height: AppConfig.labelPreviewCellHeight
                radius: 2
                // The grid lines: every cell boundary visible, Excel-
                // style, whether or not the cell holds anything.
                color: slotDrop.containsDrag
                       ? Qt.alpha(AppConfig.universalAccent, 0.25)
                       : "transparent"
                border.color: slotDrop.containsDrag
                              ? AppConfig.universalAccent
                              : AppConfig.containerIdleBorder
                border.width: 1

                DropArea {
                    id: slotDrop
                    anchors.fill: parent
                    keys: ["tfs-label-cell"]
                    onDropped: (drop) => {
                        root.label.moveCell(drop.source.slotIndex,
                                            slotRect.index)
                        drop.accept()
                    }
                }

                // Empty cells: click releases focus (the cell is not a
                // control), double-click starts a custom-text note.
                MouseArea {
                    id: emptyArea
                    anchors.fill: parent
                    enabled: !slotRect.occupied && !slotRect.editing
                    hoverEnabled: true
                    onClicked: root.forceActiveFocus()
                    onDoubleClicked: slotRect.startEdit()

                    ToolTip.text: Strings.customCellEmptyTooltip
                    ToolTip.visible: containsMouse && root.interactive
                    ToolTip.delay: AppConfig.toolTipDelayMs
                    ToolTip.timeout: AppConfig.toolTipTimeoutMs
                }

                // The draggable occupant. Anchor-free so only the
                // ParentChange runs when a drag lifts it out.
                Item {
                    id: chip
                    width: slotRect.width
                    height: slotRect.height
                    visible: slotRect.occupied && !slotRect.editing

                    readonly property int slotIndex: slotRect.index
                    readonly property bool dragging: chipArea.drag.active

                    // Centre outside the plate while dragging = the
                    // drop would delete. Depends on chip.x/y so it
                    // tracks the drag live (mapToItem would not).
                    readonly property bool wouldDelete:
                        dragging && !root._insidePlate(chip.x + chip.width / 2,
                                                       chip.y + chip.height / 2)

                    Drag.active: chip.dragging
                    Drag.source: chip
                    Drag.keys: ["tfs-label-cell"]
                    Drag.hotSpot.x: width / 2
                    Drag.hotSpot.y: height / 2

                    // Dim while dragging; dim hard when the release
                    // would delete, so the gesture telegraphs itself.
                    opacity: dragging ? (wouldDelete ? 0.35 : 0.7) : 1.0
                    states: State {
                        when: chip.dragging
                        ParentChange { target: chip; parent: root }
                    }
                    onDraggingChanged: {
                        if (!dragging) {
                            // The drop (if any) has been delivered by
                            // Drag.drop() in onReleased; park the chip
                            // back in its slot once the state reverts.
                            Qt.callLater(function () {
                                chip.x = 0
                                chip.y = 0
                            })
                        }
                    }

                    // Ghosted state: this image's label will omit the
                    // cell (field absent + Omit policy). The dim rides
                    // the metadata texts, never the chip opacity (that
                    // line belongs to the drag gesture) — the slot, its
                    // border and the drag stay fully live, because the
                    // arrangement is batch-wide.
                    HoverHandler {
                        id: omittedHover
                        enabled: slotRect.omitted
                    }
                    ToolTip.text: Strings.cellOmittedTooltip
                    ToolTip.visible: omittedHover.hovered && !chip.dragging
                    ToolTip.delay: AppConfig.toolTipDelayMs
                    ToolTip.timeout: AppConfig.toolTipTimeoutMs

                    // Metadata cells: key and value halves, aligned per
                    // the settings, separator suffix included — the
                    // same text the output renders.
                    Text {
                        visible: !slotRect.custom
                        opacity: slotRect.omitted
                                 ? AppConfig.labelPreviewCellOmittedOpacity
                                 : 1.0
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.leftMargin: AppConfig.labelPreviewCellSpacing
                        width: (parent.width
                                - 2 * AppConfig.labelPreviewCellSpacing) / 2
                        verticalAlignment: Text.AlignVCenter
                        horizontalAlignment:
                            root._hAlign[root.settings.keyAlignment]
                        text: slotRect.occupied
                              ? slotRect.keyText
                                + root.settings.keySeparatorSuffix
                              : ""
                        elide: Text.ElideRight
                        font.family: root.settings.fontFamily
                        // No image to scale against in the editor; cap
                        // so a 200 px setting cannot explode the cell.
                        font.pixelSize: Math.min(root.settings.fontSize,
                                                 AppConfig.labelPreviewFontSizeCap)
                        color: root.settings.fontColor
                    }

                    Text {
                        visible: !slotRect.custom
                        opacity: slotRect.omitted
                                 ? AppConfig.labelPreviewCellOmittedOpacity
                                 : 1.0
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        anchors.rightMargin: AppConfig.labelPreviewCellSpacing
                        width: (parent.width
                                - 2 * AppConfig.labelPreviewCellSpacing) / 2
                        verticalAlignment: Text.AlignVCenter
                        horizontalAlignment:
                            root._hAlign[root.settings.valueAlignment]
                        text: slotRect.occupied ? slotRect.valueText : ""
                        elide: Text.ElideRight
                        font.family: root.settings.fontFamily
                        font.pixelSize: Math.min(root.settings.fontSize,
                                                 AppConfig.labelPreviewFontSizeCap)
                        color: root.settings.fontColor
                    }

                    // Custom cells: one text spanning the whole cell,
                    // exactly as the output renders it.
                    Text {
                        visible: slotRect.custom
                        anchors.fill: parent
                        anchors.leftMargin: AppConfig.labelPreviewCellSpacing
                        anchors.rightMargin: AppConfig.labelPreviewCellSpacing
                        verticalAlignment: Text.AlignVCenter
                        text: slotRect.custom ? slotRect.valueText : ""
                        elide: Text.ElideRight
                        font.family: root.settings.fontFamily
                        font.pixelSize: Math.min(root.settings.fontSize,
                                                 AppConfig.labelPreviewFontSizeCap)
                        color: root.settings.fontColor
                    }

                    MouseArea {
                        id: chipArea
                        anchors.fill: parent
                        enabled: root.interactive && slotRect.occupied
                                 && !slotRect.editing
                        hoverEnabled: true
                        drag.target: chip
                        // The chip grabs the press, so the backing
                        // focus MouseAreas never see it — release the
                        // spin box here.
                        onPressed: root.forceActiveFocus()
                        onDoubleClicked: {
                            if (slotRect.custom) {
                                slotRect.startEdit()
                            }
                        }
                        onReleased: {
                            // Deliver the drop first: an accepted drop
                            // is a move/swap. Ignored + outside the
                            // plate is the delete gesture; ignored +
                            // inside (between cells) snaps back.
                            const action = chip.Drag.drop()
                            if (action === Qt.IgnoreAction
                                    && chip.wouldDelete) {
                                root.label.removeCell(chip.slotIndex)
                            }
                        }
                        cursorShape: !enabled
                                     ? Qt.ArrowCursor
                                     : (pressed ? Qt.ClosedHandCursor
                                                : Qt.OpenHandCursor)

                        ToolTip.text: Strings.customCellEditTooltip
                        ToolTip.visible: containsMouse && slotRect.custom
                                         && !chip.dragging
                                         && root.interactive
                        ToolTip.delay: AppConfig.toolTipDelayMs
                        ToolTip.timeout: AppConfig.toolTipTimeoutMs
                    }
                }

                // The inline custom-text editor, alive only while
                // editing. Commit on Enter or focus-out; Escape
                // cancels; committing empty text removes the cell.
                Loader {
                    id: editorLoader
                    anchors.fill: parent
                    active: slotRect.editing
                    sourceComponent: TextField {
                        property bool cancelled: false

                        function commitNow() {
                            if (!slotRect.editing) {
                                return
                            }
                            root.label.setCustomText(slotRect.index, text)
                            slotRect.editing = false
                        }

                        text: slotRect.custom ? slotRect.valueText : ""
                        placeholderText: Strings.customCellPlaceholder
                        font.family: root.settings.fontFamily
                        font.pixelSize: Math.min(root.settings.fontSize,
                                                 AppConfig.labelPreviewFontSizeCap)
                        Component.onCompleted: {
                            forceActiveFocus()
                            selectAll()
                        }
                        Keys.onReturnPressed: focus = false
                        Keys.onEnterPressed: focus = false
                        Keys.onEscapePressed: {
                            cancelled = true
                            focus = false
                        }
                        onActiveFocusChanged: {
                            // Enter, clicking anywhere else, Tab — all
                            // land here; Escape marked itself first.
                            if (!activeFocus) {
                                if (cancelled) {
                                    slotRect.editing = false
                                } else {
                                    commitNow()
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    }

    // The batch cycler, pinned to the reserved strip at the card's
    // bottom so it never chases the plate around as the grid resizes.
    // A chip dropped on it deletes the cell — that is the normal
    // outside-the-plate gesture, unchanged.
    BatchNavRow {
        id: navRow
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        visible: root.images.count > 1 && !root.images.isParsing
        interactive: root.interactive
        fileListModel: root.images.fileModel
        currentIndex: root.images.currentImageIndex
        count: root.images.count
        onPreviousClicked: root.images.previousImage()
        onNextClicked: root.images.nextImage()
        onJumpRequested: (index) => root.images.setCurrentImage(index)
    }

}
