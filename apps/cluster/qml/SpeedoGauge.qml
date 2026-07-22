import QtQuick

Item {
    id: root

    property real speed: 23
    property real odometer: 87266
    property real trip: 0
    property bool demoMode: true
    property string fontFamily: (typeof uiFontFamily !== "undefined" && uiFontFamily.length > 0) ? uiFontFamily : "Sans Serif"

    // Profile — settable at runtime via settings panel
    property int  profileMaxSpeed: 260   // 180 | 200 | 220 | 240 | 260 | 300
    property string profileUnit: "km/h"  // "km/h" | "mph"

    readonly property real minSpeed: 20
    readonly property real maxSpeed: profileMaxSpeed
    readonly property real startDeg: 140
    readonly property real sweepDeg: 260

    // classic | data | map  (or aliases: cluster/status→classic, bluetooth→data, carplay→map)
    property string mainAreaMode: "classic"
    property real   oilTemp:       -1.0
    property real   outsideTemp: -999.0
    property real   voltage:        0.0
    property bool settingsOpen: false
    property string statusText: ""
    property string warningText: ""
    property bool warningActive: false

    property real shownSpeed: speed

    // ── Analog needle spring-damper ──────────────────────────────────────────
    // Models a real mechanical gauge: mass on a spring with viscous damping.
    // Equation:  x'' = ω₀²(target − x) − 2ζω₀·x'
    //   ω₀ = 7.5 rad/s  → natural period ~0.84 s  (snappy but not twitchy)
    //   ζ  = 0.72        → slightly underdamped:  ~4% overshoot, one soft bounce
    //
    // FrameAnimation fires once per rendered frame (vsync-locked), giving the
    // same 60 fps smoothness as built-in QML animations.
    property real _needleVel: 0.0   // km/h per second

    FrameAnimation {
        running: true
        onTriggered: {
            const omega = 7.5
            const zeta  = 0.72
            const dt    = Math.min(frameTime, 0.05)   // cap at 50 ms (e.g. after tab switch)
            const err   = root.speed - root.shownSpeed
            const acc   = omega * omega * err - 2.0 * zeta * omega * root._needleVel
            root._needleVel  += acc * dt
            root.shownSpeed  += root._needleVel * dt
        }
    }

        DialBackground {
        z: 0
        anchors.fill: parent
        fontFamily: root.fontFamily
        minSpeed: root.minSpeed
        maxSpeed: root.maxSpeed
        startDeg: root.startDeg
        sweepDeg: root.sweepDeg
            opacity: 1.0
        Behavior on opacity { NumberAnimation { duration: 400; easing.type: Easing.InOutCubic } }
    }

        DialScale {
            z: 2
            anchors.fill: parent
            fontFamily: root.fontFamily
            minSpeed: root.minSpeed
            maxSpeed: root.maxSpeed
            startDeg: root.startDeg
            sweepDeg: root.sweepDeg
            opacity: root.settingsOpen || root.mainAreaMode === "map" ? 0.0 : 1.0
            Behavior on opacity { NumberAnimation { duration: 400; easing.type: Easing.InOutCubic } }
        }
    Needle {
            z: 3
        anchors.fill: parent
        speed: root.shownSpeed
        minSpeed: root.minSpeed
        maxSpeed: root.maxSpeed
        startDeg: root.startDeg
        sweepDeg: root.sweepDeg
        outlineStyle: root.mainAreaMode === "data"
        opacity: root.settingsOpen || root.mainAreaMode === "map" ? 0.0 : 1.0
        Behavior on opacity { NumberAnimation { duration: 400; easing.type: Easing.InOutCubic } }
    }

    MainArea {
        id: mainArea
            z: 1
        anchors.fill: parent
        speed: root.shownSpeed
        odometer: root.odometer
        trip: root.trip
        unitText: root.profileUnit
        fontFamily: root.fontFamily
        mode: root.mainAreaMode
        oilTemp: root.oilTemp
        outsideTemp: root.outsideTemp
        voltage:     root.voltage
        statusText: root.statusText
        warningText: root.warningText
        warningActive: root.warningActive
        connected: (typeof vehicleState !== "undefined") ? vehicleState.connected : true
        opacity: root.settingsOpen ? 0.0 : 1.0
        Behavior on opacity { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
    }
    Timer {
        id: demoTimer
        // Short interval so SmoothedAnimation is always "in flight" — needle
        // never fully settles before the next target arrives, just like real driving.
        interval: 1800
        running: root.demoMode
        repeat: true
        property int _idx: 0
        // Sequence simulates: pull away → city → light highway → city → stop
        readonly property var _seq: [
            20, 40, 60, 50, 70, 90, 80, 100,
            120, 100, 80, 60, 50, 70, 90,
            120, 160, 140, 120, 100, 80, 60, 40, 20
        ]
        onTriggered: {
            _idx = (_idx + 1) % _seq.length
            if (typeof vehicleState !== "undefined") {
                vehicleState.speed = _seq[_idx]
            } else {
                root.speed = _seq[_idx]
            }
        }
    }

    function nextMainAreaMode() {
        mainArea.nextMode()
        root.mainAreaMode = mainArea.mode
    }

    function previousMainAreaMode() {
        mainArea.previousMode()
        root.mainAreaMode = mainArea.mode
    }

    onSpeedChanged: shownSpeed = speed
}
