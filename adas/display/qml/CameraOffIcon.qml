import QtQuick
import QtQuick.Shapes

// A camera struck through: the camera can't see (blocked or not found), so
// the features that rely on it are paused. Drawn on a 64×64 grid; set `size`.
Item {
    id: root
    property real size: 64
    property color color: Theme.system
    property color bg: Theme.bg       // behind the icon: cuts the gap round the slash

    width: size
    height: size

    Shape {
        width: 64
        height: 64
        scale: root.size / 64
        transformOrigin: Item.TopLeft
        layer.enabled: true
        layer.samples: 4

        ShapePath {   // body with the viewfinder bump
            strokeColor: root.color; strokeWidth: 5; fillColor: "transparent"
            joinStyle: ShapePath.RoundJoin
            startX: 7; startY: 20
            PathLine { x: 21; y: 20 }
            PathLine { x: 25; y: 13 }
            PathLine { x: 39; y: 13 }
            PathLine { x: 43; y: 20 }
            PathLine { x: 57; y: 20 }
            PathLine { x: 57; y: 52 }
            PathLine { x: 7; y: 52 }
            PathLine { x: 7; y: 20 }
        }
        ShapePath {   // lens
            strokeColor: root.color; strokeWidth: 5; fillColor: "transparent"
            PathAngleArc { centerX: 32; centerY: 36; radiusX: 9.5; radiusY: 9.5; startAngle: 0; sweepAngle: 360 }
        }
        ShapePath {   // gap round the slash
            strokeColor: root.bg; strokeWidth: 12; fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            startX: 6; startY: 11
            PathLine { x: 58; y: 57 }
        }
        ShapePath {   // the slash
            strokeColor: root.color; strokeWidth: 5; fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            startX: 6; startY: 11
            PathLine { x: 58; y: 57 }
        }
    }
}
