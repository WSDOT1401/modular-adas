import QtQuick

Item {
    id: root

    property bool connected: true
    property string fontFamily: "Sans Serif"

    readonly property real s: Math.min(width, height) / 560

    // Album art
    Rectangle {
        id: albumArt
        width: 138 * root.s
        height: width
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: -38 * root.s
        radius: 11 * root.s
        color: "#1b1a18"
        border.color: "#47403a"
        border.width: 1

        Canvas {
            anchors.fill: parent
            Component.onCompleted: requestPaint()
            onPaint: {
                const ctx = getContext("2d")
                const W = width, H = height
                ctx.clearRect(0, 0, W, H)
                // Subtle record grooves
                ctx.strokeStyle = "rgba(255,255,255,0.035)"
                ctx.lineWidth = 0.8
                for (let r = 22; r < H / 2 - 6; r += 7) {
                    ctx.beginPath()
                    ctx.arc(W / 2, H / 2, r, 0, Math.PI * 2)
                    ctx.stroke()
                }
                // Music note glyph
                ctx.fillStyle = "#6e6760"
                ctx.font = `${Math.round(H * 0.42)}px sans-serif`
                ctx.textAlign = "center"
                ctx.textBaseline = "middle"
                ctx.fillText("♪", W / 2, H / 2 + H * 0.02)
            }
        }
    }

    Text {
        id: musicTitle
        text: "No Track"
        color: "#efede8"
        font.pixelSize: Math.round(16 * root.s)
        font.family: root.fontFamily
        font.weight: Font.Medium
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: albumArt.bottom
        anchors.topMargin: 12 * root.s
    }

    Text {
        text: "Bluetooth Audio"
        color: "#8f897f"
        font.pixelSize: Math.round(10 * root.s)
        font.family: root.fontFamily
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: musicTitle.bottom
        anchors.topMargin: 4 * root.s
    }

    // Progress bar
    Rectangle {
        id: progressTrack
        width: 148 * root.s
        height: 3 * root.s
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: musicTitle.bottom
        anchors.topMargin: 22 * root.s
        color: "#2d2b28"
        radius: 1.5 * root.s

        Rectangle {
            width: 0
            height: parent.height
            color: "#c8b890"
            radius: parent.radius
            NumberAnimation on width {
                from: 0
                to: progressTrack.width
                duration: 14000
                loops: Animation.Infinite
                running: true
            }
        }
    }

    // Connection status pill
    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: progressTrack.bottom
        anchors.topMargin: 10 * root.s
        spacing: 5 * root.s

        Rectangle {
            width: 6 * root.s
            height: width
            radius: width / 2
            color: root.connected ? "#52aee0" : "#4a4540"
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: root.connected ? "Connected" : "Disconnected"
            color: root.connected ? "#70a8cc" : "#5e5852"
            font.pixelSize: Math.round(9 * root.s)
            font.family: root.fontFamily
            anchors.verticalCenter: parent.verticalCenter
        }
    }
}
