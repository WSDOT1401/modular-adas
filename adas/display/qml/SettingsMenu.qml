import QtQuick

// Settings, driven entirely by the rotary encoder (or the arrow keys):
// turn to move, press to change, hold to close.
//
// The safety features come first, each with its icon: the driver switches
// them on and off here, one at a time.
//
// Motion: the highlight slides from row to row with each detent, so turning
// the knob feels connected to the screen. A switch animates in the icon
// itself (FeatureIcon); switching a feature ON also makes the highlight glow
// green for a moment: a safety feature coming back on gets the positive
// confirmation, switching one off stays clear but quiet.
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

    // Fixed rows: the values are looked up, not baked in, so a change
    // updates the row in place (rebuilding it would cut its animation off).
    readonly property var items: [
        { key: "lane", feature: "lane", label: "Lane departure" },
        { key: "fcw", feature: "fcw", label: "Forward collision" },
        { key: "signs", feature: "signs", label: "Sign recognition" },
        { key: "shape", feature: "", label: "Screen shape" },
        { key: "demo", feature: "", label: "Demo scenarios" },
        { key: "close", feature: "", label: "Close" }
    ]
    function isOn(key) {
        if (key === "lane") return laneOn
        if (key === "fcw") return fcwOn
        if (key === "signs") return signsOn
        if (key === "demo") return demoOn
        return true
    }
    function valueText(key) {
        if (key === "shape") return roundShape ? "Round" : "4:3"
        if (key === "close") return ""
        return isOn(key) ? "On" : "Off"
    }

    readonly property real rowHeight: 58
    readonly property real rowGap: 4
    readonly property color highlight: "#E6EBEF"
    readonly property color glow: "#C9F0D9"        // Theme.active, washed into the highlight
    readonly property color onText: "#17703F"      // Theme.active, dark enough for the highlight (5:1)

    function handle(name) {
        if (name === "rotate_cw") index = (index + 1) % items.length
        else if (name === "rotate_ccw") index = (index + items.length - 1) % items.length
        else if (name === "press") activate(items[index].key)
    }
    function activate(key) {
        if (key === "lane" || key === "fcw" || key === "signs") {
            const turningOn = !isOn(key)
            toggleFeature(key)
            if (turningOn) confirm.restart()
        }
        else if (key === "shape") toggleShape()
        else if (key === "demo") toggleDemo()
        else closeRequested()
    }
    onVisibleChanged: if (visible) index = 0

    width: 480
    height: title.height + rows.height + 54
    radius: 20
    color: "#14191E"
    border.color: "#2A3138"
    border.width: 2

    Text {
        id: title
        x: 24
        y: 24
        text: "SETTINGS"
        color: Theme.textDim
        font.pixelSize: 14
        font.letterSpacing: 1.7
    }

    Item {
        id: rows
        x: 24
        y: title.y + title.height + 12
        width: parent.width - 48
        height: root.items.length * (root.rowHeight + root.rowGap) - root.rowGap

        // The highlight, one shape that travels to the current row.
        Rectangle {
            id: bar
            width: parent.width
            height: root.rowHeight
            radius: 12
            y: root.index * (root.rowHeight + root.rowGap)
            color: root.highlight
            Behavior on y {
                enabled: root.visible
                NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
            }
            SequentialAnimation on color {
                id: confirm
                running: false
                ColorAnimation { to: root.glow; duration: 120; easing.type: Easing.OutCubic }
                ColorAnimation { to: root.highlight; duration: 280; easing.type: Easing.InOutQuad }
            }
        }

        Repeater {
            model: root.items
            delegate: Item {
                id: row
                required property var modelData
                required property int index
                readonly property bool current: index === root.index
                readonly property bool feature: modelData.feature !== ""
                readonly property bool on: root.isOn(modelData.key)
                y: index * (root.rowHeight + root.rowGap)
                width: rows.width
                height: root.rowHeight

                FeatureIcon {
                    visible: row.feature
                    x: 12
                    anchors.verticalCenter: parent.verticalCenter
                    size: 40
                    feature: row.modelData.feature || "lane"
                    status: row.on ? "on" : "off"
                    bg: row.current ? bar.color : root.color   // cut-outs match what is behind
                }
                Text {
                    x: row.feature ? 64 : 18
                    anchors.verticalCenter: parent.verticalCenter
                    text: row.modelData.label
                    color: row.current ? "#0A0D10" : Theme.text
                    Behavior on color { ColorAnimation { duration: 120 } }
                    font.pixelSize: 21
                    font.weight: Font.Medium
                }
                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 18
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.valueText(row.modelData.key)
                    color: row.feature && row.on ? (row.current ? root.onText : Theme.active)
                         : row.current ? "#3A4148" : Theme.textDim
                    Behavior on color { ColorAnimation { duration: 160 } }
                    font.pixelSize: 20
                    font.weight: Font.DemiBold
                }
            }
        }
    }
}
