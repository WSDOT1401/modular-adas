import QtQuick
import QtQuick.Shapes

// The GPS the speed comes from, as a crosshair (the usual "location" mark):
//   ok       green, centre dot: locked, the speed is live
//   no_fix   amber, no dot, slow pulse: talking, still searching for satellites
//   no_data  grey, struck through: nothing from the module (a wire off, no
//            power, its reader stopped)
//   ""       hidden: no GPS heard since start-up (bench, demo)
// Drawn on a 64×64 grid; set `size`.
Item {
    id: root
    property string status: ""
    property real size: 64
    property color bg: Theme.bg       // behind the icon: cuts the gap round the slash

    width: size
    height: size
    visible: status !== ""

    property color c: status === "ok" ? Theme.active
                    : status === "no_fix" ? Theme.caution : Theme.system
    Behavior on c { ColorAnimation { duration: 200; easing.type: Easing.OutCubic } }

    property real dot: status === "ok" ? 1 : 0
    Behavior on dot { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

    // Searching: a slow breath, so the amber reads as "working on it".
    SequentialAnimation on opacity {
        running: root.status === "no_fix"
        loops: Animation.Infinite
        alwaysRunToEnd: false
        NumberAnimation { to: 0.45; duration: 1100; easing.type: Easing.InOutSine }
        NumberAnimation { to: 1.0; duration: 1100; easing.type: Easing.InOutSine }
        onRunningChanged: if (!running) root.opacity = 1
    }

    // A lock gets one small pop.
    property bool _ready: false
    Component.onCompleted: _ready = true
    onStatusChanged: if (_ready && status === "ok") pop.restart()
    SequentialAnimation {
        id: pop
        NumberAnimation { target: popper; property: "scale"; to: 1.18; duration: 110; easing.type: Easing.OutCubic }
        NumberAnimation { target: popper; property: "scale"; to: 1.0; duration: 170; easing.type: Easing.InOutQuad }
    }

    Item {
        id: popper
        anchors.fill: parent

        Shape {
            width: 64
            height: 64
            scale: root.size / 64
            transformOrigin: Item.TopLeft
            layer.enabled: true
            layer.samples: 4

            ShapePath {   // ring
                strokeColor: root.c; strokeWidth: 5; fillColor: "transparent"
                PathAngleArc { centerX: 32; centerY: 32; radiusX: 15; radiusY: 15; startAngle: 0; sweepAngle: 360 }
            }
            ShapePath {   // four ticks
                strokeColor: root.c; strokeWidth: 5; fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                PathMove { x: 32; y: 4 }   PathLine { x: 32; y: 13 }
                PathMove { x: 32; y: 51 }  PathLine { x: 32; y: 60 }
                PathMove { x: 4; y: 32 }   PathLine { x: 13; y: 32 }
                PathMove { x: 51; y: 32 }  PathLine { x: 60; y: 32 }
            }
            ShapePath {   // centre dot: the fix
                strokeColor: "transparent"
                fillColor: Qt.rgba(root.c.r, root.c.g, root.c.b, root.dot)
                PathAngleArc { centerX: 32; centerY: 32; radiusX: 6.5 * root.dot + 0.01; radiusY: 6.5 * root.dot + 0.01; startAngle: 0; sweepAngle: 360 }
            }
        }

        Shape {   // not working: struck through
            visible: root.status === "no_data"
            width: 64
            height: 64
            scale: root.size / 64
            transformOrigin: Item.TopLeft
            layer.enabled: true
            layer.samples: 4

            ShapePath {   // gap round the slash
                strokeColor: root.bg; strokeWidth: 12; fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                startX: 9; startY: 9
                PathLine { x: 55; y: 55 }
            }
            ShapePath {   // the slash
                strokeColor: root.c; strokeWidth: 5; fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                startX: 9; startY: 9
                PathLine { x: 55; y: 55 }
            }
        }
    }
}
