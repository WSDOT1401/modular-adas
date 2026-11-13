import QtQuick
import QtQuick.Shapes

// Settings, MBUX-inspired: a rotary carousel made for the encoder.
//
//   turn   the carousel rotates one item per detent (it wraps round)
//   press  change the item in focus: a feature on/off, the screen shape, ...
//   hold   close (handled in Main.qml)
//
// One item is in focus, large on a glass disc inside a cool cyan halo; its
// neighbours wait smaller and dimmer along an arc. Under it, its name and its
// control. Cyan is only the menu's light (focus, ambient strip, position);
// on/off keeps the app's meaning: green is a feature switched on.
//
// Motion: the carousel turns with the knob (240 ms ease-out). Switching a
// feature ON flashes the halo green and slides the switch; switching it off
// slides the switch back and draws the strike across the icon, quietly.
Item {
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

    // ---- position ------------------------------------------------------------
    // `target` counts detents without wrapping; `scroll` follows it smoothly;
    // `index` is the item in focus.
    property int target: 0
    property real scroll: target
    property bool jumping: false
    Behavior on scroll {
        enabled: !root.jumping
        NumberAnimation { duration: 240; easing.type: Easing.OutCubic }
    }
    readonly property int count: items.length
    readonly property int index: ((target % count) + count) % count
    readonly property var current: items[index]

    function handle(name) {
        if (name === "rotate_cw") target += 1
        else if (name === "rotate_ccw") target -= 1
        else if (name === "press") activate(current.key)
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
    // Opening starts at the first item, without a spin (assigning scroll
    // directly would cut its link to target).
    onVisibleChanged: if (visible) { jumping = true; target = 0; jumping = false }

    // ---- geometry (design units: 720×720 round, 960×720 rect) ----------------
    readonly property real cx: width / 2
    readonly property real cy: roundShape ? 292 : 300
    readonly property real spacing: roundShape ? 178 : 214
    readonly property real reach: roundShape ? 1.55 : 2.55      // how many neighbours show
    readonly property real disc: 150

    property color halo: Theme.ambient
    SequentialAnimation {
        id: confirm
        ColorAnimation { target: root; property: "halo"; to: Theme.active; duration: 120; easing.type: Easing.OutCubic }
        ColorAnimation { target: root; property: "halo"; to: Theme.ambient; duration: 380; easing.type: Easing.InOutQuad }
    }

    // ---- the room goes dark ----------------------------------------------------
    Rectangle {
        anchors.fill: parent
        radius: root.roundShape ? width / 2 : 14
        color: "#030506"
    }

    // ambient light strip along the bottom edge
    Shape {
        anchors.fill: parent
        layer.enabled: true
        layer.samples: 4
        ShapePath {   // soft spill
            strokeColor: Qt.rgba(root.halo.r, root.halo.g, root.halo.b, 0.06)
            strokeWidth: 20; fillColor: "transparent"; capStyle: ShapePath.RoundCap
            PathAngleArc {
                centerX: 360; centerY: 360; radiusX: 336; radiusY: 336
                startAngle: root.roundShape ? 50 : 0; sweepAngle: root.roundShape ? 80 : 0
            }
        }
        ShapePath {   // the light line itself
            strokeColor: Qt.rgba(root.halo.r, root.halo.g, root.halo.b, 0.75)
            strokeWidth: 3.5; fillColor: "transparent"; capStyle: ShapePath.RoundCap
            PathAngleArc {
                centerX: 360; centerY: 360; radiusX: 338; radiusY: 338
                startAngle: root.roundShape ? 55 : 0; sweepAngle: root.roundShape ? 70 : 0
            }
        }
    }
    Rectangle {   // 4:3: the strip is a straight line
        visible: !root.roundShape
        x: root.cx - width / 2; y: root.height - 22
        width: 520; height: 3.5; radius: 2
        color: Qt.rgba(root.halo.r, root.halo.g, root.halo.b, 0.75)
        Rectangle {
            anchors.centerIn: parent
            width: parent.width + 30; height: 20; radius: 10
            color: Qt.rgba(root.halo.r, root.halo.g, root.halo.b, 0.06)
        }
    }

    Text {
        y: root.roundShape ? 112 : 64
        width: root.width
        horizontalAlignment: Text.AlignHCenter
        text: "Settings"
        color: Theme.textDim
        font.pixelSize: 15
        font.letterSpacing: 4
    }

    // ---- focus halo -------------------------------------------------------------
    Shape {
        anchors.fill: parent
        ShapePath {
            strokeColor: "transparent"
            fillGradient: RadialGradient {
                centerX: root.cx; centerY: root.cy; centerRadius: 132
                focalX: root.cx; focalY: root.cy
                GradientStop { position: 0.50; color: Qt.rgba(root.halo.r, root.halo.g, root.halo.b, 0.34) }
                GradientStop { position: 0.72; color: Qt.rgba(root.halo.r, root.halo.g, root.halo.b, 0.12) }
                GradientStop { position: 1.00; color: Qt.rgba(root.halo.r, root.halo.g, root.halo.b, 0.0) }
            }
            startX: root.cx + 132; startY: root.cy
            PathAngleArc { centerX: root.cx; centerY: root.cy; radiusX: 132; radiusY: 132; startAngle: 0; sweepAngle: 360 }
        }
    }

    // ---- the carousel -----------------------------------------------------------
    Repeater {
        model: root.items
        delegate: Item {
            id: item
            required property var modelData
            required property int index
            // Signed distance from the focus, wrapped round the carousel.
            readonly property real d: {
                let v = index - root.scroll
                return v - root.count * Math.round(v / root.count)
            }
            readonly property real ad: Math.abs(d)
            readonly property bool focused: index === root.index

            width: root.disc
            height: root.disc
            x: root.cx + d * root.spacing - width / 2
            y: root.cy + ad * ad * 20 - height / 2
            z: 10 - ad
            scale: ad <= 1 ? 1 - 0.40 * ad : 0.60 - 0.16 * (ad - 1)
            opacity: Math.max(0, Math.min(1, 1 - 0.38 * ad))
                     * Math.max(0, Math.min(1, (root.reach - ad) / 0.4))
            visible: opacity > 0.01

            Rectangle {   // the glass disc
                anchors.fill: parent
                radius: width / 2
                color: Theme.glass
                border.width: 1.5
                border.color: Qt.rgba(1, 1, 1, 0.10)
                Rectangle {   // a soft sheen across the top
                    x: parent.width * 0.14; y: 5
                    width: parent.width * 0.72; height: parent.height * 0.42
                    radius: height / 2
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.06) }
                        GradientStop { position: 0.6; color: Qt.rgba(1, 1, 1, 0.0) }
                    }
                }
            }
            Rectangle {   // the light ring, on the item in focus
                anchors.centerIn: parent
                width: parent.width + 10; height: width; radius: width / 2
                color: "transparent"
                border.width: 2
                border.color: Qt.rgba(root.halo.r, root.halo.g, root.halo.b, 0.9)
                opacity: Math.max(0, 1 - 2.2 * item.ad)
            }
            FeatureIcon {
                visible: item.modelData.feature !== ""
                anchors.centerIn: parent
                size: 78
                feature: item.modelData.feature || "lane"
                status: root.isOn(item.modelData.key) ? "on" : "off"
                bg: Theme.glass
            }
            MenuIcon {
                visible: item.modelData.feature === ""
                anchors.centerIn: parent
                size: 70
                kind: item.modelData.key
                color: Theme.text
            }
        }
    }

    // ---- the item in focus: its name and its control -----------------------------
    Text {
        id: label
        y: root.cy + root.disc / 2 + 34
        width: root.width
        horizontalAlignment: Text.AlignHCenter
        text: root.current.label
        color: Theme.text
        font.pixelSize: 28
        font.letterSpacing: 3
        onTextChanged: fadeIn.restart()
        NumberAnimation on opacity { id: fadeIn; from: 0.25; to: 1; duration: 180; easing.type: Easing.OutCubic }
    }

    Item {
        id: control
        y: label.y + 52
        width: root.width
        height: 44
        readonly property string key: root.current.key
        readonly property bool switchable: key === "lane" || key === "fcw" || key === "signs" || key === "demo"
        readonly property bool on: root.isOn(key)

        // on/off: a switch and its word
        Row {
            visible: control.switchable
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 16
            Rectangle {
                width: 84; height: 42; radius: 21
                color: control.on ? Theme.active : "#262D34"
                Behavior on color { ColorAnimation { duration: 180 } }
                Rectangle {
                    width: 34; height: 34; radius: 17
                    y: 4
                    x: control.on ? parent.width - width - 4 : 4
                    Behavior on x { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
                    color: control.on ? "#FFFFFF" : "#8B949C"
                }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: 64
                text: control.on ? "On" : "Off"
                color: control.on ? Theme.active : Theme.textDim
                font.pixelSize: 22
                font.weight: Font.DemiBold
                font.letterSpacing: 1.5
            }
        }

        // screen shape: a two-way choice, the current one lit
        Row {
            visible: control.key === "shape"
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 10
            Repeater {
                model: [{ round: true, text: "Round" }, { round: false, text: "4:3" }]
                Rectangle {
                    required property var modelData
                    readonly property bool lit: modelData.round === root.roundShape
                    width: 120; height: 42; radius: 21
                    color: lit ? Qt.rgba(root.halo.r, root.halo.g, root.halo.b, 0.16) : "transparent"
                    border.width: 1.5
                    border.color: lit ? root.halo : "#2E363E"
                    Text {
                        anchors.centerIn: parent
                        text: parent.modelData.text
                        color: parent.lit ? Theme.text : Theme.textDim
                        font.pixelSize: 19
                        font.letterSpacing: 1.5
                    }
                }
            }
        }
    }

    // ---- where you are: one dot per item ----------------------------------------
    Row {
        y: control.y + (root.roundShape ? 76 : 96)
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 8
        Repeater {
            model: root.count
            Rectangle {
                required property int index
                readonly property bool here: index === root.index
                width: here ? 22 : 8; height: 8; radius: 4
                color: here ? root.halo : "#323A42"
                Behavior on width { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
            }
        }
    }
}
