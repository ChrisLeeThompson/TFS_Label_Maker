import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Config"

// The Output card's controls: what Start produces, and the PowerPoint
// send that can ride along (or, in PowerPoint only mode, be the output).
//
// Same binding contract as SettingsPanel: bind the control's value
// *from* the setting and write back in the interaction handler, never a
// two-way binding.
//
// Laid out as a single column (checkbox captions carry their own text)
// rather than the settings form's label|control grid — this card lives
// in the narrow right-hand column, where a two-column form would crush
// the labels.

Item {

    id: root

    required property var powerpoint
    required property var settings
    // UX-only gate: every value here is frozen into snapshots at
    // Start, so a mid-run edit could never touch the running job —
    // it would silently apply to the next run, which is exactly the
    // misleading feedback this gate prevents. No Python-side refusal
    // exists or is wanted: the snapshots are the load-bearing guard.
    property bool interactive: true

    implicitHeight: form.implicitHeight

    // Declared before the form so it sits underneath: clicks that miss
    // a control land here and release spin-box focus.
    MouseArea {
        anchors.fill: parent
        onClicked: root.forceActiveFocus()
    }

    ColumnLayout {
        id: form
        width: root.width
        spacing: AppConfig.formRowSpacing

        // --- What Start produces --------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: AppConfig.formRowSpacing

            ToolTippedLabel {
                text: Strings.outputLabel
                toolTipText: Strings.outputTooltip
            }

            Item { Layout.fillWidth: true }

            ComboBox {
                Layout.preferredWidth: AppConfig.comboBoxWidth
                enabled: root.interactive
                model: root.settings.outputNames
                currentIndex: root.settings.outputMode
                onActivated: (index) => root.settings.outputMode = index
            }
        }

        // --- Transition slide: enable + which template layout ---------
        RowLayout {
            Layout.fillWidth: true
            spacing: AppConfig.formRowSpacing

            CheckBox {
                id: transitionCheck
                text: Strings.pptTransitionLabel
                enabled: root.interactive
                checked: root.powerpoint.transitionSlideEnabled
                onToggled: root.powerpoint.transitionSlideEnabled = checked

                ToolTip.text: Strings.pptTransitionTooltip
                ToolTip.visible: hovered
                ToolTip.delay: AppConfig.toolTipDelayMs
                ToolTip.timeout: AppConfig.toolTipTimeoutMs
            }

            Item { Layout.fillWidth: true }

            CustomSpinBox {
                Layout.preferredWidth: AppConfig.pptSpinBoxWidth
                Layout.maximumWidth: AppConfig.pptSpinBoxWidth
                from: AppConfig.pptSlideIndexMin
                to: AppConfig.pptSlideIndexMax
                value: root.powerpoint.transitionSlideIndex
                enabled: root.interactive
                         && root.powerpoint.transitionSlideEnabled
                opacity: enabled ? 1.0 : 0.5
                onValueModified: root.powerpoint.transitionSlideIndex = value
            }
        }

        // --- Image slide layout ---------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: AppConfig.formRowSpacing

            ToolTippedLabel {
                text: Strings.pptImageSlideLabel
                toolTipText: Strings.pptImageSlideTooltip
            }

            Item { Layout.fillWidth: true }

            CustomSpinBox {
                Layout.preferredWidth: AppConfig.pptSpinBoxWidth
                Layout.maximumWidth: AppConfig.pptSpinBoxWidth
                from: AppConfig.pptSlideIndexMin
                to: AppConfig.pptSlideIndexMax
                value: root.powerpoint.imageSlideIndex
                // This spin box was never disabled before, so unlike
                // its transition sibling it needs the opacity idiom
                // added along with the gate (CustomSpinBox does not
                // dim itself).
                enabled: root.interactive
                opacity: enabled ? 1.0 : 0.5
                onValueModified: root.powerpoint.imageSlideIndex = value
            }
        }

        // --- Send, and what rides along -------------------------------
        CheckBox {
            id: sendCheck
            Layout.fillWidth: true
            text: Strings.pptSendLabel
            // PowerPoint only output is itself a send: shown checked and not
            // interactive, without writing the forced state into the
            // stored preference (it returns when the mode changes back).
            // Also disabled without Windows + pywin32; the tooltip says
            // why, and the controller refuses the value defensively too.
            enabled: root.interactive && root.powerpoint.available
                     && !root.settings.outputIsPptOnly
            checked: root.powerpoint.sendToActivePpt
                     || root.settings.outputIsPptOnly
            onToggled: {
                root.powerpoint.sendToActivePpt = checked
                // The click broke the declarative binding; re-establish
                // it so a later switch to PowerPoint Only still shows
                // the implied check.
                checked = Qt.binding(function () {
                    return root.powerpoint.sendToActivePpt
                           || root.settings.outputIsPptOnly
                })
            }

            ToolTip.text: !root.powerpoint.available
                          ? Strings.pptUnavailableTooltip
                          : root.settings.outputIsPptOnly
                            ? Strings.pptSendImpliedTooltip
                            : Strings.pptSendTooltip
            ToolTip.visible: hovered
            ToolTip.delay: AppConfig.toolTipDelayMs
            ToolTip.timeout: AppConfig.toolTipTimeoutMs
        }

        CheckBox {
            id: labelObjectCheck
            Layout.fillWidth: true
            Layout.leftMargin: AppConfig.formColumnSpacing  // reads as a child
            text: Strings.pptAddLabelObjectLabel
            // Enabled whenever a send will actually happen, however it
            // was requested — checkbox or PowerPoint Only mode.
            enabled: root.interactive && root.powerpoint.available
                     && (root.powerpoint.sendToActivePpt
                         || root.settings.outputIsPptOnly)
            opacity: enabled ? 1.0 : 0.5
            checked: root.powerpoint.addLabelObject
            onToggled: root.powerpoint.addLabelObject = checked

            ToolTip.text: Strings.pptAddLabelObjectTooltip
            ToolTip.visible: hovered
            ToolTip.delay: AppConfig.toolTipDelayMs
            ToolTip.timeout: AppConfig.toolTipTimeoutMs
        }
    }

}
