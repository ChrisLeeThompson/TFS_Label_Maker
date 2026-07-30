import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Config"

// Previous | filename | Next — the batch cycler under the label plate.
// Dumb component: properties in, signals out; the images controller
// stays with the caller (StatusBar's pattern). The "2 / 11" position
// readout lives in the card's title band (Card.headerText), not here,
// so the ComboBox centres vertically with the buttons.
//
// The filename is a ComboBox so a large batch can jump straight to any
// image instead of click-stepping; the buttons disable at the ends
// (CustomSpinBox's convention) rather than wrapping — mid-comparison,
// an 11 -> 1 jump reads as a glitch, and the dropdown already covers
// "get back to the start fast".
RowLayout {

    id: root

    // --- Public state ---
    property var fileListModel
    property int currentIndex: 0
    property int count: 0
    property bool interactive: true

    // --- Public signals ---
    signal previousClicked()
    signal nextClicked()
    signal jumpRequested(int index)

    spacing: AppConfig.statusBarButtonSpacing

    RoundButton {
        text: Strings.batchNavPreviousText
        radius: AppConfig.buttonRadius
        padding: AppConfig.statusBarButtonPadding
        enabled: root.interactive && root.currentIndex > 0
        onClicked: root.previousClicked()

        ToolTip.text: Strings.batchNavPreviousTooltip
        ToolTip.visible: hovered
        ToolTip.delay: AppConfig.toolTipDelayMs
        ToolTip.timeout: AppConfig.toolTipTimeoutMs
    }

    ComboBox {
        id: fileCombo
        // Full width between the buttons: TFS filenames encode the
        // acquisition parameters, so the wider the readout the more
        // of them survive un-elided (explicit user preference).
        Layout.fillWidth: true
        model: root.fileListModel
        textRole: "fileName"
        enabled: root.interactive
        onActivated: (index) => root.jumpRequested(index)

        // No declarative currentIndex binding: a user selection
        // would break it, and Prev/Next drive this from outside
        // constantly — sync by hand in both directions instead.
        Component.onCompleted: currentIndex = root.currentIndex

        ToolTip.text: Strings.batchNavFileTooltip
        ToolTip.visible: hovered
        ToolTip.delay: AppConfig.toolTipDelayMs
        ToolTip.timeout: AppConfig.toolTipTimeoutMs
    }

    Connections {
        target: root
        function onCurrentIndexChanged() {
            fileCombo.currentIndex = root.currentIndex
        }
    }

    RoundButton {
        text: Strings.batchNavNextText
        radius: AppConfig.buttonRadius
        padding: AppConfig.statusBarButtonPadding
        enabled: root.interactive && root.currentIndex < root.count - 1
        onClicked: root.nextClicked()

        ToolTip.text: Strings.batchNavNextTooltip
        ToolTip.visible: hovered
        ToolTip.delay: AppConfig.toolTipDelayMs
        ToolTip.timeout: AppConfig.toolTipTimeoutMs
    }

}
