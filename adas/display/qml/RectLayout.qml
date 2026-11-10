import QtQuick

// 4:3 screen, designed at 960×720 (Main.qml scales it to the real panel).
// The extra width buys a full-width alert banner, a module status list and a
// strip of recently read signs.
Item {
    id: root
    required property var st          // AdasState
    width: 960
    height: 720

    readonly property bool paused: !st.adasOnline || st.systemFault !== ""
    readonly property bool fcw: st.reason === "fcw"

    Rectangle {
        anchors.fill: parent
        radius: 14
        color: Theme.bg
    }

    // ---- banner ------------------------------------------------------------
    Rectangle {
        width: parent.width
        height: 80
        radius: 14   // rounded top corners; the strip below squares the bottom
        color: Theme.bannerBg(st.level)
        Rectangle {
            y: 40
            width: parent.width
            height: 40
            color: parent.color
        }
        Row {
            x: 32
            anchors.verticalCenter: parent.verticalCenter
            spacing: 16
            AlertIcon {
                anchors.verticalCenter: parent.verticalCenter
                visible: st.level !== "none"
                level: st.level
                color: Theme.bannerFg(st.level)
            }
            Text {
                anchors.baseline: detailText.baseline
                text: Theme.bannerTitle(st)
                color: Theme.bannerFg(st.level)
                font.pixelSize: 30
                font.weight: Font.DemiBold
                font.letterSpacing: 0.6
            }
            Text {
                id: detailText
                anchors.verticalCenter: parent.verticalCenter
                text: Theme.bannerDetail(st)
                color: Theme.bannerSub(st.level)
                font.pixelSize: 20
            }
        }
    }

    // ---- left column: limit, speed, modules --------------------------------
    Column {
        x: 32
        y: 112
        width: 252
        spacing: 0
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            width: 162; height: 162; radius: 81
            color: "transparent"
            border.width: 5
            border.color: st.overspeed ? Theme.caution : "transparent"
            SignIcon {
                anchors.centerIn: parent
                size: 144
                kind: "limit"
                value: st.speedLimit
                dim: st.speedLimit <= 0
            }
        }
        Item { width: 1; height: 22 }
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: st.hasSpeed ? Math.round(st.speed) : "--"
            color: st.overspeed ? Theme.caution : Theme.text
            font.pixelSize: 112
            font.weight: Font.Medium
        }
        Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: "KM/H"
            color: Theme.textDim
            font.pixelSize: 18
            font.letterSpacing: 2
        }
    }
    Column {
        x: 32
        y: 584
        width: 252
        spacing: 12
        Repeater {
            model: [
                { name: "Lane departure", state: st.moduleLane },
                { name: "Forward collision", state: st.moduleFcw },
                { name: "Sign reading", state: st.moduleSigns }
            ]
            delegate: Row {
                required property var modelData
                width: 252
                spacing: 12
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 12; height: 12; radius: 6
                    color: modelData.state === "on" ? "#E6EBEF" : "transparent"
                    border.width: 2
                    border.color: modelData.state === "on" ? "#E6EBEF" : Theme.muted
                }
                // filled dot = on, hollow = paused or off
                Text {
                    width: 252 - 12 - 12
                    text: modelData.name
                    color: modelData.state === "on" ? Theme.text : Theme.textDim
                    font.pixelSize: 18
                }
            }
        }
    }

    // ---- road ------------------------------------------------------------
    Rectangle {
        x: 316
        y: 112
        width: 612
        height: 380
        radius: 14
        color: Theme.panel
        clip: true
        LaneView {
            y: 9
            scale: 612 / 440
            transformOrigin: Item.TopLeft
            drift: st.laneWarning ? st.laneDirection : "none"
            lead: st.fcwWarning
            paused: root.paused
        }
    }

    // ---- signs seen --------------------------------------------------------
    Rectangle {
        x: 316
        y: 512
        width: 612
        height: 176
        radius: 14
        color: Theme.panel
        // The signs themselves, newest first; the words are kept big.
        Row {
            x: 24
            anchors.verticalCenter: parent.verticalCenter
            spacing: 32
            Row {
                visible: st.signFresh
                spacing: 16
                SignIcon { size: 112; kind: st.signSeen }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: Theme.signLabel(st.signSeen)
                    color: "#9CD3FF"
                    font.pixelSize: 24
                    font.weight: Font.Medium
                }
            }
            SignIcon { size: 112; kind: "limit"; value: st.speedLimit; dim: st.speedLimit <= 0 }
        }
    }

    // ---- collision: the whole frame pulses red -------------------------------
    Rectangle {
        anchors.fill: parent
        anchors.margins: 0
        radius: 14
        color: "transparent"
        border.color: Theme.warning
        border.width: 12
        visible: root.fcw
        SequentialAnimation on opacity {
            running: root.fcw
            loops: Animation.Infinite
            NumberAnimation { from: 1; to: 0.25; duration: 350 }
            NumberAnimation { from: 0.25; to: 1; duration: 350 }
        }
    }
}
