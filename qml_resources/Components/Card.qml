import QtQuick
import QtQuick.Controls
import "../Config"

// Titled panel providing the app's container chrome.
//
// The sibling apps get this look from GroupBox with its frame erased plus
// a wrapping Rectangle. Doing it in one component avoids fighting
// GroupBox's title-band geometry, which is awkward to position against
// the Universal style's padding.
//
// Children are reparented into contentArea and should anchor themselves,
// typically `anchors.fill: parent`.

Rectangle {

    id: root

    property string title: ""
    default property alias contentData: contentArea.data

    color: AppConfig.containerBackground
    border.color: AppConfig.containerIdleBorder
    border.width: AppConfig.containerBorderWidth
    radius: AppConfig.containerBorderRadius

    // Declared before the content so it stacks underneath: real
    // controls get the click first, and only clicks that miss them
    // land here — taking focus away from whichever spin box or text
    // field held it, so a stray click anywhere in a card commits and
    // dismisses the focused control (same treatment SettingsPanel
    // gives its own form).
    MouseArea {
        anchors.fill: parent
        onClicked: root.forceActiveFocus()
    }

    Label {
        id: titleLabel
        text: root.title
        visible: root.title !== ""
        font.pixelSize: AppConfig.pageBodyFontSize
        font.bold: true
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: AppConfig.pageMargin
        elide: Text.ElideRight
    }

    Item {
        id: contentArea
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: titleLabel.visible ? titleLabel.bottom : parent.top
        anchors.bottom: parent.bottom
        anchors.leftMargin: AppConfig.pageMargin
        anchors.rightMargin: AppConfig.pageMargin
        anchors.bottomMargin: AppConfig.pageMargin
        anchors.topMargin: titleLabel.visible ? AppConfig.formRowSpacing
                                              : AppConfig.pageMargin
        clip: true
    }

}
