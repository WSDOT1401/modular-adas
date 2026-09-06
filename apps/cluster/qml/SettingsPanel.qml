import QtQuick

Item {
    id: panel

    property real speed: 0
    property string fontFamily: "Sans Serif"

    // Two-way bindings to the gauge profile
    property int    selectedMaxSpeed:    260
    property string selectedUnit:        "km/h"
    property string selectedSpeedSource: "OBD"

    signal closed()

    readonly property real s: Math.min(width, height) / 560

    // ── Navigation state ─────────────────────────────────────────
    property int currentRow: 0
    readonly property int rowCount: 3

    function open() { currentRow = 0 }

    function navigateUp() {
        currentRow = (currentRow - 1 + rowCount) % rowCount
    }
    function navigateDown() {
        currentRow = (currentRow + 1) % rowCount
    }
    function navigateLeft() {
        if (currentRow === 0) {
            const o = [180, 200, 220, 240, 260, 300]
            const i = o.indexOf(selectedMaxSpeed)
            selectedMaxSpeed = o[(i - 1 + o.length) % o.length]
        } else if (currentRow === 1) {
            const u = ["km/h", "mph"]
            selectedUnit = u[(u.indexOf(selectedUnit) - 1 + u.length) % u.length]
        } else {
            const src = ["OBD", "GPS"]
            selectedSpeedSource = src[(src.indexOf(selectedSpeedSource) - 1 + src.length) % src.length]
        }
    }
    function navigateRight() {
        if (currentRow === 0) {
            const o = [180, 200, 220, 240, 260, 300]
            const i = o.indexOf(selectedMaxSpeed)
            selectedMaxSpeed = o[(i + 1) % o.length]
        } else if (currentRow === 1) {
            const u = ["km/h", "mph"]
            selectedUnit = u[(u.indexOf(selectedUnit) + 1) % u.length]
        } else {
            const src = ["OBD", "GPS"]
            selectedSpeedSource = src[(src.indexOf(selectedSpeedSource) + 1) % src.length]
        }
    }

    // ── Settings card ─────────────────────────────────────────────
    Rectangle {
        id: settingsCard

        readonly property real rowH: 48 * panel.s
        readonly property real headerH: 38 * panel.s
        readonly property real footerH: 32 * panel.s
        readonly property real sepH: 1

        width:  390 * panel.s
        height: headerH + sepH + rowH * 3 + sepH + footerH
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter:   parent.verticalCenter
        anchors.verticalCenterOffset: -26 * panel.s
        color:  "#191714"
        border.color: "#2e2b28"
        border.width: 1
        radius: 8 * panel.s
        clip: true

        // ── Header ────────────────────────────────────────────────
        Item {
            id: headerArea
            width: parent.width
            height: settingsCard.headerH
            anchors.top: parent.top

            Text {
                text: "SETTINGS"
                color: "#d0ccc4"
                font.family: panel.fontFamily
                font.pixelSize: Math.round(13 * panel.s)
                font.letterSpacing: 5
                anchors.centerIn: parent
            }
        }

        Rectangle { id: topSep; width: parent.width; height: 1; color: "#252220"; anchors.top: headerArea.bottom }

        // ── Menu rows ─────────────────────────────────────────────
        Repeater {
            id: rowRepeater
            model: 3
            delegate: Item {
                id: rowItem
                readonly property bool sel: index === panel.currentRow
                readonly property string rowLabel: ["MAX SPEED", "UNIT", "SPEED SOURCE"][index]
                readonly property string rowValue: index === 0 ? String(panel.selectedMaxSpeed)
                                                 : index === 1 ? panel.selectedUnit
                                                               : panel.selectedSpeedSource

                width:  settingsCard.width
                height: settingsCard.rowH
                y: topSep.y + 1 + index * settingsCard.rowH

                // Row highlight
                Rectangle {
                    anchors.fill: parent
                    color: rowItem.sel ? "#21201c" : "transparent"
                }

                // Left accent bar
                Rectangle {
                    width: Math.round(4 * panel.s)
                    height: Math.round(26 * panel.s)
                    radius: Math.round(2 * panel.s)
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: parent.left
                    anchors.leftMargin: Math.round(8 * panel.s)
                    color: rowItem.sel ? "#ffa62f" : "transparent"
                }

                // Setting label
                Text {
                    text: rowItem.rowLabel
                    color: rowItem.sel ? "#d0ccc4" : "#4e4b47"
                    font.family: panel.fontFamily
                    font.pixelSize: Math.round(17 * panel.s)
                    font.letterSpacing: 2
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: parent.left
                    anchors.leftMargin: Math.round(26 * panel.s)
                }

                // Value + arrow indicators
                Row {
                    spacing: Math.round(7 * panel.s)
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.right: parent.right
                    anchors.rightMargin: Math.round(16 * panel.s)

                    Text {
                        text: "\u25c4"
                        color: rowItem.sel ? "#cc7c1a" : "transparent"
                        font.family: panel.fontFamily
                        font.pixelSize: Math.round(13 * panel.s)
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: rowItem.rowValue
                        color: rowItem.sel ? "#ffa62f" : "#4e4b47"
                        font.family: panel.fontFamily
                        font.pixelSize: Math.round(20 * panel.s)
                        font.weight: rowItem.sel ? Font.DemiBold : Font.Normal
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: "\u25ba"
                        color: rowItem.sel ? "#cc7c1a" : "transparent"
                        font.family: panel.fontFamily
                        font.pixelSize: Math.round(13 * panel.s)
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
        }

        // ── Bottom separator ──────────────────────────────────────
        Rectangle {
            id: botSep
            width: parent.width
            height: 1
            color: "#252220"
            anchors.bottom: footerArea.top
        }

        // ── Footer hints ──────────────────────────────────────────
        Item {
            id: footerArea
            width: parent.width
            height: settingsCard.footerH
            anchors.bottom: parent.bottom

            Row {
                anchors.centerIn: parent
                spacing: Math.round(22 * panel.s)

                Text {
                    text: "PUSH TO CLOSE"
                    color: "#d0ccc4"
                    font.family: panel.fontFamily
                    font.pixelSize: Math.round(11 * panel.s)
                    font.letterSpacing: 2
                }
            }
        }
    }

    // ── Digital speed readout (below card) ────────────────────────
    Item {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: settingsCard.bottom
        anchors.topMargin: 8 * panel.s
        width: 250 * panel.s
        height: 76 * panel.s

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.horizontalCenterOffset: -18 * panel.s
            anchors.bottom: parent.bottom
            text: Math.round(panel.speed)
            color: "#efede8"
            font.family: panel.fontFamily
            font.pixelSize: Math.round(64 * panel.s)
            font.weight: Font.Light
        }

        Text {
            anchors.left: parent.horizontalCenter
            anchors.leftMargin: 52 * panel.s
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 8 * panel.s
            text: panel.selectedUnit
            color: "#c8c1b8"
            font.family: panel.fontFamily
            font.pixelSize: Math.round(20 * panel.s)
            font.weight: Font.Medium
        }
    }
}
