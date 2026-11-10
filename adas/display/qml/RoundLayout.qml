import QtQuick
import QtQuick.Shapes

// Round screen, designed at 720×720 (Main.qml scales it to the real panel).
// Alerts live on the rim and in the line under the road view.
Item {
    id: root
    required property var st          // AdasState
    width: 720
    height: 720

    readonly property bool paused: !st.adasOnline || st.systemFault !== ""
    readonly property bool fcw: st.reason === "fcw"

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: Theme.bg
    }

    // ---- rim -----------------------------------------------------------
    Rectangle {
        anchors.centerIn: parent
        width: 706; height: 706; radius: 353
        color: "transparent"
        border.color: Theme.track
        border.width: 6
    }
    Shape {
        anchors.fill: parent
        visible: root.paused
        layer.enabled: true
        layer.samples: 4
        ShapePath {
            strokeColor: Theme.muted; strokeWidth: 6; fillColor: "transparent"
            strokeStyle: ShapePath.DashLine; dashPattern: [1.7, 2.3]
            PathAngleArc { centerX: 360; centerY: 360; radiusX: 350; radiusY: 350; startAngle: 0; sweepAngle: 360 }
        }
    }
    Shape {
        anchors.fill: parent
        layer.enabled: true
        layer.samples: 4
        // drifting left / right: the rim lights on that side
        ShapePath {
            strokeColor: st.reason === "lane_left" ? Theme.caution : "transparent"
            strokeWidth: 18; fillColor: "transparent"; capStyle: ShapePath.RoundCap
            PathAngleArc { centerX: 360; centerY: 360; radiusX: 350; radiusY: 350; startAngle: 150; sweepAngle: 60 }
        }
        ShapePath {
            strokeColor: st.reason === "lane_right" ? Theme.caution : "transparent"
            strokeWidth: 18; fillColor: "transparent"; capStyle: ShapePath.RoundCap
            PathAngleArc { centerX: 360; centerY: 360; radiusX: 350; radiusY: 350; startAngle: -30; sweepAngle: 60 }
        }
        // over the limit: the rim lights above the sign
        ShapePath {
            strokeColor: st.reason === "overspeed" ? Theme.caution : "transparent"
            strokeWidth: 14; fillColor: "transparent"; capStyle: ShapePath.RoundCap
            PathAngleArc { centerX: 360; centerY: 360; radiusX: 350; radiusY: 350; startAngle: 240; sweepAngle: 60 }
        }
    }
    // collision: the whole rim pulses red
    Rectangle {
        anchors.centerIn: parent
        width: 698; height: 698; radius: 349
        color: "transparent"
        border.color: Theme.warning
        border.width: 24
        visible: root.fcw
        SequentialAnimation on opacity {
            running: root.fcw
            loops: Animation.Infinite
            NumberAnimation { from: 1; to: 0.25; duration: 350 }
            NumberAnimation { from: 0.25; to: 1; duration: 350 }
        }
    }

    // ---- signs -----------------------------------------------------------
    Row {
        y: 56
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 20
        Rectangle {
            width: 98; height: 98; radius: 49
            color: "transparent"
            border.width: 4
            border.color: st.overspeed ? Theme.caution : "transparent"
            SignIcon {
                anchors.centerIn: parent
                size: 84
                kind: "limit"
                value: st.speedLimit
                dim: st.speedLimit <= 0
            }
        }
        Rectangle {
            visible: st.signFresh
            width: 98; height: 98; radius: 49
            color: "transparent"
            border.width: 4
            border.color: Theme.info
            SignIcon {
                anchors.centerIn: parent
                size: 84
                kind: st.signSeen
            }
        }
    }

    // ---- speed / brake -------------------------------------------------------
    // Placed, not stacked: fonts differ in line height, and "KM/H" must stay
    // above the road's horizon (y 322) whatever font the Pi has.
    Text {
        y: 164
        width: parent.width
        height: 112
        visible: !root.fcw
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        text: st.hasSpeed ? Math.round(st.speed) : "--"
        color: st.overspeed ? Theme.caution : Theme.text
        font.pixelSize: 108
        font.weight: Font.Medium
    }
    Text {
        y: 280
        width: parent.width
        visible: !root.fcw
        horizontalAlignment: Text.AlignHCenter
        text: "KM/H"
        color: Theme.textDim
        font.pixelSize: 18
        font.letterSpacing: 2
    }
    Text {
        y: 168
        width: parent.width
        height: 132
        visible: root.fcw
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        text: "BRAKE"
        color: Theme.warning
        font.pixelSize: 104
        font.weight: Font.DemiBold
        font.letterSpacing: 4
    }

    // ---- road ------------------------------------------------------------
    LaneView {
        x: 140
        y: 304
        drift: st.laneWarning ? st.laneDirection : "none"
        lead: st.fcwWarning
        paused: root.paused
    }

    // ---- alert text: one line, big enough to read at a glance ---------------
    Text {
        x: 140
        y: 580
        width: 440
        visible: st.level !== "none"
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
        text: Theme.title(st)
        color: Theme.levelColor(st.level)
        font.pixelSize: 34
        font.weight: Font.Medium
    }
}
