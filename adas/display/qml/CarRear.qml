import QtQuick
import QtQuick.Shapes

// A generic sedan seen from behind and about 30° above: roof and rear window
// foreshortened at the top, then boot lid, tail panel, bumper and tyres.
// Drawn on a 120×110 grid; set `scale` to resize.
Item {
    id: root
    property color body: Theme.car
    property color glass: "#1B2229"
    property color trim: "#9AA2A9"        // bumper, boot shut line
    property color tail: "#B3261E"        // tail lights
    property color plate: "#F5F7F8"       // number plate
    property bool details: true           // plate, mirrors, shut line (off when tiny)

    width: 120
    height: 110

    // tyres, peeking out under the bumper
    Rectangle { x: 12; y: 88; width: 20; height: 20; radius: 4; color: "#101418" }
    Rectangle { x: 88; y: 88; width: 20; height: 20; radius: 4; color: "#101418" }

    // mirrors
    Rectangle { visible: root.details; x: 4; y: 34; width: 12; height: 7; radius: 2; color: root.body }
    Rectangle { visible: root.details; x: 104; y: 34; width: 12; height: 7; radius: 2; color: root.body }

    Shape {
        anchors.fill: parent
        layer.enabled: true
        layer.samples: 4

        // cabin: roof narrowing away from us
        ShapePath {
            strokeColor: "transparent"
            fillColor: root.body
            joinStyle: ShapePath.RoundJoin
            startX: 30; startY: 4
            PathLine { x: 90; y: 4 }
            PathLine { x: 106; y: 48 }
            PathLine { x: 14; y: 48 }
            PathLine { x: 30; y: 4 }
        }
        // rear window
        ShapePath {
            strokeColor: "transparent"
            fillColor: root.glass
            startX: 27; startY: 15
            PathLine { x: 93; y: 15 }
            PathLine { x: 102; y: 44 }
            PathLine { x: 18; y: 44 }
            PathLine { x: 27; y: 15 }
        }
        // boot lid and tail panel
        ShapePath {
            strokeColor: "transparent"
            fillColor: root.body
            startX: 12; startY: 48
            PathLine { x: 108; y: 48 }
            PathLine { x: 115; y: 62 }
            PathLine { x: 115; y: 90 }
            PathLine { x: 5; y: 90 }
            PathLine { x: 5; y: 62 }
            PathLine { x: 12; y: 48 }
        }
        // boot shut line
        ShapePath {
            strokeColor: root.details ? root.trim : "transparent"
            strokeWidth: 1.5
            fillColor: "transparent"
            startX: 9; startY: 58
            PathLine { x: 111; y: 58 }
        }
    }

    // tail lights
    Rectangle { x: 7; y: 62; width: 28; height: 10; radius: 2; color: root.tail }
    Rectangle { x: 85; y: 62; width: 28; height: 10; radius: 2; color: root.tail }

    // number plate
    Rectangle {
        visible: root.details
        x: 45; y: 66; width: 30; height: 13; radius: 2
        color: root.plate
        border.color: root.trim
        border.width: 1
    }

    // bumper
    Rectangle { x: 3; y: 84; width: 114; height: 13; radius: 5; color: root.trim }
}
