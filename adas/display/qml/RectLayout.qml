import QtQuick

// 4:3 screen, designed at 960×720 (Main.qml scales it to the real panel).
// The extra width buys a full-width alert banner, the safety features in use
// and a strip of recently read signs. Only BRAKE, CAMERA VIEW BLOCKED and
// OVERSPEED are spelled out.
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
            spacing: 18
            CameraOffIcon {
                anchors.verticalCenter: parent.verticalCenter
                visible: st.reason === "fault" && Theme.isCameraFault(st.systemFault)
                size: 44
                color: Theme.bannerFg(st.level)
                bg: Theme.bannerBg(st.level)
            }
            AlertIcon {
                anchors.verticalCenter: parent.verticalCenter
                visible: st.level !== "none" && st.level !== "system"
                level: st.level
                color: Theme.bannerFg(st.level)
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: root.fcw ? "BRAKE" : Theme.title(st)
                color: Theme.bannerFg(st.level)
                font.pixelSize: 32
                font.weight: Font.DemiBold
                font.letterSpacing: 1
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
    // safety features in use: green on, amber unavailable, struck-through off
    Row {
        x: 32
        y: 600
        spacing: 30
        FeatureIcon { feature: "lane"; status: st.moduleLane; size: 64 }
        FeatureIcon { feature: "fcw"; status: st.moduleFcw; size: 64 }
        FeatureIcon { feature: "signs"; status: st.moduleSigns; size: 64 }
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
        // camera can't see: a struck-through camera over the road
        Rectangle {
            visible: st.reason === "fault" && Theme.isCameraFault(st.systemFault)
            x: parent.width / 2 - width / 2
            y: 56
            width: 132; height: 132; radius: 66
            color: Theme.bg
            border.color: Theme.track
            border.width: 3
            CameraOffIcon {
                anchors.centerIn: parent
                size: 92
            }
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
        // The signs themselves, newest first; a newly read one ringed blue.
        Row {
            x: 24
            anchors.verticalCenter: parent.verticalCenter
            spacing: 32
            Rectangle {
                visible: st.signFresh && !Theme.isLimitSign(st.signSeen)
                width: 124; height: 124; radius: 62
                anchors.verticalCenter: parent.verticalCenter
                color: "transparent"
                border.width: 4
                border.color: Theme.info
                SignIcon { anchors.centerIn: parent; size: 108; kind: st.signSeen }
            }
            Rectangle {
                width: 124; height: 124; radius: 62
                color: "transparent"
                border.width: 4
                border.color: st.signFresh && Theme.isLimitSign(st.signSeen) ? Theme.info : "transparent"
                SignIcon { anchors.centerIn: parent; size: 108; kind: "limit"; value: st.speedLimit; dim: st.speedLimit <= 0 }
            }
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
