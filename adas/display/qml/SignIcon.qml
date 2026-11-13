import QtQuick
import QtQuick.Shapes

// A traffic sign as the driver knows it from the roadside: the display spells
// nothing out, so the shape, colour and symbol have to do all the work.
//
//   limit        white disc, red ring, the number (grey ring: not known)
//   stop         red octagon, STOP
//   prohibitory  white disc, red ring, black symbol, red slash
//                (no_left_turn, no_right_turn, no_right_u_turn)
//   no stopping  blue disc, red ring, red cross (no_stopping_parking)
//   mandatory    blue disc, white symbol (keep_left, keep_right,
//                keep_left_or_right, turn_left, turn_right, u_turn,
//                reserved_for_bus)
//   warning      yellow diamond, black border and symbol (left_curve,
//                right_curve, t_junction_left, t_junction_right,
//                pedestrian_crossing)
//
// Ids are the detector's classes (b01.pt). An id this file doesn't know is
// shown as a red ring with its name, so a new class still shows something.
// Drawn on a 100×100 grid; set `size`. Left/right pairs share one drawing,
// mirrored. Thailand drives on the left, so a U-turn bends right.
Item {
    id: root
    property string kind: "limit"   // "limit" or any sign id
    property int value: 0           // the number on a speed-limit sign
    property real size: 84
    property bool dim: false        // ring drawn grey when the value is stale/unknown

    width: size
    height: size

    readonly property string family: {
        if (kind === "limit" || Theme.isLimitSign(kind)) return "limit"
        switch (kind) {
        case "stop": return "stop"
        case "no_left_turn": case "no_right_turn": case "no_right_u_turn": return "prohibitory"
        case "no_stopping_parking": return "nostop"
        case "keep_left": case "keep_right": case "keep_left_or_right":
        case "turn_left": case "turn_right": case "u_turn": case "reserved_for_bus":
            return "mandatory"
        case "left_curve": case "right_curve": case "t_junction_left":
        case "t_junction_right": case "pedestrian_crossing":
            return "warning"
        default: return "unknown"
        }
    }
    // The symbol drawn inside, with left-hand variants drawn as mirrored
    // right-hand ones.
    readonly property string glyph: {
        switch (kind) {
        case "turn_left": case "turn_right": case "no_left_turn": case "no_right_turn": return "turn"
        case "keep_left": case "keep_right": return "keep"
        case "u_turn": case "no_right_u_turn": return "uturn"
        case "left_curve": case "right_curve": return "curve"
        case "t_junction_left": case "t_junction_right": return "junction"
        default: return kind
        }
    }
    readonly property bool mirrored: kind === "turn_left" || kind === "no_left_turn"
                                     || kind === "keep_left" || kind === "left_curve"
                                     || kind === "t_junction_left"

    readonly property color ink: family === "mandatory" ? "#FFFFFF" : "#111111"
    readonly property color blue: "#1E5BB8"
    readonly property color yellow: "#FFC20E"

    // Each Shape is antialiased in its own layer, as in the other icons, with
    // the texture at the final size so the 100-unit grid doesn't scale up
    // soft. (One layer round the whole sign came out on an opaque square.)
    Item {
        anchors.fill: parent

        Item {
            width: 100
            height: 100
            scale: root.size / 100
            transformOrigin: Item.TopLeft

            // ---- plates --------------------------------------------------
            Rectangle {   // round signs: disc
                visible: root.family !== "stop" && root.family !== "warning"
                anchors.fill: parent
                radius: 50
                antialiasing: true
                color: root.family === "mandatory" || root.family === "nostop" ? root.blue : "#FFFFFF"
            }
            Rectangle {   // round signs: red ring (mandatory signs have none)
                visible: root.family === "limit" || root.family === "prohibitory"
                         || root.family === "nostop" || root.family === "unknown"
                anchors.centerIn: parent
                width: 93; height: 93; radius: 46.5
                antialiasing: true
                color: "transparent"
                border.color: root.dim ? "#9AA3AB" : Theme.signRed
                border.width: 11
            }
            Rectangle {   // mandatory: a thin white rim, as on the real plate
                visible: root.family === "mandatory"
                anchors.centerIn: parent
                width: 92; height: 92; radius: 46
                antialiasing: true
                color: "transparent"
                border.color: "#FFFFFF"
                border.width: 2.5
            }
            Shape {   // stop: octagon with a white inner rim
                layer.enabled: true; layer.samples: 4; layer.textureSize: Qt.size(root.size, root.size)
                visible: root.family === "stop"
                anchors.fill: parent
                ShapePath {
                    fillColor: Theme.signRed; strokeColor: "transparent"
                    PathSvg { path: "M 30.9 3.8 L 69.1 3.8 L 96.2 30.9 L 96.2 69.1 L 69.1 96.2 L 30.9 96.2 L 3.8 69.1 L 3.8 30.9 Z" }
                }
                ShapePath {
                    fillColor: "transparent"; strokeColor: "#FFFFFF"; strokeWidth: 3
                    joinStyle: ShapePath.MiterJoin
                    PathSvg { path: "M 33.2 9.3 L 66.8 9.3 L 90.7 33.2 L 90.7 66.8 L 66.8 90.7 L 33.2 90.7 L 9.3 66.8 L 9.3 33.2 Z" }
                }
            }
            Shape {   // warning: yellow diamond, black border
                layer.enabled: true; layer.samples: 4; layer.textureSize: Qt.size(root.size, root.size)
                visible: root.family === "warning"
                anchors.fill: parent
                ShapePath {
                    fillColor: root.yellow; strokeColor: "transparent"
                    PathSvg { path: "M 50 1 L 99 50 L 50 99 L 1 50 Z" }
                }
                ShapePath {
                    fillColor: "transparent"; strokeColor: "#111111"; strokeWidth: 4.5
                    joinStyle: ShapePath.RoundJoin
                    PathSvg { path: "M 50 8 L 92 50 L 50 92 L 8 50 Z" }
                }
            }

            // ---- symbols -------------------------------------------------
            Item {
                anchors.fill: parent
                transform: Scale { origin.x: 50; xScale: root.mirrored ? -1 : 1 }

                Shape {   // turn right: up, then round to the right
                    layer.enabled: true; layer.samples: 4; layer.textureSize: Qt.size(root.size, root.size)
                    visible: root.glyph === "turn"
                    anchors.fill: parent
                    ShapePath {
                        strokeColor: root.ink; strokeWidth: 9; fillColor: "transparent"
                        capStyle: ShapePath.FlatCap; joinStyle: ShapePath.RoundJoin
                        PathSvg { path: "M 40 78 L 40 52 Q 40 39 53 39 L 60 39" }
                    }
                    ShapePath {
                        strokeColor: "transparent"; fillColor: root.ink
                        PathSvg { path: "M 58 25 L 76 39 L 58 53 Z" }
                    }
                }
                Shape {   // keep right: down and to the right
                    layer.enabled: true; layer.samples: 4; layer.textureSize: Qt.size(root.size, root.size)
                    visible: root.glyph === "keep"
                    anchors.fill: parent
                    ShapePath {
                        strokeColor: root.ink; strokeWidth: 9; fillColor: "transparent"
                        capStyle: ShapePath.FlatCap
                        PathSvg { path: "M 32 30 L 60 58" }
                    }
                    ShapePath {
                        strokeColor: "transparent"; fillColor: root.ink
                        PathSvg { path: "M 72 46 L 72 72 L 46 72 Z" }
                    }
                }
                Shape {   // keep left or right: one stem, two ways down
                    layer.enabled: true; layer.samples: 4; layer.textureSize: Qt.size(root.size, root.size)
                    visible: root.glyph === "keep_left_or_right"
                    anchors.fill: parent
                    ShapePath {
                        strokeColor: root.ink; strokeWidth: 8; fillColor: "transparent"
                        capStyle: ShapePath.FlatCap; joinStyle: ShapePath.MiterJoin
                        PathSvg { path: "M 50 20 L 50 44 L 35 59 M 50 44 L 65 59" }
                    }
                    ShapePath {
                        strokeColor: "transparent"; fillColor: root.ink
                        PathSvg { path: "M 24 76 L 24 54 L 46 76 Z M 76 76 L 76 54 L 54 76 Z" }
                    }
                }
                Shape {   // U-turn: up on the left, over, back down on the right
                    layer.enabled: true; layer.samples: 4; layer.textureSize: Qt.size(root.size, root.size)
                    visible: root.glyph === "uturn"
                    anchors.fill: parent
                    ShapePath {
                        strokeColor: root.ink; strokeWidth: 9; fillColor: "transparent"
                        capStyle: ShapePath.FlatCap
                        PathSvg { path: "M 37 78 L 37 45 A 13 13 0 0 1 63 45 L 63 56" }
                    }
                    ShapePath {
                        strokeColor: "transparent"; fillColor: root.ink
                        PathSvg { path: "M 50 54 L 76 54 L 63 72 Z" }
                    }
                }
                Shape {   // bend to the right
                    layer.enabled: true; layer.samples: 4; layer.textureSize: Qt.size(root.size, root.size)
                    visible: root.glyph === "curve"
                    anchors.fill: parent
                    ShapePath {
                        strokeColor: root.ink; strokeWidth: 8; fillColor: "transparent"
                        capStyle: ShapePath.FlatCap
                        PathSvg { path: "M 42 74 L 42 54 Q 42 40 56 40 L 58 40" }
                    }
                    ShapePath {
                        strokeColor: "transparent"; fillColor: root.ink
                        PathSvg { path: "M 56 29 L 71 40 L 56 51 Z" }
                    }
                }
                Shape {   // side road joining from the right
                    layer.enabled: true; layer.samples: 4; layer.textureSize: Qt.size(root.size, root.size)
                    visible: root.glyph === "junction"
                    anchors.fill: parent
                    ShapePath {
                        strokeColor: root.ink; strokeWidth: 9; fillColor: "transparent"
                        capStyle: ShapePath.FlatCap
                        PathSvg { path: "M 44 25 L 44 75 M 44 50 L 70 50" }
                    }
                }
                Item {   // pedestrian crossing: a person walking over stripes
                    visible: root.glyph === "pedestrian_crossing"
                    anchors.fill: parent
                    Rectangle { x: 46; y: 21; width: 10; height: 10; radius: 5; color: root.ink; antialiasing: true }
                    Shape {
                        layer.enabled: true; layer.samples: 4; layer.textureSize: Qt.size(root.size, root.size)
                        anchors.fill: parent
                        ShapePath {
                            strokeColor: root.ink; strokeWidth: 5.5; fillColor: "transparent"
                            capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
                            PathSvg { path: "M 50 35 L 46 52 L 39 66 M 46 52 L 54 59 L 56 67 M 49 39 L 39 47 M 49 39 L 60 46" }
                        }
                    }
                    Repeater {
                        model: [38, 50, 62]
                        Rectangle {
                            required property int modelData
                            x: modelData - 4; y: 72; width: 8; height: 4; color: root.ink
                        }
                    }
                }
                Shape {   // no stopping: red cross on blue
                    layer.enabled: true; layer.samples: 4; layer.textureSize: Qt.size(root.size, root.size)
                    visible: root.family === "nostop"
                    anchors.fill: parent
                    ShapePath {
                        strokeColor: Theme.signRed; strokeWidth: 11; fillColor: "transparent"
                        capStyle: ShapePath.FlatCap
                        PathSvg { path: "M 20 20 L 80 80 M 80 20 L 20 80" }
                    }
                }
            }

            // ---- words -----------------------------------------------------
            Text {
                visible: root.family === "stop"
                anchors.centerIn: parent
                text: "STOP"
                font.pixelSize: 25
                font.weight: Font.Bold
                color: "#FFFFFF"
            }
            Text {
                visible: root.kind === "reserved_for_bus"
                anchors.centerIn: parent
                text: "BUS"
                font.pixelSize: 26
                font.weight: Font.Bold
                color: "#FFFFFF"
            }
            Text {
                visible: root.family === "limit"
                anchors.centerIn: parent
                text: root.value > 0 ? root.value : "–"
                font.pixelSize: 38
                font.weight: Font.DemiBold
                color: "#111111"
            }
            Text {
                visible: root.family === "unknown"
                anchors.centerIn: parent
                width: 60
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                text: Theme.signLabel(root.kind)
                font.pixelSize: 13
                font.weight: Font.DemiBold
                color: "#111111"
            }

            // prohibitory: the red slash goes over the symbol, top-left to bottom-right
            Rectangle {
                visible: root.family === "prohibitory"
                anchors.centerIn: parent
                width: 9; height: 86
                rotation: -45
                antialiasing: true
                color: Theme.signRed
            }
        }
    }
}
