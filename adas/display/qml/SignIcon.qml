import QtQuick

// A round regulatory sign (red ring on white): a speed limit, no overtaking,
// or any other sign id drawn as a short label.
Item {
    id: root
    property string kind: "limit"   // "limit", "no_overtaking" or any sign id
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

    // No overtaking: a black car beside a red one.
    Item {
        visible: root.kind === "no_overtaking"
        anchors.fill: parent
        Rectangle { x: 26 * root.u; y: 37 * root.u; width: 16 * root.u; height: 10 * root.u; radius: 3 * root.u; color: "#111111" }
        Rectangle { x: 22 * root.u; y: 45 * root.u; width: 24 * root.u; height: 15 * root.u; radius: 4 * root.u; color: "#111111" }
        Rectangle { x: 58 * root.u; y: 37 * root.u; width: 16 * root.u; height: 10 * root.u; radius: 3 * root.u; color: Theme.signRed }
        Rectangle { x: 54 * root.u; y: 45 * root.u; width: 24 * root.u; height: 15 * root.u; radius: 4 * root.u; color: Theme.signRed }
    }

    Text {
        visible: root.kind !== "limit" && root.kind !== "no_overtaking"
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
