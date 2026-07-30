import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Config"

// Label styling controls. (Output selection lives on the Output card.)
//
// Binding contract throughout: bind the control's value *from* the
// setting and write back in the `...Modified` / `onActivated` handler.
// Two-way bindings would re-enter the settings setters on their own
// change notification; the setters guard against it, but the one-way-in,
// signal-out shape keeps the data flow obvious.

ScrollView {

    id: root

    required property var settings

    contentWidth: availableWidth
    clip: true

    // Strong focus so a click on empty panel space takes focus away from
    // whichever spin box or field had it. Without this an edited spin box
    // keeps focus (and its text cursor) until Tab or Enter, which makes
    // it ambiguous whether a typed value has been committed.
    focusPolicy: Qt.StrongFocus

    ScrollBar.vertical.policy: ScrollBar.AsNeeded

    Item {
        id: content
        width: root.availableWidth
        implicitWidth: root.availableWidth
        implicitHeight: form.implicitHeight
        height: form.implicitHeight

        // Declared before the form so it sits underneath: real controls
        // get the click first, and only clicks that miss them land here.
        MouseArea {
            anchors.fill: parent
            onClicked: root.forceActiveFocus()
        }

    GridLayout {
        id: form
        width: content.width
        columns: 2
        rowSpacing: AppConfig.formRowSpacing
        columnSpacing: AppConfig.formColumnSpacing

        // --- Background ---------------------------------------------------

        ToolTippedLabel {
            text: Strings.backgroundColorLabel
            toolTipText: Strings.backgroundColorTooltip
        }
        ColorPicker {
            Layout.preferredWidth: AppConfig.colorPickerWidth
            selectedColor: root.settings.backgroundColor
            previewOpacityPercent: root.settings.backgroundOpacity
            toolTipText: Strings.backgroundColorTooltip
            onColorPicked: (picked) => root.settings.backgroundColor = picked
        }

        ToolTippedLabel {
            text: Strings.backgroundOpacityLabel
            toolTipText: Strings.backgroundOpacityTooltip
        }
        CustomSpinBox {
            from: AppConfig.backgroundOpacityMin
            to: AppConfig.backgroundOpacityMax
            value: root.settings.backgroundOpacity
            onValueModified: root.settings.backgroundOpacity = value
        }

        // --- Shape --------------------------------------------------------

        ToolTippedLabel {
            text: Strings.cornerRadiusLabel
            toolTipText: Strings.cornerRadiusTooltip
        }
        CustomSpinBox {
            from: AppConfig.cornerRadiusMin
            to: AppConfig.cornerRadiusMax
            value: root.settings.cornerRadius
            onValueModified: root.settings.cornerRadius = value
        }

        ToolTippedLabel {
            text: Strings.borderThicknessLabel
            toolTipText: Strings.borderThicknessTooltip
        }
        CustomSpinBox {
            from: AppConfig.borderThicknessMin
            to: AppConfig.borderThicknessMax
            value: root.settings.borderThickness
            onValueModified: root.settings.borderThickness = value
        }

        ToolTippedLabel {
            text: Strings.borderColorLabel
            toolTipText: Strings.borderColorTooltip
            // Thickness 0 means no border, so the colour is inert.
            enabled: root.settings.hasBorder
            color: enabled ? AppConfig.universalForeground
                           : AppConfig.textDisabledColor
        }
        ColorPicker {
            Layout.preferredWidth: AppConfig.colorPickerWidth
            enabled: root.settings.hasBorder
            opacity: enabled ? 1.0 : 0.5
            selectedColor: root.settings.borderColor
            toolTipText: Strings.borderColorTooltip
            onColorPicked: (picked) => root.settings.borderColor = picked
        }

        // --- Type ---------------------------------------------------------

        ToolTippedLabel {
            text: Strings.fontFamilyLabel
            toolTipText: Strings.fontFamilyTooltip
        }
        ComboBox {
            Layout.preferredWidth: AppConfig.comboBoxWidth
            model: root.settings.fontFamilies
            currentIndex: root.settings.fontFamilies.indexOf(
                root.settings.fontFamily)
            onActivated: (index) =>
                root.settings.fontFamily = root.settings.fontFamilies[index]
        }

        ToolTippedLabel {
            text: Strings.fontSizeLabel
            toolTipText: Strings.fontSizeTooltip
        }
        CustomSpinBox {
            from: AppConfig.fontSizeMin
            to: AppConfig.fontSizeMax
            value: root.settings.fontSize
            onValueModified: root.settings.fontSize = value
        }

        ToolTippedLabel {
            text: Strings.fontColorLabel
            toolTipText: Strings.fontColorTooltip
        }
        ColorPicker {
            Layout.preferredWidth: AppConfig.colorPickerWidth
            selectedColor: root.settings.fontColor
            toolTipText: Strings.fontColorTooltip
            onColorPicked: (picked) => root.settings.fontColor = picked
        }

        // --- Placement ------------------------------------------------------

        ToolTippedLabel {
            text: Strings.labelPositionLabel
            toolTipText: Strings.labelPositionTooltip
        }
        ComboBox {
            Layout.preferredWidth: AppConfig.comboBoxWidth
            model: root.settings.positionNames
            currentIndex: root.settings.labelPosition
            onActivated: (index) => root.settings.labelPosition = index
        }

        ToolTippedLabel {
            text: Strings.labelMarginLabel
            toolTipText: Strings.labelMarginTooltip
        }
        CustomSpinBox {
            from: AppConfig.labelMarginMin
            to: AppConfig.labelMarginMax
            value: root.settings.labelMargin
            onValueModified: root.settings.labelMargin = value
        }

        ToolTippedLabel {
            text: Strings.labelColumnsLabel
            toolTipText: Strings.labelColumnsTooltip
        }
        CustomSpinBox {
            from: AppConfig.labelColumnsMin
            to: AppConfig.labelColumnsMax
            value: root.settings.labelColumns
            onValueModified: root.settings.labelColumns = value
        }

        ToolTippedLabel {
            text: Strings.labelRowsLabel
            toolTipText: Strings.labelRowsTooltip
        }
        CustomSpinBox {
            from: AppConfig.labelRowsMin
            to: AppConfig.labelRowsMax
            value: root.settings.labelRows
            onValueModified: root.settings.labelRows = value
        }

        ToolTippedLabel {
            text: Strings.keyAlignmentLabel
            toolTipText: Strings.keyAlignmentTooltip
        }
        ComboBox {
            Layout.preferredWidth: AppConfig.comboBoxWidth
            model: root.settings.alignmentNames
            currentIndex: root.settings.keyAlignment
            onActivated: (index) => root.settings.keyAlignment = index
        }

        ToolTippedLabel {
            text: Strings.valueAlignmentLabel
            toolTipText: Strings.valueAlignmentTooltip
        }
        ComboBox {
            Layout.preferredWidth: AppConfig.comboBoxWidth
            model: root.settings.alignmentNames
            currentIndex: root.settings.valueAlignment
            onActivated: (index) => root.settings.valueAlignment = index
        }

        ToolTippedLabel {
            text: Strings.keySeparatorLabel
            toolTipText: Strings.keySeparatorTooltip
        }
        ComboBox {
            Layout.preferredWidth: AppConfig.comboBoxWidth
            model: root.settings.separatorNames
            currentIndex: root.settings.keySeparator
            onActivated: (index) => root.settings.keySeparator = index
        }

        ToolTippedLabel {
            text: Strings.alignColumnsLabel
            toolTipText: Strings.alignColumnsTooltip
        }
        CheckBox {
            checked: root.settings.alignColumns
            onToggled: root.settings.alignColumns = checked
        }

        ToolTippedLabel {
            text: Strings.missingFieldLabel
            toolTipText: Strings.missingFieldTooltip
        }
        ComboBox {
            Layout.preferredWidth: AppConfig.comboBoxWidth
            model: root.settings.missingFieldPolicyNames
            currentIndex: root.settings.missingFieldPolicy
            onActivated: (index) => root.settings.missingFieldPolicy = index
        }

        // --- Reset ----------------------------------------------------------

        Item { Layout.fillWidth: false; implicitWidth: 1; implicitHeight: 1 }
        Button {
            Layout.alignment: Qt.AlignLeft
            text: "Restore defaults"
            padding: AppConfig.statusBarButtonPadding
            onClicked: {
                root.settings.restoreDefaults()
                root.forceActiveFocus()
            }
        }
    }

    }

}
