import QtQuick

Item {
    id: panel

    // Two-way bindings to the gauge profile
    property int  selectedMaxSpeed: 260
    property string selectedUnit: "km/h"

    signal closed()

    // Dim overlay
    Rectangle {
        anchors.fill: parent
        color: "#000000"
        opacity: 0.72
    }

    // Card
    Rectangle {
        anchors.centerIn: parent
        width: Math.min(parent.width * 0.72, 440)
        height: col.implicitHeight + 48
        radius: 14
        color: "#1a1816"
        border.color: "#3a3632"
        border.width: 1

        Column {
            id: col
            anchors {
                top: parent.top
                left: parent.left
                right: parent.right
                topMargin: 24
                leftMargin: 24
                rightMargin: 24
            }
            spacing: 20

            // Title
            Text {
                text: "CLUSTER SETTINGS"
                color: "#8f8b85"
                font.pixelSize: 11
                font.letterSpacing: 3
                anchors.horizontalCenter: parent.horizontalCenter
            }

            // Hint
            Text {
                text: "Release spacebar to close"
                color: "#4f4a44"
                font.pixelSize: 9
                font.letterSpacing: 1.5
                anchors.horizontalCenter: parent.horizontalCenter
            }

            // ── Max speed section ──────────────────────────────────
            Text {
                text: "MAX SPEED"
                color: "#6f6b64"
                font.pixelSize: 9
                font.letterSpacing: 2
            }

            Flow {
                spacing: 8
                width: parent.width

                Repeater {
                    model: [180, 200, 220, 240, 260, 300]
                    delegate: SpeedButton {
                        label: modelData + ""
                        active: panel.selectedMaxSpeed === modelData
                        onClicked: panel.selectedMaxSpeed = modelData
                    }
                }
            }

            // ── Unit section ───────────────────────────────────────
            Text {
                text: "UNIT"
                color: "#6f6b64"
                font.pixelSize: 9
                font.letterSpacing: 2
            }

            Row {
                spacing: 8
                SpeedButton {
                    label: "km/h"
                    active: panel.selectedUnit === "km/h"
                    onClicked: panel.selectedUnit = "km/h"
                }
                SpeedButton {
                    label: "mph"
                    active: panel.selectedUnit === "mph"
                    onClicked: panel.selectedUnit = "mph"
                }
            }
        }
    }

    // ── Reusable button component (inline) ────────────────────────
    component SpeedButton: Rectangle {
        id: btn
        property string label: ""
        property bool active: false
        signal clicked()

        width: labelText.implicitWidth + 20
        height: 34
        radius: 6
        color: active ? "#ffa62f" : "#2a2724"
        border.color: active ? "#ffa62f" : "#4a4540"
        border.width: 1

        Text {
            id: labelText
            text: btn.label
            color: btn.active ? "#0e0d0c" : "#cfccc5"
            font.pixelSize: 13
            font.bold: btn.active
            anchors.centerIn: parent
        }

        MouseArea {
            anchors.fill: parent
            onClicked: btn.clicked()
        }
    }
}
