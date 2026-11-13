import QtQuick
import QtQuick.Shapes

// One safety feature and whether it is working, in the style of a dashboard
// telltale. The pictures are the ones drivers already know from production
// cars:
//   lane   lane departure warning: a car seen from above, angled across a
//          solid lane line, a dashed line on the other side
//   fcw    forward collision warning: two cars in outline from the side, an
//          impact star between them, an arrow for the gap closing
//   signs  traffic sign recognition: a speed-limit sign
// and the colours follow the usual telltale convention:
//   on      green  the feature is switched on and working
//   paused  amber  switched on but unavailable right now (camera blocked, ...)
//   off     grey, struck through   switched off by the driver
// Drawn on a 64×64 grid; set `size`.
//
// Changes of state are animated, so a switch reads as cause and effect:
// switching off draws the strike across while the colour fades to grey;
// switching on pulls the strike back, fills green and gives one small pop.
Item {
    id: root
    property string feature: "lane"   // "lane", "fcw" or "signs"
    property string status: "on"      // "on", "paused" or "off"
    property real size: 64
    property color bg: Theme.bg       // behind the icon: used to cut details out

    width: size
    height: size

    property color c: status === "on" ? Theme.active
                    : status === "paused" ? Theme.caution : Theme.muted
    Behavior on c { ColorAnimation { duration: 200; easing.type: Easing.OutCubic } }

    // How far the strike is drawn, 0..1. Drawing (off) takes a little longer
    // than retracting (on): the switch-off is the one worth seeing happen.
    property real strike: status === "off" ? 1 : 0
    Behavior on strike {
        NumberAnimation { duration: root.status === "off" ? 240 : 160; easing.type: Easing.OutCubic }
    }

    property bool _ready: false
    Component.onCompleted: _ready = true
    onStatusChanged: if (_ready && status === "on") pop.restart()

    SequentialAnimation {
        id: pop
        NumberAnimation { target: popper; property: "scale"; to: 1.14; duration: 110; easing.type: Easing.OutCubic }
        NumberAnimation { target: popper; property: "scale"; to: 1.0; duration: 170; easing.type: Easing.InOutQuad }
    }

    Item {
        id: popper
        anchors.fill: parent
        transformOrigin: Item.Center

        Item {
            id: grid
            width: 64
            height: 64
            scale: root.size / 64
            transformOrigin: Item.TopLeft

            // ---- lane departure warning ------------------------------------
            Item {
                anchors.fill: parent
                visible: root.feature === "lane"

                // dashed line on the left, solid line on the right
                Repeater {
                    model: [3, 18, 33, 48]
                    Rectangle {
                        required property int modelData
                        x: 8; y: modelData; width: 4.5; height: 9; radius: 1
                        color: root.c
                    }
                }
                Rectangle { x: 47.5; y: 2; width: 4.5; height: 60; radius: 1; color: root.c }

                // the car from above, nose up and to the right, across the line
                Item {
                    x: 37 - width / 2; y: 32 - height / 2
                    width: 19; height: 33
                    rotation: 28
                    antialiasing: true
                    Rectangle {   // a gap round the car where it crosses the line
                        x: -2.5; y: -2.5; width: parent.width + 5; height: parent.height + 5
                        radius: 8.5; color: root.bg; antialiasing: true
                    }
                    Rectangle {   // mirrors
                        x: -3.5; y: 9; width: parent.width + 7; height: 4; radius: 1.5
                        color: root.c; antialiasing: true
                    }
                    Rectangle {
                        anchors.fill: parent
                        radius: 6.5; color: root.c; antialiasing: true
                    }
                    Rectangle {   // windscreen
                        x: 3; y: 7; width: parent.width - 6; height: 7; radius: 2
                        color: root.bg; antialiasing: true
                    }
                    Rectangle {   // rear window
                        x: 3.5; y: parent.height - 9; width: parent.width - 7; height: 5; radius: 1.5
                        color: root.bg; antialiasing: true
                    }
                }
            }

            // ---- forward collision warning ---------------------------------
            Shape {
                anchors.fill: parent
                visible: root.feature === "fcw"
                layer.enabled: true
                layer.samples: 4

                ShapePath {   // our car, closing in from behind (front half)
                    strokeColor: root.c; strokeWidth: 3.2; fillColor: "transparent"
                    joinStyle: ShapePath.RoundJoin; capStyle: ShapePath.FlatCap
                    startX: 1; startY: 24.5
                    PathLine { x: 6; y: 24.5 }
                    PathLine { x: 11.5; y: 30.5 }
                    PathLine { x: 17; y: 31.5 }
                    PathQuad { x: 19.5; y: 35; controlX: 19.5; controlY: 31.5 }
                    PathLine { x: 19.5; y: 40 }
                    PathLine { x: 16.5; y: 40 }
                    PathArc { x: 9; y: 40; radiusX: 3.75; radiusY: 3.75; direction: PathArc.Counterclockwise }
                    PathLine { x: 1; y: 40 }
                }
                ShapePath {   // the car ahead
                    strokeColor: root.c; strokeWidth: 3.2; fillColor: "transparent"
                    joinStyle: ShapePath.RoundJoin
                    startX: 24.5; startY: 40
                    PathLine { x: 24.5; y: 33 }
                    PathQuad { x: 27; y: 30.5; controlX: 24.5; controlY: 30.5 }
                    PathLine { x: 32; y: 30.5 }
                    PathLine { x: 37.5; y: 24 }
                    PathLine { x: 49; y: 24 }
                    PathLine { x: 55; y: 30 }
                    PathLine { x: 60.5; y: 31 }
                    PathQuad { x: 62.5; y: 34; controlX: 62.5; controlY: 31 }
                    PathLine { x: 62.5; y: 40 }
                    PathLine { x: 59.5; y: 40 }
                    PathArc { x: 52; y: 40; radiusX: 3.75; radiusY: 3.75; direction: PathArc.Counterclockwise }
                    PathLine { x: 35; y: 40 }
                    PathArc { x: 27.5; y: 40; radiusX: 3.75; radiusY: 3.75; direction: PathArc.Counterclockwise }
                    PathLine { x: 24.5; y: 40 }
                }
                ShapePath {   // wheels
                    strokeColor: root.c; strokeWidth: 3.2; fillColor: "transparent"
                    startX: 15.25; startY: 41.5
                    PathAngleArc { centerX: 12.75; centerY: 41.5; radiusX: 2.5; radiusY: 2.5; startAngle: 0; sweepAngle: 360 }
                    PathMove { x: 33.75; y: 41.5 }
                    PathAngleArc { centerX: 31.25; centerY: 41.5; radiusX: 2.5; radiusY: 2.5; startAngle: 0; sweepAngle: 360 }
                    PathMove { x: 58.25; y: 41.5 }
                    PathAngleArc { centerX: 55.75; centerY: 41.5; radiusX: 2.5; radiusY: 2.5; startAngle: 0; sweepAngle: 360 }
                }
                ShapePath {   // the impact star, between them
                    strokeColor: "transparent"; fillColor: root.c
                    startX: 19.92; startY: 2.72
                    PathLine { x: 23.63; y: 8.85 }
                    PathLine { x: 30.66; y: 7.5 }
                    PathLine { x: 25.98; y: 12.92 }
                    PathLine { x: 29.43; y: 19.19 }
                    PathLine { x: 22.83; y: 16.41 }
                    PathLine { x: 17.93; y: 21.64 }
                    PathLine { x: 18.54; y: 14.5 }
                    PathLine { x: 12.05; y: 11.45 }
                    PathLine { x: 19.03; y: 9.82 }
                    PathLine { x: 19.92; y: 2.72 }
                }
                ShapePath {   // the gap closing
                    strokeColor: "transparent"; fillColor: root.c
                    startX: 29; startY: 54.5
                    PathLine { x: 37.5; y: 48 }
                    PathLine { x: 37.5; y: 51.8 }
                    PathLine { x: 51; y: 51.8 }
                    PathLine { x: 51; y: 57.2 }
                    PathLine { x: 37.5; y: 57.2 }
                    PathLine { x: 37.5; y: 61 }
                    PathLine { x: 29; y: 54.5 }
                }
            }

            // ---- traffic sign recognition: a speed-limit sign ----------------
            Item {
                anchors.fill: parent
                visible: root.feature === "signs"
                Rectangle {
                    anchors.centerIn: parent
                    width: 52; height: 52; radius: 26
                    color: "transparent"
                    border.width: 6.5
                    border.color: root.c
                    antialiasing: true
                }
                Text {
                    anchors.centerIn: parent
                    anchors.verticalCenterOffset: 0.5
                    text: "60"
                    color: root.c
                    font.pixelSize: 21
                    font.weight: Font.Bold
                    font.letterSpacing: -0.5
                }
            }

            // ---- switched off: struck through, drawn from the top left ----------
            Shape {
                anchors.fill: parent
                visible: root.strike > 0.01
                layer.enabled: true
                layer.samples: 4
                ShapePath {
                    strokeColor: root.bg; strokeWidth: 10; fillColor: "transparent"
                    capStyle: ShapePath.RoundCap
                    startX: 6; startY: 6
                    PathLine { x: 6 + 52 * root.strike; y: 6 + 52 * root.strike }
                }
                ShapePath {
                    strokeColor: root.c; strokeWidth: 4.5; fillColor: "transparent"
                    capStyle: ShapePath.RoundCap
                    startX: 6; startY: 6
                    PathLine { x: 6 + 52 * root.strike; y: 6 + 52 * root.strike }
                }
            }
        }
    }
}
