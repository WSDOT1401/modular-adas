import QtQuick
import QtQuick.Shapes

// A Mercedes W124 saloon seen from behind and about 30° above. What makes it
// read as a W124: the wide, horizontally ribbed tail lamps; the boot lid that
// drops between them to the bumper, with the plate in a recess; the star on
// the lid; a thick ribbed bumper; a flat roof over a big rear window.
// Drawn on a 160×130 grid; set `scale` to resize.
Item {
    id: root
    property color body: Theme.car
    property color glass: "#1B2229"
    property color trim: "#9AA2A9"        // bumper, star, shut lines
    property color tail: "#B3261E"        // tail lamps
    property color indicator: "#D98A1C"   // amber segment of each lamp
    property color reverse: "#D7DCE0"     // reversing-light segment
    property color plate: "#F5F7F8"       // number plate
    property bool details: true           // ribs, plate, star, mirrors, shut lines (off when tiny)

    width: 160
    height: 130

    // Vertical faces are a shade darker than the ones facing up, which is
    // what gives the car its depth.
    readonly property color face: Qt.darker(body, 1.12)
    readonly property color recess: Qt.darker(body, 1.35)
    readonly property color rib: Qt.darker(tail, 1.7)

    // tyres, under the bumper
    Rectangle { x: 16; y: 106; width: 26; height: 22; radius: 5; color: "#101418" }
    Rectangle { x: 118; y: 106; width: 26; height: 22; radius: 5; color: "#101418" }

    // door mirrors, wider than the cabin
    Rectangle { visible: root.details; x: 12; y: 44; width: 16; height: 9; radius: 3; color: root.face }
    Rectangle { visible: root.details; x: 132; y: 44; width: 16; height: 9; radius: 3; color: root.face }

    Shape {
        anchors.fill: parent
        layer.enabled: true
        layer.samples: 4

        // cabin: flat roof, thin C-pillars
        ShapePath {
            strokeColor: "transparent"
            fillColor: root.body
            startX: 46; startY: 8
            PathLine { x: 114; y: 8 }
            PathLine { x: 134; y: 54 }
            PathLine { x: 26; y: 54 }
            PathLine { x: 46; y: 8 }
        }
        // rear window, gently curved top and bottom
        ShapePath {
            strokeColor: "transparent"
            fillColor: root.glass
            startX: 46; startY: 19
            PathQuad { x: 114; y: 19; controlX: 80; controlY: 15 }
            PathLine { x: 127; y: 49 }
            PathQuad { x: 33; y: 49; controlX: 80; controlY: 51 }
            PathLine { x: 46; y: 19 }
        }
        // boot lid, the face pointing up
        ShapePath {
            strokeColor: "transparent"
            fillColor: root.body
            startX: 26; startY: 54
            PathLine { x: 134; y: 54 }
            PathLine { x: 154; y: 66 }
            PathLine { x: 6; y: 66 }
            PathLine { x: 26; y: 54 }
        }
        // tail panel, the face pointing back
        ShapePath {
            strokeColor: "transparent"
            fillColor: root.face
            startX: 6; startY: 66
            PathLine { x: 154; y: 66 }
            PathLine { x: 154; y: 100 }
            PathLine { x: 6; y: 100 }
            PathLine { x: 6; y: 66 }
        }
        // shut lines: across the top of the lamps, then down beside the
        // plate where the lid drops between them
        ShapePath {
            strokeColor: root.details ? root.recess : "transparent"
            strokeWidth: 1.2
            fillColor: "transparent"
            startX: 54; startY: 98
            PathLine { x: 54; y: 67.5 }
            PathLine { x: 106; y: 67.5 }
            PathLine { x: 106; y: 98 }
        }
        // the star: a ring with three spokes
        ShapePath {
            strokeColor: root.details ? root.trim : "transparent"
            strokeWidth: 1.2
            fillColor: "transparent"
            startX: 84.5; startY: 72.5
            PathArc { x: 75.5; y: 72.5; radiusX: 4.5; radiusY: 4.5; useLargeArc: true }
            PathArc { x: 84.5; y: 72.5; radiusX: 4.5; radiusY: 4.5; useLargeArc: true }
            PathMove { x: 80; y: 72.5 }
            PathLine { x: 80; y: 68 }
            PathMove { x: 80; y: 72.5 }
            PathLine { x: 76.1; y: 74.7 }
            PathMove { x: 80; y: 72.5 }
            PathLine { x: 83.9; y: 74.7 }
        }
    }

    // ---- tail lamps: wide, ribbed, with amber and reversing segments inboard
    Repeater {
        model: 2
        Item {
            readonly property bool leftLamp: index === 0
            x: leftLamp ? 9 : 108
            y: 69
            width: 43
            height: 25

            Rectangle { anchors.fill: parent; radius: 2; color: root.tail }
            // inboard column: indicator above, reversing light below
            Rectangle {
                visible: root.details
                x: parent.leftLamp ? parent.width - 12 : 0
                width: 12; height: parent.height / 2
                radius: 1.5
                color: root.indicator
            }
            Rectangle {
                visible: root.details
                x: parent.leftLamp ? parent.width - 12 : 0
                y: parent.height / 2
                width: 12; height: parent.height / 2
                radius: 1.5
                color: root.reverse
            }
            // the horizontal ribs
            Repeater {
                model: root.details ? 4 : 0
                Rectangle {
                    y: 4.2 + index * 5
                    width: parent.width
                    height: 1.2
                    color: root.rib
                    opacity: 0.7
                }
            }
        }
    }

    // plate, in its recess between the lamps
    Rectangle {
        visible: root.details
        x: 58; y: 78; width: 44; height: 20; radius: 2
        color: root.recess
        Rectangle {
            anchors.centerIn: parent
            width: 38; height: 14; radius: 1.5
            color: root.plate
            border.color: root.trim
            border.width: 1
        }
    }

    // bumper, full width, ribbed
    Rectangle {
        x: 3; y: 96; width: 154; height: 15; radius: 6
        color: root.trim
        Repeater {
            model: root.details ? 2 : 0
            Rectangle {
                x: 6; y: 5 + index * 4.5
                width: parent.width - 12; height: 1.2
                color: Qt.darker(root.trim, 1.3)
            }
        }
    }
}
