import QtQuick
import QtQuick.Shapes

// Icons for the menu items that are not safety features, drawn in the same
// 64×64 grid and 4.5 stroke as FeatureIcon so the carousel reads as one set:
//   shape   a round screen beside a 4:3 one
//   demo    play, inside a ring
//   close   a chevron pointing back
Item {
    id: root
    property string kind: "close"
    property real size: 64
    property color color: Theme.text

    width: size
    height: size

    Shape {
        width: 64
        height: 64
        scale: root.size / 64
        transformOrigin: Item.TopLeft
        layer.enabled: true
        layer.samples: 4

        ShapePath {   // shape: the round screen
            strokeColor: root.kind === "shape" ? root.color : "transparent"
            strokeWidth: 4.5; fillColor: "transparent"
            PathAngleArc { centerX: 20; centerY: 32; radiusX: 14; radiusY: 14; startAngle: 0; sweepAngle: 360 }
        }
        ShapePath {   // shape: the 4:3 screen
            strokeColor: root.kind === "shape" ? root.color : "transparent"
            strokeWidth: 4.5; fillColor: "transparent"; joinStyle: ShapePath.RoundJoin
            startX: 40; startY: 21
            PathLine { x: 60; y: 21 }
            PathLine { x: 60; y: 43 }
            PathLine { x: 40; y: 43 }
            PathLine { x: 40; y: 21 }
        }
        ShapePath {   // demo: the ring
            strokeColor: root.kind === "demo" ? root.color : "transparent"
            strokeWidth: 4.5; fillColor: "transparent"
            PathAngleArc { centerX: 32; centerY: 32; radiusX: 24; radiusY: 24; startAngle: 0; sweepAngle: 360 }
        }
        ShapePath {   // demo: play
            strokeColor: "transparent"
            fillColor: root.kind === "demo" ? root.color : "transparent"
            startX: 26; startY: 20
            PathLine { x: 44; y: 32 }
            PathLine { x: 26; y: 44 }
            PathLine { x: 26; y: 20 }
        }
        ShapePath {   // close: back chevron
            strokeColor: root.kind === "close" ? root.color : "transparent"
            strokeWidth: 5; fillColor: "transparent"
            capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
            startX: 38; startY: 14
            PathLine { x: 20; y: 32 }
            PathLine { x: 38; y: 50 }
        }
    }
}
