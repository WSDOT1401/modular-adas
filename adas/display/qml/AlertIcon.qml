import QtQuick
import QtQuick.Shapes

// Banner icon for the 4:3 layout: a triangle for caution/warning, an "i" for
// info. Nothing for "none" or "system" (the layouts draw CameraOffIcon).
Item {
    id: root
    property string level: "none"
    property color color: "white"
    width: 34
    height: 34

    Shape {
        anchors.fill: parent
        visible: root.level === "caution" || root.level === "warning"
        layer.enabled: true
        layer.samples: 4
        ShapePath {
            strokeColor: root.color
            strokeWidth: 3
            fillColor: "transparent"
            joinStyle: ShapePath.RoundJoin
            startX: 17; startY: 4
            PathLine { x: 32; y: 30 }
            PathLine { x: 2; y: 30 }
            PathLine { x: 17; y: 4 }
        }
    }
    Text {
        visible: root.level === "caution" || root.level === "warning"
        x: 0; y: 9; width: 34
        horizontalAlignment: Text.AlignHCenter
        text: "!"
        color: root.color
        font.pixelSize: 18
        font.weight: Font.Bold
    }

    Rectangle {
        visible: root.level === "info"
        anchors.fill: parent
        anchors.margins: 3
        radius: width / 2
        color: "transparent"
        border.color: root.color
        border.width: 3
        Text {
            anchors.centerIn: parent
            text: "i"
            color: root.color
            font.capitalization: Font.MixedCase
            font.pixelSize: 18
            font.weight: Font.Bold
        }
    }
}
