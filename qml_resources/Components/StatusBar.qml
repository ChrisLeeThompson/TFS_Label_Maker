import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Config"

// Three-slot status bar:
//   • Left:   transient message (auto-clears via showMessage).
//   • Center: progress bar, shown when busy.
//   • Right:  Stop / Start button row.
//
// The persistent state indicator the sibling apps carry on the right has
// been replaced by the button row, so this bar is taller than theirs.

Rectangle {

    id: root

    // --- Public state ---
    property string message: ""            // Transient (left).
    property real progress: 0
    property bool indeterminate: false
    property bool busy: false
    property bool loadEnabled: true
    property bool clearEnabled: false
    property bool startEnabled: false
    property bool stopEnabled: false

    // --- Public signals ---
    signal loadClicked()
    signal clearClicked()
    signal startClicked()
    signal stopClicked()

    // --- Public API (transient messages only) ---
    function showMessage(text, durationMs) {
        message = text
        messageTimer.interval = durationMs
        messageTimer.restart()
    }

    function clearMessage() {
        messageTimer.stop()
        message = ""
    }

    // --- Internal ---
    Timer {
        id: messageTimer
        repeat: false
        onTriggered: root.message = ""
    }

    color: AppConfig.universalBackground
    implicitHeight: AppConfig.statusBarHeight

    RowLayout {

        anchors.fill: parent
        anchors.leftMargin: AppConfig.statusBarHorizontalMargin
        anchors.rightMargin: AppConfig.statusBarHorizontalMargin
        spacing: AppConfig.statusBarButtonSpacing

        // Left — transient
        Label {
            id: transientLabel
            text: root.message
            font.pixelSize: AppConfig.statusBarLabelFontSize
            Layout.fillWidth: true
            Layout.preferredWidth: 0
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignLeft
        }

        // Center — progress.
        //
        // Collapses to zero width when idle rather than merely fading:
        // an invisible bar reserving 300 px left only ~216 px for the
        // message at the minimum window width, which elided the opening
        // instruction. Giving the space back when there is no progress
        // to show is what makes a full-sentence message fit.
        ProgressBar {
            id: statusBarProgressBar
            Layout.preferredWidth: root.busy ? AppConfig.statusBarProgressWidth : 0
            Layout.alignment: Qt.AlignHCenter
            opacity: root.busy ? 1 : 0
            value: root.progress
            indeterminate: root.indeterminate
            Behavior on Layout.preferredWidth {
                NumberAnimation { duration: 150; easing.type: Easing.OutQuad }
            }
            Behavior on opacity { NumberAnimation { duration: 150 } }
            Behavior on value { NumberAnimation { duration: 0 } }
        }

        // Right — Load / Clear / Stop / Start
        RowLayout {
            id: buttonRow
            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
            spacing: AppConfig.statusBarButtonSpacing

            RoundButton {
                id: loadButton
                text: Strings.loadButtonText
                radius: AppConfig.buttonRadius
                padding: AppConfig.statusBarButtonPadding
                enabled: root.loadEnabled
                onClicked: root.loadClicked()

                ToolTip.text: Strings.loadButtonTooltip
                ToolTip.visible: hovered
                ToolTip.delay: AppConfig.toolTipDelayMs
                ToolTip.timeout: AppConfig.toolTipTimeoutMs
            }

            RoundButton {
                id: clearButton
                text: Strings.clearButtonText
                radius: AppConfig.buttonRadius
                padding: AppConfig.statusBarButtonPadding
                enabled: root.clearEnabled
                onClicked: root.clearClicked()

                ToolTip.text: Strings.clearButtonTooltip
                ToolTip.visible: hovered
                ToolTip.delay: AppConfig.toolTipDelayMs
                ToolTip.timeout: AppConfig.toolTipTimeoutMs
            }

            RoundButton {
                id: stopButton
                text: Strings.stopButtonText
                radius: AppConfig.buttonRadius
                padding: AppConfig.statusBarButtonPadding
                enabled: root.stopEnabled
                onClicked: root.stopClicked()

                ToolTip.text: Strings.stopButtonTooltip
                ToolTip.visible: hovered
                ToolTip.delay: AppConfig.toolTipDelayMs
                ToolTip.timeout: AppConfig.toolTipTimeoutMs
            }

            RoundButton {
                id: startButton
                text: Strings.startButtonText
                radius: AppConfig.buttonRadius
                padding: AppConfig.statusBarButtonPadding
                enabled: root.startEnabled
                onClicked: root.startClicked()

                ToolTip.text: Strings.startButtonTooltip
                ToolTip.visible: hovered
                ToolTip.delay: AppConfig.toolTipDelayMs
                ToolTip.timeout: AppConfig.toolTipTimeoutMs
            }
        }

    }

}
