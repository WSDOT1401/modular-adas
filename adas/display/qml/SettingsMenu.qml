import QtQuick

// Settings, driven entirely by the rotary encoder (or the arrow keys):
// turn to move, press to change, hold to close.
Rectangle {
    id: root
    property bool roundShape: true
    property bool demoOn: false
    signal toggleShape()
    signal toggleDemo()
    signal closeRequested()

    property int index: 0
    readonly property var items: [
        { key: "shape", label: "Screen shape", value: roundShape ? "Round" : "4:3" },
        { key: "demo", label: "Demo scenarios", value: demoOn ? "On" : "Off" },
        { key: "close", label: "Close", value: "" }
    ]

    function handle(name) {
        if (name === "rotate_cw") index = (index + 1) % items.length
        else if (name === "rotate_ccw") index = (index + items.length - 1) % items.length
        else if (name === "press") activate(items[index].key)
    }
    function activate(key) {
        if (key === "shape") toggleShape()
        else if (key === "demo") toggleDemo()
        else closeRequested()
    }
    onVisibleChanged: if (visible) index = 0

    width: 460
    height: column.implicitHeight + 48
    radius: 20
    color: "#14191E"
    border.color: "#2A3138"
    border.width: 2

    Column {
        id: column
        x: 24
        y: 24
        width: parent.width - 48
        spacing: 6
        Text {
            text: "SETTINGS"
            color: Theme.textDim
            font.pixelSize: 14
            font.letterSpacing: 1.7
            bottomPadding: 6
        }
        Repeater {
            model: root.items
            delegate: Rectangle {
                required property var modelData
                required property int index
                width: column.width
                height: 56
                radius: 12
                color: index === root.index ? "#E6EBEF" : "transparent"
                Text {
                    x: 18
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.label
                    color: index === root.index ? "#0A0D10" : Theme.text
                    font.pixelSize: 22
                    font.weight: Font.Medium
                }
                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 18
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.value
                    color: index === root.index ? "#0A0D10" : Theme.textDim
                    font.pixelSize: 20
                }
            }
        }
        Text {
            width: column.width
            topPadding: 8
            horizontalAlignment: Text.AlignHCenter
            text: "Turn to choose · press to change · hold to close"
            color: Theme.textDim
            font.pixelSize: 15
        }
    }
}
