import QtQuick
import QtQuick.Shapes

// The road ahead from behind the car: our lane, our car, and a vehicle ahead
// when a collision is near. Drawn on a 440×260 grid; scale it to fit.
Item {
    id: root
    property string drift: "none"   // "left", "right" or "none"
    property bool lead: false       // vehicle ahead (collision warning)
    property bool paused: false     // camera unusable: dashed lines, grey car

    width: 440
    height: 260

    readonly property color leftColor: paused ? Theme.lineOff : (drift === "left" ? Theme.caution : Theme.line)
    readonly property color rightColor: paused ? Theme.lineOff : (drift === "right" ? Theme.caution : Theme.line)
    readonly property real carShift: drift === "left" ? -72 : (drift === "right" ? 72 : 0)

    Shape {
        anchors.fill: parent
        layer.enabled: true
        layer.samples: 4

        // horizon
        ShapePath {
            strokeColor: Theme.track; strokeWidth: 2; fillColor: "transparent"
            startX: 0; startY: 18
            PathLine { x: 440; y: 18 }
        }
        // road surface
        ShapePath {
            strokeColor: "transparent"; fillColor: Theme.road
            startX: 200; startY: 18
            PathLine { x: 240; y: 18 }
            PathLine { x: 410; y: 260 }
            PathLine { x: 30; y: 260 }
            PathLine { x: 200; y: 18 }
        }
        // drift bands
        ShapePath {
            strokeColor: "transparent"
            fillColor: root.drift === "left" && !root.paused ? Qt.rgba(1, 0.69, 0.125, 0.22) : "transparent"
            startX: 196; startY: 18
            PathLine { x: 204; y: 18 }
            PathLine { x: 92; y: 260 }
            PathLine { x: 44; y: 260 }
            PathLine { x: 196; y: 18 }
        }
        ShapePath {
            strokeColor: "transparent"
            fillColor: root.drift === "right" && !root.paused ? Qt.rgba(1, 0.69, 0.125, 0.22) : "transparent"
            startX: 236; startY: 18
            PathLine { x: 244; y: 18 }
            PathLine { x: 396; y: 260 }
            PathLine { x: 348; y: 260 }
            PathLine { x: 236; y: 18 }
        }
        // lane lines
        ShapePath {
            strokeColor: root.leftColor
            strokeWidth: root.drift === "left" && !root.paused ? 8 : 4
            strokeStyle: root.paused ? ShapePath.DashLine : ShapePath.SolidLine
            dashPattern: [1.5, 2.25]
            capStyle: ShapePath.RoundCap
            fillColor: "transparent"
            startX: 196; startY: 18
            PathLine { x: 44; y: 260 }
        }
        ShapePath {
            strokeColor: root.rightColor
            strokeWidth: root.drift === "right" && !root.paused ? 8 : 4
            strokeStyle: root.paused ? ShapePath.DashLine : ShapePath.SolidLine
            dashPattern: [1.5, 2.25]
            capStyle: ShapePath.RoundCap
            fillColor: "transparent"
            startX: 244; startY: 18
            PathLine { x: 396; y: 260 }
        }
        // gap to the vehicle ahead
        ShapePath {
            strokeColor: root.lead ? Theme.warning : "transparent"
            strokeWidth: 3
            strokeStyle: ShapePath.DashLine
            dashPattern: [1.3, 2]
            fillColor: "transparent"
            startX: 220; startY: 108
            PathLine { x: 220; y: 140 }
        }
    }

    // vehicle ahead: the same sedan, far away and red
    CarRear {
        visible: root.lead
        x: 220 - width / 2
        y: 66
        scale: 0.36
        transformOrigin: Item.Top
        body: Theme.warning
        glass: "#5A1410"
        trim: "#B8382C"
        tail: "#5A1410"
        details: false
    }

    // our car, from behind and above
    CarRear {
        x: 220 - width / 2 + root.carShift
        y: 148
        body: root.paused ? Theme.lineOff : Theme.car
        trim: root.paused ? "#3A4148" : "#9AA2A9"
        tail: root.paused ? "#3A4148" : "#B3261E"
        plate: root.paused ? "#5B636B" : "#F5F7F8"
        Behavior on x { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
    }
}
