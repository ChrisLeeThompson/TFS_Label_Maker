import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Universal
import QtQuick.Dialogs
import QtQuick.Layouts
import "./Config"
import "./Components"

ApplicationWindow {

    id: mainWindow

    // Single entry point for images however they arrive — dropped on the
    // catbug or chosen through the Load dialog. URLs are passed on as
    // strings with the file:// scheme intact; QUrl.toLocalFile() on the
    // Python side handles percent-encoding and UNC shares correctly.
    function loadUrls(urls) {
        if (!urls || urls.length === 0) {
            return
        }
        // Never start a reparse under a running job: a drop mid-export
        // would run both BackgroundJobs at once and interleave their
        // progress streams on the one status bar.
        if (appController.busy) {
            return
        }
        appController.images.addUrls(urls)
    }

    // The top row's right column can neither scroll nor shrink: the
    // catbug's floor plus the content-sized Output card is a hard
    // floor. Derived from the live panel rather than an AppConfig
    // token so a new Output row can never quietly reopen the gap
    // between a token and the real height. (Heights only — the
    // binding-loop hazard the config file warns about runs through
    // widths and label wrapping.)
    readonly property real outputCardHeight: outputPanel.implicitHeight
                                             + AppConfig.labelPreviewCardChrome
    readonly property real topRowFloor: Math.max(
        AppConfig.topRowMinimumHeight,
        AppConfig.dropZoneMinimumHeight + AppConfig.pageSectionSpacing
        + outputCardHeight)
    readonly property real previewCardHeight: Math.max(
        AppConfig.labelPreviewMinimumHeight,
        labelPreview.implicitHeight + AppConfig.labelPreviewCardChrome)

    width: AppConfig.mainWindowWidth
    height: AppConfig.mainWindowHeight
    minimumWidth: AppConfig.mainWindowMinimumWidth
    // The stack's true floor: every fixed-height row at full size, the
    // tree at its minimum. Below this something must clip (the rows
    // cannot scroll), so the window refuses to go there — the Output
    // card stays whole at any height the user can reach. Grows live
    // when the preview gains rows; the static config value is only a
    // backstop.
    minimumHeight: Math.max(
        AppConfig.mainWindowMinimumHeight,
        2 * AppConfig.pageMargin + 3 * AppConfig.pageSectionSpacing
        + topRowFloor + previewCardHeight
        + AppConfig.metadataTreeMinimumHeight
        + mainStatusBar.implicitHeight)
    visible: true
    title: Strings.mainWindowTitle

    Universal.theme: AppConfig.universalTheme
    Universal.accent: AppConfig.universalAccent
    Universal.foreground: AppConfig.universalForeground
    Universal.background: AppConfig.universalBackground

    // Underneath everything: clicks on the page margins between cards
    // clear whatever control holds focus (the cards handle their own
    // interiors the same way).
    MouseArea {
        anchors.fill: parent
        onClicked: mainWindow.contentItem.forceActiveFocus()
    }

    ColumnLayout {

        anchors.fill: parent
        anchors.margins: AppConfig.pageMargin
        spacing: AppConfig.pageSectionSpacing

        // --- Row 1: settings + drop zone ---------------------------------
        //
        // Fixed at its preferred height: window stretch belongs to the
        // metadata tree (row 3), the only genuinely unbounded content —
        // the settings card scrolls, so growing this row only moves its
        // cut-off point around (explicit user decision: the tree was
        // the cramped one). The maximum stays as a safety cap should
        // the preferred height ever misbehave.
        RowLayout {
            id: topRow
            Layout.fillWidth: true
            Layout.fillHeight: false
            // Content-aware: the right column is fixed-height content
            // (catbug floor + Output card) that cannot scroll, so the
            // row must prefer at least that much or the cards overflow
            // into the preview row below (measured at 44 px once the
            // Output card gained its combo row).
            Layout.preferredHeight: Math.max(AppConfig.topRowHeight,
                                             rightColumn.implicitHeight)
            // Content-aware for the same reason: the static token alone
            // let a short window squeeze the row below the right
            // column's needs, pushing the Output card out of the row
            // and under the preview (user-reported clip).
            Layout.minimumHeight: mainWindow.topRowFloor
            Layout.maximumHeight: AppConfig.topRowMaximumHeight
            spacing: AppConfig.pageSectionSpacing

            Card {
                id: settingsCard
                title: Strings.settingsGroupTitle
                Layout.fillWidth: true
                Layout.fillHeight: true

                SettingsPanel {
                    anchors.fill: parent
                    interactive: !appController.busy
                    settings: appController.settings
                }
            }

            // Right column: catbug on top, output settings beneath.
            // The drop card takes all the slack so the icon stays the
            // prominent target; the Output card is content-sized.
            ColumnLayout {
                id: rightColumn
                // A ColumnLayout inside a RowLayout defaults fillWidth to
                // true (plain items default false) — without pinning it,
                // this column absorbed the row and crushed the settings
                // card to 2 px (measured).
                Layout.fillWidth: false
                Layout.preferredWidth: AppConfig.topRowRightColumnWidth
                Layout.fillHeight: true
                spacing: AppConfig.pageSectionSpacing

                Card {
                    id: dropCard
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    // A floor so the content-sized PowerPoint card below
                    // can never crush the catbug out of existence at the
                    // window's minimum height.
                    Layout.minimumHeight: AppConfig.dropZoneMinimumHeight

                    // The drop zone draws no frame of its own, so the card's
                    // border carries the drag feedback.
                    border.color: dropZone.dragActive ? AppConfig.dropZoneActiveBorder
                                                      : AppConfig.containerIdleBorder
                    Behavior on border.color {
                        ColorAnimation { duration: AppConfig.dropZoneHoverDurationMs }
                    }

                    DropZone {
                        id: dropZone
                        anchors.fill: parent
                        // Same gate as the Load button: no drops while a
                        // parse or an export is running (enabled: false
                        // disables the child DropArea too).
                        enabled: !appController.busy
                        opacity: enabled ? 1.0 : 0.5
                        onFilesDropped: (urls) => mainWindow.loadUrls(urls)
                    }
                }

                Card {
                    id: outputCard
                    title: Strings.outputGroupTitle
                    Layout.fillWidth: true
                    Layout.fillHeight: false
                    // Shared with the window-minimum math above so the
                    // floor can never drift from the real card height.
                    Layout.preferredHeight: mainWindow.outputCardHeight

                    OutputPanel {
                        id: outputPanel
                        anchors.fill: parent
                        interactive: !appController.busy
                        powerpoint: appController.powerpoint
                        settings: appController.settings
                    }
                }
            }
        }

        // --- Row 2: label preview ----------------------------------------
        //
        // Fixed-height frame: LabelPreview sizes itself for the largest
        // grid (4 rows) plus the reserved nav strip, so row/column
        // changes never resize the window. Never a hard-coded height on
        // the card — a fixed height plus the Card's clip once cut the
        // outer rows off and stopped their DropAreas from receiving
        // drag hover; the preview's own safety valve grows this instead
        // of clipping.
        Card {
            id: previewCard
            title: Strings.labelPreviewGroupTitle
            // The batch position, in line with the title (mirrors the
            // nav row's visibility rule).
            headerText: appController.images.count > 1
                        && !appController.images.isParsing
                        ? (appController.images.currentImageIndex + 1)
                          + Strings.batchNavPositionSeparator
                          + appController.images.count
                        : ""
            Layout.fillWidth: true
            Layout.fillHeight: false
            // Shared with the window-minimum math above so the floor
            // can never drift from the real card height.
            Layout.preferredHeight: mainWindow.previewCardHeight

            // The blank grid is always visible — empty cells are the
            // invitation ("a matrix ready to be populated"), so there
            // is no placeholder text to swap in and out.
            LabelPreview {
                id: labelPreview
                anchors.fill: parent
                interactive: !appController.busy
                label: appController.label
                settings: appController.settings
                images: appController.images
            }
        }

        // --- Row 3: metadata tree ----------------------------------------
        //
        // The only genuinely unbounded content, so it absorbs all slack.
        Card {
            id: metadataCard
            title: Strings.metadataGroupTitle
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: AppConfig.metadataTreeMinimumHeight

            MetadataTree {
                anchors.fill: parent
                visible: appController.images.fieldCount > 0
                fieldsModel: appController.images.fieldsModel
                treeModel: appController.images.treeModel
            }

            Label {
                anchors.centerIn: parent
                visible: appController.images.fieldCount === 0
                // Same empty tree, three different truths: nothing
                // loaded yet (invite a drop), a parse the user stopped
                // (the tree empties by design — say so, not "your
                // images are unreadable"), or a loaded batch in which
                // no image carried any readable metadata.
                text: appController.images.count > 0
                      && !appController.images.isParsing
                      ? (appController.images.lastParseStopped
                         ? Strings.treeStoppedText
                         : Strings.treeNoMetadataText)
                      : Strings.treeEmptyText
                color: AppConfig.textDisabledColor
                font.pixelSize: AppConfig.pageBodyFontSize
                wrapMode: Text.WordWrap
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
            }
        }

        // --- Status bar ---------------------------------------------------
        StatusBar {
            id: mainStatusBar
            Layout.fillWidth: true

            message: appController.statusMessage
            busy: appController.busy
            loadEnabled: !appController.busy
            clearEnabled: !appController.busy && appController.images.count > 0
            startEnabled: appController.canStart
            stopEnabled: appController.busy

            onLoadClicked: loadDialog.open()
            onClearClicked: appController.images.clear()
            onStartClicked: appController.start()
            onStopClicked: appController.stop()

            Connections {
                target: appController
                ignoreUnknownSignals: true

                function onProgressUpdated(current, total) {
                    if (current === -1 && total === -1) {
                        mainStatusBar.indeterminate = true
                    } else if (total > 0) {
                        mainStatusBar.progress = current / total
                        mainStatusBar.indeterminate = false
                    }
                }

                function onBusyChanged() {
                    if (appController.busy) {
                        progressResetTimer.stop()
                    } else {
                        progressResetTimer.restart()
                    }
                }
            }

            Timer {
                id: progressResetTimer
                interval: AppConfig.statusBarProgressResetMs
                repeat: false
                onTriggered: {
                    mainStatusBar.progress = 0
                    mainStatusBar.indeterminate = false
                }
            }
        }

    }

    // Alternative to dropping. Left native (no DontUseNativeDialog) on
    // purpose: unlike the colour dialog, a file dialog is somewhere users
    // expect their own shell — recent places, mapped drives, typing a UNC
    // path — and the Qt Quick replacement offers none of that.
    FileDialog {
        id: loadDialog
        title: Strings.loadDialogTitle
        fileMode: FileDialog.OpenFiles
        nameFilters: Strings.loadDialogFilters
        onAccepted: {
            var urls = []
            for (var i = 0; i < selectedFiles.length; ++i) {
                urls.push(selectedFiles[i].toString())
            }
            mainWindow.loadUrls(urls)
        }
    }

    // Fatal, pre-flight problems only. Per-file failures go to the status
    // bar and the log so a batch is never interrupted by a modal.
    Dialog {
        id: errorDialog
        anchors.centerIn: parent
        modal: true
        title: Strings.errorDialogTitle
        standardButtons: Dialog.Ok
        property string detail: ""

        Label {
            text: errorDialog.detail
            wrapMode: Text.WordWrap
            width: 380
        }
    }

    Connections {
        target: appController
        ignoreUnknownSignals: true
        function onErrorOccurred(text) {
            errorDialog.detail = text
            errorDialog.open()
        }
    }

}
