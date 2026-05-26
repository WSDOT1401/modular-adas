import QtQuick

Item {
    id: root

    property real speed: 0
    property string unitText: "km/h"
    property string fontFamily: "Sans Serif"

    readonly property real s: Math.min(width, height) / 560

    // Center CarPlay placeholder rectangle
    Rectangle {
        id: carplayPlaceholder
        width: 386 * root.s
        height: 238 * root.s
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: -26 * root.s
        color: "#1a1816"
        border.color: "#2e2b28"
        border.width: 2 * root.s
        radius: 10 * root.s

        Rectangle {
            width: 2 * root.s
            height: parent.height - 36 * root.s
            anchors.left: parent.left
            anchors.leftMargin: 24 * root.s
            anchors.verticalCenter: parent.verticalCenter
            color: "#5b5650"
            opacity: 0.38
        }

        Rectangle {
            width: 3 * root.s
            height: parent.height * 0.84
            radius: width / 2
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.horizontalCenterOffset: 22 * root.s
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: 6 * root.s
            rotation: -29
            color: "#d9d2c8"
            opacity: 0.34
        }

        Rectangle {
            width: 3 * root.s
            height: parent.height * 0.54
            radius: width / 2
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.horizontalCenterOffset: 50 * root.s
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -16 * root.s
            rotation: 33
            color: "#e8e1d6"
            opacity: 0.34
        }
    }

    // Large digital speed below the placeholder
    Item {
        id: speedReadout
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: carplayPlaceholder.bottom
        anchors.topMargin: 8 * root.s
        width: 250 * root.s
        height: 76 * root.s

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
}
