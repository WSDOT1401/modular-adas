import QtQuick

Item {
    id: root

    property real speed: 0
    property string unitText: "km/h"
    property string fontFamily: "Sans Serif"
    property real scaleFactor: 1.0

    readonly property real s: scaleFactor

    width: 250 * s
    height: 76 * s

    Text {
        id: speedValue
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.horizontalCenterOffset: -18 * root.s
        anchors.bottom: parent.bottom
        text: Math.round(root.speed)
        color: "#efede8"
        font.pixelSize: Math.round(64 * root.s)
        font.family: root.fontFamily
        font.weight: Font.Light
    }

    Text {
        id: speedUnit
        anchors.left: parent.horizontalCenter
        anchors.leftMargin: 52 * root.s
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 8 * root.s
        text: root.unitText
        color: "#c8c1b8"
        font.pixelSize: Math.round(20 * root.s)
        font.family: root.fontFamily
        font.weight: Font.Medium
    }
}
