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

    // Lane lines in perspective: each is a filled outline that is widest at
    // the bottom and thins to a hairline at the horizon (y 18). When paused
    // the line breaks into dashes that are equally long on the road, so they
    // shorten toward the horizon too.
    readonly property real horizonY: 18
    readonly property real depth: 242   // horizon to bottom edge
    readonly property real lineWidth: 12
    readonly property real driftLineWidth: 20

    function lanePath(xTop, xBottom, widthBottom, dashed) {
        const half = d => (1 + (widthBottom - 1) * d / depth) / 2
        const xAt = d => xTop + (xBottom - xTop) * d / depth
        const pt = (x, d) => x.toFixed(2) + "," + (horizonY + d).toFixed(2)
        // d is the distance below the horizon; d0 is the far end of a piece.
        const piece = (d0, d1) => "M" + pt(xAt(d0) - half(d0), d0)
            + " L" + pt(xAt(d0) + half(d0), d0)
            + " L" + pt(xAt(d1) + half(d1), d1)
            + " L" + pt(xAt(d1) - half(d1), d1) + " Z"
        if (!dashed)
            return piece(0, depth)
        // On screen, distance below the horizon is depth / z for a point z
        // road-units ahead (z = 1 at the bottom edge).
        let path = ""
        for (let z = 1; depth / (z + 0.35) > 3; z += 0.8)
            path += piece(depth / (z + 0.35), depth / z) + " "
        return path
    }

    Shape {
        anchors.fill: parent
        antialiasing: true   // smooth edges on the software renderer too
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
            strokeColor: "transparent"
            fillColor: root.leftColor
            PathSvg {
                path: root.lanePath(196, 44,
                    root.drift === "left" && !root.paused ? root.driftLineWidth : root.lineWidth,
                    root.paused)
            }
        }
        ShapePath {
            strokeColor: "transparent"
            fillColor: root.rightColor
            PathSvg {
                path: root.lanePath(244, 396,
                    root.drift === "right" && !root.paused ? root.driftLineWidth : root.lineWidth,
                    root.paused)
            }
        }
        // gap to the vehicle ahead
        ShapePath {
            strokeColor: root.lead ? Theme.warning : "transparent"
            strokeWidth: 3
            strokeStyle: ShapePath.DashLine
            dashPattern: [1.3, 2]
            fillColor: "transparent"
            startX: 220; startY: 100
            PathLine { x: 220; y: 132 }
        }
    }

    // vehicle ahead: a far-away silhouette in red
    CarRear {
        visible: root.lead
        x: 220 - width / 2
        y: 56
        scale: 0.3
        transformOrigin: Item.Top
        body: Theme.warning
        glass: "#5A1410"
        trim: "#B8382C"
        tail: "#5A1410"
        indicator: "#5A1410"
        reverse: "#5A1410"
        details: false
    }

    // our car (a W124), from behind and above, its wheels on the bottom edge
    CarRear {
        x: 220 - width / 2 + root.carShift
        y: 130
        body: root.paused ? Theme.lineOff : Theme.car
        trim: root.paused ? "#3A4148" : "#9AA2A9"
        tail: root.paused ? "#3A4148" : "#B3261E"
        indicator: root.paused ? "#3A4148" : "#D98A1C"
        reverse: root.paused ? "#4A525A" : "#D7DCE0"
        plate: root.paused ? "#5B636B" : "#F5F7F8"
        Behavior on x { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
    }
}
