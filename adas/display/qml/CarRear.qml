import QtQuick
import QtQuick.Shapes

// Our car from behind and a little above, drawn from a W124 saloon but with
// no badges: a thin roof over a very large rear window, a broad boot lid
// whose shut lines run down to the inner corners of the tail lamps, lamps
// with a slanted inner edge (smoked top, ribbed red below), a body-coloured
// bumper and the tyres showing beneath it.
// Drawn on a 160×130 grid; set `scale` to resize.
Item {
    id: root
    property color body: Theme.car
    property color glass: "#1B2229"
    property color trim: "#9AA2A9"        // plate surround strip
    property color tail: "#B3261E"        // tail lamps
    property color plate: "#F5F7F8"       // number plate
    property bool details: true           // ribs, plate, mirrors, shut lines, exhaust (off when tiny)

    width: 160
    height: 130

    // Faces pointing back are a shade darker than faces pointing up, which
    // is what gives the car depth.
    readonly property color face: Qt.darker(body, 1.1)
    readonly property color seam: Qt.darker(body, 1.4)
    readonly property color smoke: Qt.darker(tail, 2.4)
    readonly property color rib: Qt.darker(tail, 1.6)
    readonly property color tyre: "#2A3036"
    readonly property color tyreEdge: "#3C444C"

    // ---- the parts that come in mirrored pairs: tyre, mirror
    Repeater {
        model: 2
        Item {
            width: root.width
            height: root.height
            transform: Scale { origin.x: 80; xScale: index === 0 ? 1 : -1 }

            // tyre, below the bumper at the very edge of the car
            Rectangle {
                x: 1; y: 106; width: 21; height: 22; radius: 4
                color: root.tyre
                border.color: root.tyreEdge
                border.width: 1
            }
            // door mirror, on a short stalk off the C-pillar
            Rectangle {
                visible: root.details
                x: 8; y: 28; width: 12; height: 9; radius: 2
                color: Qt.darker(root.body, 1.8)
            }
        }
    }

    Shape {
        anchors.fill: parent
        layer.enabled: true
        layer.samples: 4

        // the body: roof, C-pillars, shoulders, flat sides
        ShapePath {
            strokeColor: "transparent"
            fillColor: root.body
            startX: 37; startY: 0
            PathLine { x: 123; y: 0 }
            PathQuad { x: 126; y: 3; controlX: 125.5; controlY: 0.5 }
            PathLine { x: 145.5; y: 38.5 }
            PathQuad { x: 156.5; y: 46; controlX: 154; controlY: 40.5 }
            PathLine { x: 158.5; y: 90 }
            PathLine { x: 1.5; y: 90 }
            PathLine { x: 3.5; y: 46 }
            PathQuad { x: 14.5; y: 38.5; controlX: 6; controlY: 40.5 }
            PathLine { x: 34; y: 3 }
            PathQuad { x: 37; y: 0; controlX: 34.5; controlY: 0.5 }
        }
        // the panel below the boot lid, facing straight back
        ShapePath {
            strokeColor: "transparent"
            fillColor: root.face
            startX: 3.8; startY: 81.2
            PathLine { x: 156.2; y: 81.2 }
            PathLine { x: 158.5; y: 90 }
            PathLine { x: 1.5; y: 90 }
            PathLine { x: 3.8; y: 81.2 }
        }
        // rear window: nearly the whole width of the cabin
        ShapePath {
            strokeColor: "transparent"
            fillColor: root.glass
            startX: 35; startY: 6.5
            PathQuad { x: 125; y: 6.5; controlX: 80; controlY: 5.2 }
            PathLine { x: 141.5; y: 37 }
            PathQuad { x: 18.5; y: 37; controlX: 80; controlY: 38.2 }
            PathLine { x: 35; y: 6.5 }
        }
    }

    // ---- tail lamps and shut lines (left drawn, right mirrored)
    Repeater {
        model: 2
        Shape {
            width: root.width
            height: root.height
            layer.enabled: true
            layer.samples: 4
            transform: Scale { origin.x: 80; xScale: index === 0 ? 1 : -1 }

            // shut line: from under the window, down the lamp's inner edge,
            // then along the bottom of the lid
            ShapePath {
                strokeColor: root.details ? root.seam : "transparent"
                strokeWidth: 1.1
                fillColor: "transparent"
                startX: 15.5; startY: 41
                PathQuad { x: 27.5; y: 62.5; controlX: 19; controlY: 52 }
                PathLine { x: 39.5; y: 81.2 }
                PathLine { x: 80; y: 81.2 }
            }
            // lamp, smoked top part
            ShapePath {
                strokeColor: "transparent"
                fillColor: root.smoke
                startX: 5; startY: 63.3
                PathLine { x: 26.5; y: 63.3 }
                PathLine { x: 31.3; y: 70.5 }
                PathLine { x: 4.7; y: 70.5 }
                PathLine { x: 5; y: 63.3 }
            }
            // lamp, red lower part
            ShapePath {
                strokeColor: "transparent"
                fillColor: root.tail
                startX: 4.7; startY: 70.5
                PathLine { x: 31.3; y: 70.5 }
                PathLine { x: 38.5; y: 81.2 }
                PathLine { x: 4.3; y: 81.2 }
                PathLine { x: 4.7; y: 70.5 }
            }
            // the ribs across the red
            ShapePath {
                strokeColor: root.details ? root.rib : "transparent"
                strokeWidth: 1.1
                fillColor: "transparent"
                startX: 4.6; startY: 74
                PathLine { x: 33.6; y: 74 }
                PathMove { x: 4.5; y: 77.6 }
                PathLine { x: 36; y: 77.6 }
            }
        }
    }

    // plate, in its recess, under a bright strip
    Rectangle {
        visible: root.details
        x: 47; y: 61.5; width: 66; height: 1.6; radius: 0.8
        color: root.trim
    }
    Rectangle {
        visible: root.details
        x: 53; y: 64.5; width: 54; height: 14.5; radius: 1.5
        color: root.seam
        Rectangle {
            anchors.centerIn: parent
            width: 48; height: 10.5; radius: 1
            color: root.plate
        }
    }

    // bumper: body-coloured, with a crease and a darker lower band
    Rectangle {
        x: 0; y: 89; width: 160; height: 25.5; radius: 5
        color: root.face
        Rectangle { x: 4; y: 3.5; width: parent.width - 8; height: 1; color: root.seam; opacity: 0.6 }
        Rectangle {
            x: 3; y: 17.5; width: parent.width - 6; height: 7; radius: 3
            color: Qt.darker(root.face, 1.15)
        }
    }

    // exhaust, left only
    Rectangle {
        visible: root.details
        x: 25; y: 113; width: 10; height: 6; radius: 3
        color: root.tyreEdge
        Rectangle { anchors.centerIn: parent; width: 6; height: 3; radius: 1.5; color: "#0E1216" }
    }
}
