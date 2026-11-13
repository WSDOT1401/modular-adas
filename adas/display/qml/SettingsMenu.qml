import QtQuick

// Settings, driven entirely by the rotary encoder (or the arrow keys):
// turn to move, press to change, hold to close.
//
// The safety features come first, each with its icon: the driver switches
// them on and off here, one at a time.
Rectangle {
    id: root
    property bool laneOn: true
    property bool fcwOn: true
    property bool signsOn: true
    property bool roundShape: true
    property bool demoOn: false
    signal toggleFeature(string name)
    signal toggleShape()
    signal toggleDemo()
    signal closeRequested()

    property int index: 0
    readonly property var items: [
        { key: "lane", feature: "lane", label: "Lane departure", value: laneOn ? "On" : "Off", on: laneOn },
        { key: "fcw", feature: "fcw", label: "Forward collision", value: fcwOn ? "On" : "Off", on: fcwOn },
        { key: "signs", feature: "signs", label: "Sign recognition", value: signsOn ? "On" : "Off", on: signsOn },
        { key: "shape", feature: "", label: "Screen shape", value: roundShape ? "Round" : "4:3", on: true },
        { key: "demo", feature: "", label: "Demo scenarios", value: demoOn ? "On" : "Off", on: true },
        { key: "close", feature: "", label: "Close", value: "", on: true }
    ]

    function handle(name) {
        if (name === "rotate_cw") index = (index + 1) % items.length
        else if (name === "rotate_ccw") index = (index + items.length - 1) % items.length
        else if (name === "press") activate(items[index].key)
    }
    function activate(key) {
        if (key === "lane" || key === "fcw" || key === "signs") toggleFeature(key)
        else if (key === "shape") toggleShape()
        else if (key === "demo") toggleDemo()
        else closeRequested()
    }
    onVisibleChanged: if (visible) index = 0

    width: 480
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
        spacing: 4
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
                id: row
                required property var modelData
                required property int index
                readonly property bool current: index === root.index
                width: column.width
                height: 58
                radius: 12
                color: current ? "#E6EBEF" : "transparent"
                FeatureIcon {
                    visible: row.modelData.feature !== ""
                    x: 12
                    anchors.verticalCenter: parent.verticalCenter
                    size: 40
                    feature: row.modelData.feature
                    status: row.modelData.on ? "on" : "off"
                    bg: row.current ? "#E6EBEF" : "#14191E"   // the row behind it
                }
                Text {
                    x: row.modelData.feature !== "" ? 64 : 18
                    anchors.verticalCenter: parent.verticalCenter
                    text: row.modelData.label
                    color: row.current ? "#0A0D10" : Theme.text
                    font.pixelSize: 21
                    font.weight: Font.Medium
                }
                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 18
                    anchors.verticalCenter: parent.verticalCenter
                    text: row.modelData.value
                    color: row.current ? "#0A0D10"
                         : row.modelData.feature !== "" && row.modelData.on ? Theme.active
                         : Theme.textDim
                    font.pixelSize: 20
                    font.weight: Font.DemiBold
                }
            }
        }
    }
}
