import QtQuick

// A round regulatory sign (red ring on white): a speed limit, or any other
// sign id drawn as a short label.
Item {
    id: root
    property string kind: "limit"   // "limit" or any sign id
    property int value: 0           // the number on a speed-limit sign
    property real size: 84
    property bool dim: false        // ring drawn grey when the value is stale/unknown

    width: size
    height: size
    readonly property real u: size / 100

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: "#FFFFFF"
    }
    Rectangle {
        anchors.centerIn: parent
        width: 93 * root.u
        height: width
        radius: width / 2
        color: "transparent"
        border.color: root.dim ? "#9AA3AB" : Theme.signRed
        border.width: 11 * root.u
    }

    Text {
        visible: root.kind === "limit"
        anchors.centerIn: parent
        text: root.value > 0 ? root.value : "–"
        font.pixelSize: 38 * root.u
        font.weight: Font.DemiBold
        color: "#111111"
    }

    Text {
        visible: root.kind !== "limit"
        anchors.centerIn: parent
        width: 60 * root.u
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        maximumLineCount: 2
        text: Theme.signLabel(root.kind)
        font.pixelSize: 13 * root.u
        font.weight: Font.DemiBold
        color: "#111111"
    }
}
