import QtQuick
import QtQuick.Controls
import "../Config"

// Drag-and-drop target for TFS images.
//
// The icon is greyscale at rest and colour while a valid drag hovers.
// onEntered does a cheap extension sniff purely for that visual feedback;
// Python does the authoritative validation on drop.
//
// There is no caption under the icon: the status bar is the app's single
// message channel, so the opening instruction and the loaded-file count
// both live there rather than being duplicated here.
//
// URLs are passed through as strings without stripping the file:// scheme
// — QUrl.toLocalFile() on the Python side handles percent-encoding and
// UNC shares correctly, and hand-rolled stripping does not.

Item {

    id: root

    property bool dragActive: false

    signal filesDropped(var urls)

    implicitWidth: AppConfig.dropZoneMinimumWidth
    implicitHeight: 160

    function _hasSupportedUrl(urls) {
        for (var i = 0; i < urls.length; ++i) {
            var lower = urls[i].toString().toLowerCase()
            if (lower.endsWith(".tif") || lower.endsWith(".tiff")
                    || lower.endsWith(".png")) {
                return true
            }
        }
        return false
    }

    // No frame of its own: the enclosing Card already draws one, and two
    // nested rounded rectangles around a single icon read as clutter. The
    // Card's border is tinted from main.qml on dragActive instead, so the
    // drag feedback survives without the extra rectangle.

    // Greyscale at rest, colour while a valid drag hovers. Both images
    // are stacked and cross-faded rather than swapping one source, so the
    // transition animates and neither image is decoded mid-drag.
    Item {
        id: iconSlot
        anchors.fill: parent
        anchors.margins: AppConfig.dropZoneIconMargin

        Image {
            id: catbugGrayscale
            anchors.fill: parent
            source: AppConfig.iconCatbugGrayscale
            fillMode: Image.PreserveAspectFit
            mipmap: true
            opacity: root.dragActive ? 0.0 : AppConfig.dropZoneIdleOpacity
            Behavior on opacity {
                NumberAnimation { duration: AppConfig.dropZoneCrossfadeMs }
            }
        }

        Image {
            id: catbugColor
            anchors.fill: parent
            source: AppConfig.iconCatbugColor
            fillMode: Image.PreserveAspectFit
            mipmap: true
            opacity: root.dragActive ? 1.0 : 0.0
            Behavior on opacity {
                NumberAnimation { duration: AppConfig.dropZoneCrossfadeMs }
            }
        }
    }

    DropArea {
        id: dropArea
        anchors.fill: parent

        onEntered: (drag) => {
            if (drag.hasUrls && root._hasSupportedUrl(drag.urls)) {
                drag.accept(Qt.CopyAction)
                root.dragActive = true
            } else {
                drag.accepted = false
            }
        }

        onExited: root.dragActive = false

        onDropped: (drop) => {
            root.dragActive = false
            if (drop.hasUrls) {
                var urls = []
                for (var i = 0; i < drop.urls.length; ++i) {
                    urls.push(drop.urls[i].toString())
                }
                root.filesDropped(urls)
            }
        }
    }

    HoverHandler { id: zoneHover }

    ToolTip.text: Strings.dropZoneTooltip
    ToolTip.visible: zoneHover.hovered
    ToolTip.delay: AppConfig.toolTipDelayMs
    ToolTip.timeout: AppConfig.toolTipTimeoutMs

}
