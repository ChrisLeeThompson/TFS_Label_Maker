import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "../Config"

// Colour picker: a swatch button that opens a popup of curated presets,
// a hex field, a contrast strip, and a full dialog as an escape hatch.
//
// Alpha is deliberately absent — background opacity is its own spin box,
// so all three pickers in this app are RGB-only. That removes the main
// reason to build a full HSV+alpha widget.
//
// The contrast strip is the one thing no stock dialog offers: a
// black-to-white ramp is the tonal range of a greyscale micrograph, so
// drawing the candidate colour across it answers "will this disappear
// somewhere on my image?" directly.
//
// Binding contract is one-way in, signal out. Bind `selectedColor` to the
// setting and assign in `onColorPicked`; do not two-way bind, or the
// popup will fight the settings controller.

Item {

    id: root

    property color selectedColor: "#ffffff"
    property string toolTipText: ""

    // When > -1 the swatch and strip composite at this opacity, so the
    // background picker shows what the user will actually get.
    property int previewOpacityPercent: -1

    signal colorPicked(color picked)

    readonly property real _alpha: previewOpacityPercent < 0
                                   ? 1.0
                                   : previewOpacityPercent / 100.0

    readonly property var presets: [
        // Greys — the workhorses for label plates on a micrograph.
        "#ffffff", "#d0d0d0", "#a0a0a0", "#707070", "#383838", "#000000",
        // Saturated hues that stay legible against mid greys.
        "#ff3b30", "#ff9500", "#ffcc00", "#33ff33", "#2ea2ec", "#af52de",
        // Deeper variants for light backgrounds.
        "#b71c1c", "#e65100", "#f9a825", "#1b7d1b", "#1565c0", "#6a1b9a"
    ]

    implicitWidth: 120
    implicitHeight: 28

    function open() {
        pickerPopup.open()
    }

    function _emit(c) {
        root.colorPicked(c)
    }

    // --- The button -------------------------------------------------------

    Rectangle {
        id: swatchButton
        anchors.fill: parent
        radius: AppConfig.buttonRadius
        color: "transparent"
        border.width: AppConfig.containerBorderWidth
        border.color: buttonHover.hovered ? AppConfig.universalAccent
                                          : AppConfig.containerIdleBorder

        Behavior on border.color {
            ColorAnimation { duration: AppConfig.dropZoneHoverDurationMs }
        }

        RowLayout {
            anchors.fill: parent
            anchors.margins: 4
            spacing: 6

            // Chequerboard behind the swatch so a translucent colour
            // reads as translucent rather than as a darker solid.
            Item {
                Layout.preferredWidth: AppConfig.colorSwatchSize
                Layout.fillHeight: true

                Rectangle {
                    anchors.fill: parent
                    radius: 2
                    color: "#ffffff"
                }
                Grid {
                    anchors.fill: parent
                    columns: 4
                    clip: true
                    Repeater {
                        model: 16
                        Rectangle {
                            width: parent.width / 4
                            height: parent.height / 4
                            color: ((index % 4) + Math.floor(index / 4)) % 2 === 0
                                   ? "#ffffff" : "#c0c0c0"
                        }
                    }
                }
                Rectangle {
                    anchors.fill: parent
                    radius: 2
                    color: root.selectedColor
                    opacity: root._alpha
                    border.width: 1
                    border.color: AppConfig.containerIdleBorder
                }
            }

            Label {
                Layout.fillWidth: true
                text: root.selectedColor.toString().toUpperCase()
                font.pixelSize: AppConfig.pageBodyFontSize - 2
                color: AppConfig.universalForeground
                elide: Text.ElideRight
            }
        }

        HoverHandler { id: buttonHover }
        TapHandler {
            onTapped: {
                // Release the spin box FIRST: the popup grabs focus and
                // restores it on close, and it must not restore into a
                // half-edited spin box.
                root.forceActiveFocus()
                root.open()
            }
        }
    }

    ToolTip.text: root.toolTipText
    ToolTip.visible: root.toolTipText !== "" && buttonHover.hovered
                     && !pickerPopup.opened
    ToolTip.delay: AppConfig.toolTipDelayMs
    ToolTip.timeout: AppConfig.toolTipTimeoutMs

    // --- The popup --------------------------------------------------------

    Popup {
        id: pickerPopup
        y: root.height + 4
        width: AppConfig.colorPickerPopupWidth
        padding: AppConfig.pageMargin
        modal: false
        focus: true
        // CloseOnPressOutside, not CloseOnPressOutsideParent: the popup
        // is positioned below its parent and so lies outside the parent's
        // bounds, which would make every click inside the popup dismiss it.
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            color: AppConfig.containerBackground
            border.color: AppConfig.containerIdleBorder
            border.width: AppConfig.containerBorderWidth
            radius: AppConfig.containerBorderRadius
        }

        ColumnLayout {
            spacing: AppConfig.formRowSpacing

            // Preset grid
            Grid {
                id: swatchGrid
                columns: AppConfig.colorPickerColumns
                spacing: AppConfig.colorSwatchSpacing

                Repeater {
                    model: root.presets

                    Rectangle {
                        required property string modelData

                        width: AppConfig.colorSwatchSize
                        height: AppConfig.colorSwatchSize
                        radius: 3
                        color: modelData
                        border.width: root.selectedColor.toString().toLowerCase()
                                      === modelData.toLowerCase() ? 2 : 1
                        border.color: root.selectedColor.toString().toLowerCase()
                                      === modelData.toLowerCase()
                                      ? AppConfig.universalAccent
                                      : AppConfig.containerIdleBorder

                        HoverHandler { id: swatchHover }
                        // Deliberately does NOT close the popup: the whole
                        // point of the contrast strip is to judge the
                        // colour after picking it, which is impossible if
                        // selecting dismisses the strip.
                        TapHandler {
                            onTapped: {
                                root._emit(parent.modelData)
                                // Keep the hex field honest (programmatic
                                // set: does not mark it dirty).
                                hexField.text = parent.modelData
                            }
                        }

                        Rectangle {
                            anchors.fill: parent
                            anchors.margins: -3
                            visible: swatchHover.hovered
                            color: "transparent"
                            radius: 3
                            border.width: 1
                            border.color: AppConfig.universalAccent
                        }
                    }
                }
            }

            // Contrast strip — the candidate colour over a black-to-white
            // ramp, i.e. the tonal range of a greyscale micrograph.
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: AppConfig.contrastStripHeight

                Rectangle {
                    anchors.fill: parent
                    radius: 2
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: "#000000" }
                        GradientStop { position: 1.0; color: "#ffffff" }
                    }
                }

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 4
                    radius: 2
                    color: root.selectedColor
                    opacity: root._alpha
                    visible: root.previewOpacityPercent >= 0
                }

                Label {
                    anchors.centerIn: parent
                    text: "1.00 kV   25 pA   19.3 µm"
                    font.pixelSize: AppConfig.pageBodyFontSize - 3
                    color: root.selectedColor
                    visible: root.previewOpacityPercent < 0
                }

                HoverHandler { id: stripHover }
                ToolTip.text: Strings.colorPickerContrastTooltip
                ToolTip.visible: stripHover.hovered
                ToolTip.delay: AppConfig.toolTipDelayMs
                ToolTip.timeout: AppConfig.toolTipTimeoutMs
            }

            // Hex entry
            RowLayout {
                Layout.fillWidth: true
                spacing: AppConfig.formRowSpacing

                Label {
                    text: Strings.colorPickerHexLabel
                    font.pixelSize: AppConfig.pageBodyFontSize - 2
                }

                TextField {
                    id: hexField
                    Layout.fillWidth: true
                    font.pixelSize: AppConfig.pageBodyFontSize - 2
                    placeholderText: "#RRGGBB"

                    // True only while the field holds USER-typed text
                    // that has not been committed. Done consults this:
                    // committing an untouched (seeded or swatch-set)
                    // field would re-emit a stale colour and silently
                    // revert a swatch choice.
                    property bool dirty: false
                    onTextEdited: dirty = true

                    // One commit path for BOTH Enter and the Done
                    // button — typed hex must not need an Enter press
                    // before Done, or Done silently discards it.
                    function commit() {
                        var candidate = text.trim()
                        if (!candidate.startsWith("#")) {
                            candidate = "#" + candidate
                        }
                        if (/^#[0-9a-fA-F]{6}$/.test(candidate)
                                || /^#[0-9a-fA-F]{8}$/.test(candidate)) {
                            root._emit(candidate)
                        } else {
                            text = root.selectedColor.toString()
                        }
                        dirty = false
                    }

                    // Seeded on open rather than bound, so typing is not
                    // clobbered by the selectedColor notification.
                    onAccepted: commit()
                }
            }

            // Escape hatch + explicit dismiss. Since selecting a colour no
            // longer closes the popup, Done gives an obvious way out
            // alongside clicking outside or pressing Escape.
            RowLayout {
                Layout.fillWidth: true
                spacing: AppConfig.formRowSpacing

                Button {
                    text: Strings.colorPickerMoreText
                    padding: AppConfig.statusBarButtonPadding
                    onClicked: {
                        fullDialog.selectedColor = root.selectedColor
                        fullDialog.open()
                    }
                }

                Item { Layout.fillWidth: true }

                Button {
                    text: Strings.colorPickerDoneText
                    padding: AppConfig.statusBarButtonPadding
                    onClicked: {
                        // Adopt hex the user typed but never Enter-
                        // committed — Done must not discard it. An
                        // untouched field is left alone (see dirty).
                        if (hexField.dirty) {
                            hexField.commit()
                        }
                        pickerPopup.close()
                    }
                }
            }
        }

        onOpened: hexField.text = root.selectedColor.toString()
    }

    // Qt 6's QtQuick implementation, not the native Win32 dialog, so it
    // renders in the Universal dark theme instead of flashing a light
    // window in the middle of a dark UI.
    ColorDialog {
        id: fullDialog
        options: ColorDialog.DontUseNativeDialog
        onAccepted: {
            root._emit(fullDialog.selectedColor)
            hexField.text = fullDialog.selectedColor.toString()
        }
    }

}
