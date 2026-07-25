import QtCore
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Universal
import QtQuick.Layouts
import "../Config"

// Search row plus the checkable tree of metadata fields common to every
// loaded image. Fills a Card's content area; the Card owns the frame
// and title, so nothing here draws chrome.
//
// Check state and the capacity cap live on the source model
// (fieldsModel); the view shows the search proxy (treeModel). Checks
// travel as dotted path strings, never as model indexes — indexes do
// not survive the model reset that follows every parse, paths do.
Item {

    id: root

    // --- Public state ---
    required property var fieldsModel
    required property var treeModel

    // Divider between the key and value columns, as a fraction of row
    // width. Draggable — the reference explorers had user-resizable
    // columns — and persisted so it is set once, not per session.
    readonly property real keyColumnRatio: treeSettings.treeKeyColumnRatio

    function setDividerRatio(ratio) {
        treeSettings.treeKeyColumnRatio = Math.max(
            AppConfig.treeKeyColumnRatioMin,
            Math.min(AppConfig.treeKeyColumnRatioMax, ratio))
    }

    // --- Internal ---
    Settings {
        id: treeSettings
        category: "v1"
        property real treeKeyColumnRatio: AppConfig.treeKeyColumnRatio
    }

    // ATC Project Explorer behaviour: matches are always shown expanded;
    // with no search active, the Expand all toggle decides wholesale.
    // Expansion state is reset, not restored, when the search clears —
    // same simplification as the reference implementations.
    function _applyExpandState() {
        if (searchField.text.trim().length > 0 || expandAllCheck.checked) {
            treeView.expandRecursively()
        } else {
            treeView.collapseRecursively()
        }
    }

    ColumnLayout {

        anchors.fill: parent
        spacing: AppConfig.formRowSpacing

        RowLayout {
            Layout.fillWidth: true
            spacing: AppConfig.formColumnSpacing

            TextField {
                id: searchField
                Layout.fillWidth: true
                placeholderText: Strings.treeSearchPlaceholder
                placeholderTextColor: AppConfig.placeholderTextColor
                // The Universal style's focus colours are near-black on
                // this palette; pin them, as CustomSpinBox does.
                color: AppConfig.universalForeground
                selectionColor: AppConfig.universalAccent
                selectedTextColor: AppConfig.universalBackground
                onTextChanged: {
                    root.treeModel.searchText = text
                    root._applyExpandState()
                }
                Keys.onReturnPressed: root.forceActiveFocus()
                Keys.onEnterPressed: root.forceActiveFocus()
                Keys.onEscapePressed: {
                    if (text === "") {
                        root.forceActiveFocus()
                    } else {
                        text = ""
                    }
                }
                ToolTip.text: Strings.treeSearchTooltip
                ToolTip.visible: hovered
                ToolTip.delay: AppConfig.toolTipDelayMs
                ToolTip.timeout: AppConfig.toolTipTimeoutMs
            }

            CheckBox {
                id: expandAllCheck
                text: Strings.treeExpandAllText
                checked: true
                onToggled: root._applyExpandState()
                ToolTip.text: Strings.treeExpandAllTooltip
                ToolTip.visible: hovered
                ToolTip.delay: AppConfig.toolTipDelayMs
                ToolTip.timeout: AppConfig.toolTipTimeoutMs
            }

            Button {
                id: deselectAllButton
                text: Strings.treeDeselectAllText
                padding: AppConfig.statusBarButtonPadding
                enabled: root.fieldsModel.checkedCount > 0
                onClicked: root.fieldsModel.clearChecks()
                ToolTip.text: Strings.treeDeselectAllTooltip
                ToolTip.visible: hovered
                ToolTip.delay: AppConfig.toolTipDelayMs
                ToolTip.timeout: AppConfig.toolTipTimeoutMs
            }
        }

        Item {
            id: treeContainer
            Layout.fillWidth: true
            Layout.fillHeight: true

            // The width rows actually occupy: the delegates are sized by
            // columnWidthProvider, which subtracts the scrollbar. The
            // divider handle must live in the SAME geometry or its line
            // drifts scrollbarWidth * ratio pixels off the real split.
            readonly property real rowWidth:
                width - (vScroll.visible ? vScroll.width : 0)

            TreeView {
                id: treeView
                anchors.fill: parent
                clip: true
                model: root.treeModel
                boundsBehavior: Flickable.StopAtBounds
                // Checkbox state is re-bound by hand in the delegate;
                // pooled reuse would make that dance harder to reason
                // about for no gain at a few hundred rows.
                reuseItems: false
                // Single column spanning the view minus the scrollbar
                // (rows that run underneath it get the right edge of
                // their value text covered). Returning 0 would *hide*
                // the column, so fall back to implicit sizing until the
                // layout has given the view a real width.
                columnWidthProvider: function (column) {
                    var w = treeView.width
                            - (vScroll.visible ? vScroll.width : 0)
                    return w > 0 ? w : -1
                }
                onWidthChanged: forceLayout()
                ScrollBar.vertical: ScrollBar {
                    id: vScroll
                    policy: ScrollBar.AsNeeded
                    onVisibleChanged: treeView.forceLayout()
                }

                // A finished parse resets the model and TreeView drops
                // all expansion; re-apply once the new rows exist.
                Connections {
                    target: root.treeModel
                    function onModelReset() {
                        Qt.callLater(root._applyExpandState)
                    }
                }

                // The view is a Flickable: it consumes presses on empty
                // space, so the card's backing MouseArea never sees
                // them. A TapHandler fires on stationary taps only —
                // flicking and the delegates' own controls are
                // untouched — and releases spin-box focus.
                TapHandler {
                    onTapped: root.forceActiveFocus()
                }

                delegate: Rectangle {

                    id: delegateRoot

                    required property TreeView treeView
                    required property bool isTreeNode
                    required property bool expanded
                    required property bool hasChildren
                    required property int depth
                    required property int row
                    required property var model

                    readonly property bool isGroupRow: depth === 0
                    readonly property real dividerX: width * root.keyColumnRatio

                    implicitHeight: AppConfig.treeRowHeight
                    color: rowHover.hovered ? delegateRoot.Universal.baseLowColor
                                            : "transparent"

                    HoverHandler { id: rowHover }

                    // Anywhere on a branch row toggles it; the checkbox
                    // on value rows accepts its own clicks before this
                    // sees them. A row is not a focusable control, so
                    // the tap also releases whatever spin box had focus.
                    TapHandler {
                        enabled: delegateRoot.hasChildren
                        onTapped: {
                            root.forceActiveFocus()
                            delegateRoot.treeView.toggleExpanded(delegateRoot.row)
                        }
                    }

                    // The chevron artwork is taller than wide (8.19 ×
                    // 14.68 mm); rasterise by height only so the SVG
                    // keeps its aspect instead of being squashed into a
                    // square, and fit it inside the square slot.
                    Image {
                        id: chevron
                        x: delegateRoot.depth * AppConfig.treeIndentWidth
                        width: AppConfig.treeChevronSize
                        height: AppConfig.treeChevronSize
                        anchors.verticalCenter: parent.verticalCenter
                        source: AppConfig.iconChevronRight
                        fillMode: Image.PreserveAspectFit
                        sourceSize.height: 2 * AppConfig.treeChevronSize
                        visible: delegateRoot.hasChildren
                        rotation: delegateRoot.expanded ? 90 : 0
                        Behavior on rotation {
                            NumberAnimation {
                                duration: AppConfig.treeChevronRotateDurationMs
                            }
                        }
                    }

                    CheckBox {
                        id: check
                        x: chevron.x + AppConfig.treeChevronSize
                           + AppConfig.treeCellSpacing
                        anchors.verticalCenter: parent.verticalCenter
                        padding: 0
                        visible: delegateRoot.model.isLeaf === true
                        checked: delegateRoot.model.checked === true
                        onToggled: {
                            root.fieldsModel.setChecked(delegateRoot.model.path,
                                                        checked)
                            // The click broke the declarative binding;
                            // re-establish it so a refused 13th check
                            // (the model kept it false) snaps back
                            // visually.
                            checked = Qt.binding(function () {
                                return delegateRoot.model.checked === true
                            })
                        }
                    }

                    Label {
                        id: keyLabel
                        x: check.visible
                           ? check.x + check.width + AppConfig.treeCellSpacing
                           : chevron.x + AppConfig.treeChevronSize
                             + AppConfig.treeCellSpacing
                        width: Math.max(0, delegateRoot.dividerX - x
                                           - AppConfig.treeCellSpacing)
                        anchors.verticalCenter: parent.verticalCenter
                        text: delegateRoot.model.display
                        elide: Text.ElideRight
                        font.pixelSize: AppConfig.pageBodyFontSize
                        font.bold: delegateRoot.isGroupRow
                        color: AppConfig.universalForeground
                    }

                    Label {
                        id: valueLabel
                        // Offset from the divider by the same spacing the
                        // key column keeps on its side, so the draggable
                        // separator line never touches either text.
                        x: delegateRoot.dividerX + AppConfig.treeCellSpacing
                        width: Math.max(0, delegateRoot.width
                                           - AppConfig.treeCellSpacing - x)
                        anchors.verticalCenter: parent.verticalCenter
                        text: delegateRoot.model.value
                        elide: Text.ElideRight
                        font.pixelSize: AppConfig.pageBodyFontSize
                        color: AppConfig.universalForeground
                    }
                }
            }

            // Drag to move the key/value divider, like the resizable
            // columns in the reference explorers. Sits above the rows;
            // its thin line is the only visible trace.
            Item {
                id: dividerHandle
                z: 2
                width: AppConfig.treeDividerHitWidth
                height: parent.height
                x: treeContainer.rowWidth * root.keyColumnRatio - width / 2
                visible: treeView.rows > 0

                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 1
                    height: parent.height
                    color: dividerArea.pressed || dividerArea.containsMouse
                           ? AppConfig.universalAccent
                           : AppConfig.containerIdleBorder
                }

                MouseArea {
                    id: dividerArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.SplitHCursor
                    // The divider grabs its press, so the backing focus
                    // areas never see it — release the spin box here.
                    onPressed: root.forceActiveFocus()
                    onPositionChanged: (mouse) => {
                        if (pressed && treeContainer.rowWidth > 0) {
                            var inContainer = dividerArea.mapToItem(
                                treeContainer, mouse.x, 0)
                            root.setDividerRatio(
                                inContainer.x / treeContainer.rowWidth)
                        }
                    }
                }
            }
        }
    }

}
