import QtQuick
import QtQuick.Shapes

// One safety feature and whether it is working, in the style of a dashboard
// telltale. The pictures follow what carmakers converge on:
//   lane   lane departure warning: our car from behind, between two lane lines
//   fcw    forward collision warning: a car with an impact burst ahead of it
//   signs  traffic sign recognition: a round regulatory sign read by a camera
// and the colours follow the usual telltale convention:
//   on      green  the feature is switched on and working
//   paused  amber  switched on but unavailable right now (camera blocked, ...)
//   off     grey, struck through   switched off by the driver
// Drawn on a 64×64 grid; set `size`.
Item {
    id: root
    property string feature: "lane"   // "lane", "fcw" or "signs"
    property string status: "on"      // "on", "paused" or "off"
    property real size: 64
    property color bg: Theme.bg       // behind the icon: used to cut details out

    width: size
    height: size

    readonly property color c: status === "on" ? Theme.active
                             : status === "paused" ? Theme.caution : Theme.muted

    Item {
        width: 64
        height: 64
        scale: root.size / 64
        transformOrigin: Item.TopLeft

        // ---- lane departure warning ------------------------------------
        Shape {
            anchors.fill: parent
            visible: root.feature === "lane"
            layer.enabled: true
            layer.samples: 4
            ShapePath {   // lane lines, converging toward the horizon
                strokeColor: root.c; strokeWidth: 4.5; fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                startX: 18; startY: 6
                PathLine { x: 6; y: 58 }
                PathMove { x: 46; y: 6 }
                PathLine { x: 58; y: 58 }
            }
            ShapePath {   // our car from behind
                strokeColor: "transparent"; fillColor: root.c
                joinStyle: ShapePath.RoundJoin
                startX: 25; startY: 25
                PathLine { x: 39; y: 25 }
                PathLine { x: 42.5; y: 34 }
                PathLine { x: 45; y: 35 }
                PathLine { x: 45; y: 48 }
                PathLine { x: 19; y: 48 }
                PathLine { x: 19; y: 35 }
                PathLine { x: 21.5; y: 34 }
                PathLine { x: 25; y: 25 }
            }
            ShapePath {   // wheels
                strokeColor: "transparent"; fillColor: root.c
                startX: 20.5; startY: 48
                PathLine { x: 26.5; y: 48 }
                PathLine { x: 26.5; y: 53 }
                PathLine { x: 20.5; y: 53 }
                PathLine { x: 20.5; y: 48 }
                PathMove { x: 37.5; y: 48 }
                PathLine { x: 43.5; y: 48 }
                PathLine { x: 43.5; y: 53 }
                PathLine { x: 37.5; y: 53 }
                PathLine { x: 37.5; y: 48 }
            }
            ShapePath {   // rear window and tail lights, cut out
                strokeColor: "transparent"; fillColor: root.bg
                startX: 27.5; startY: 28
                PathLine { x: 36.5; y: 28 }
                PathLine { x: 38.8; y: 33 }
                PathLine { x: 25.2; y: 33 }
                PathLine { x: 27.5; y: 28 }
                PathMove { x: 21.5; y: 38 }
                PathLine { x: 27; y: 38 }
                PathLine { x: 27; y: 41 }
                PathLine { x: 21.5; y: 41 }
                PathLine { x: 21.5; y: 38 }
                PathMove { x: 37; y: 38 }
                PathLine { x: 42.5; y: 38 }
                PathLine { x: 42.5; y: 41 }
                PathLine { x: 37; y: 41 }
                PathLine { x: 37; y: 38 }
            }
        }

        // ---- forward collision warning ---------------------------------
        Shape {
            anchors.fill: parent
            visible: root.feature === "fcw"
            layer.enabled: true
            layer.samples: 4
            ShapePath {   // a car from the side, heading right
                strokeColor: "transparent"; fillColor: root.c
                joinStyle: ShapePath.RoundJoin
                startX: 3; startY: 44
                PathLine { x: 3; y: 35 }
                PathLine { x: 9; y: 32.5 }
                PathLine { x: 16; y: 23.5 }
                PathLine { x: 31; y: 23.5 }
                PathLine { x: 38.5; y: 32.5 }
                PathLine { x: 43; y: 34 }
                PathLine { x: 43; y: 44 }
                PathLine { x: 3; y: 44 }
            }
            ShapePath {   // windows and wheel arches, cut out
                strokeColor: "transparent"; fillColor: root.bg
                startX: 17.5; startY: 26.5
                PathLine { x: 23; y: 26.5 }
                PathLine { x: 23; y: 32 }
                PathLine { x: 13.2; y: 32 }
                PathLine { x: 17.5; y: 26.5 }
                PathMove { x: 25.5; y: 26.5 }
                PathLine { x: 30; y: 26.5 }
                PathLine { x: 34.5; y: 32 }
                PathLine { x: 25.5; y: 32 }
                PathLine { x: 25.5; y: 26.5 }
                PathMove { x: 20.5; y: 44 }
                PathAngleArc { centerX: 13; centerY: 44; radiusX: 7.5; radiusY: 7.5; startAngle: 0; sweepAngle: 360 }
                PathMove { x: 41.5; y: 44 }
                PathAngleArc { centerX: 34; centerY: 44; radiusX: 7.5; radiusY: 7.5; startAngle: 0; sweepAngle: 360 }
            }
            ShapePath {   // wheels
                strokeColor: "transparent"; fillColor: root.c
                startX: 18.5; startY: 44
                PathAngleArc { centerX: 13; centerY: 44; radiusX: 5.5; radiusY: 5.5; startAngle: 0; sweepAngle: 360 }
                PathMove { x: 39.5; y: 44 }
                PathAngleArc { centerX: 34; centerY: 44; radiusX: 5.5; radiusY: 5.5; startAngle: 0; sweepAngle: 360 }
            }
            ShapePath {   // the impact burst ahead of the nose
                strokeColor: root.c; strokeWidth: 3.5; fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                startX: 54; startY: 20.5
                PathLine { x: 54; y: 25.5 }
                PathMove { x: 54; y: 34.5 }
                PathLine { x: 54; y: 39.5 }
                PathMove { x: 44.5; y: 30 }
                PathLine { x: 49.5; y: 30 }
                PathMove { x: 58.5; y: 30 }
                PathLine { x: 63.5; y: 30 }
                PathMove { x: 47.3; y: 23.3 }
                PathLine { x: 50.8; y: 26.8 }
                PathMove { x: 57.2; y: 33.2 }
                PathLine { x: 60.7; y: 36.7 }
                PathMove { x: 60.7; y: 23.3 }
                PathLine { x: 57.2; y: 26.8 }
                PathMove { x: 50.8; y: 33.2 }
                PathLine { x: 47.3; y: 36.7 }
            }
        }

        // ---- traffic sign recognition ----------------------------------
        Shape {
            anchors.fill: parent
            visible: root.feature === "signs"
            layer.enabled: true
            layer.samples: 4
            ShapePath {   // the sign's ring
                strokeColor: root.c; strokeWidth: 6; fillColor: "transparent"
                PathAngleArc { centerX: 27; centerY: 28; radiusX: 19; radiusY: 19; startAngle: 0; sweepAngle: 360 }
            }
            ShapePath {   // space around the camera
                strokeColor: "transparent"; fillColor: root.bg
                startX: 64; startY: 48
                PathAngleArc { centerX: 49; centerY: 48; radiusX: 15; radiusY: 15; startAngle: 0; sweepAngle: 360 }
            }
            ShapePath {   // the camera reading it
                strokeColor: "transparent"; fillColor: root.c
                joinStyle: ShapePath.RoundJoin
                startX: 38; startY: 42
                PathLine { x: 44; y: 42 }
                PathLine { x: 46; y: 38.5 }
                PathLine { x: 52; y: 38.5 }
                PathLine { x: 54; y: 42 }
                PathLine { x: 60; y: 42 }
                PathLine { x: 60; y: 57 }
                PathLine { x: 38; y: 57 }
                PathLine { x: 38; y: 42 }
            }
            ShapePath {   // lens
                strokeColor: "transparent"; fillColor: root.bg
                startX: 54; startY: 49.5
                PathAngleArc { centerX: 49; centerY: 49.5; radiusX: 5; radiusY: 5; startAngle: 0; sweepAngle: 360 }
            }
            ShapePath {
                strokeColor: "transparent"; fillColor: root.c
                startX: 51.5; startY: 49.5
                PathAngleArc { centerX: 49; centerY: 49.5; radiusX: 2.5; radiusY: 2.5; startAngle: 0; sweepAngle: 360 }
            }
        }

        // ---- switched off: struck through ---------------------------------
        Shape {
            anchors.fill: parent
            visible: root.status === "off"
            layer.enabled: true
            layer.samples: 4
            ShapePath {
                strokeColor: root.bg; strokeWidth: 10; fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                startX: 6; startY: 6
                PathLine { x: 58; y: 58 }
            }
            ShapePath {
                strokeColor: root.c; strokeWidth: 4.5; fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                startX: 6; startY: 6
                PathLine { x: 58; y: 58 }
            }
        }
    }
}
