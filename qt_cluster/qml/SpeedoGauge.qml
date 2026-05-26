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

    // classic | music | map  (or aliases: cluster/status→classic, bluetooth→music, carplay→map)
    property string mainAreaMode: "classic"
    property string statusText: ""
    property string warningText: ""
    property bool warningActive: false

    property real shownSpeed: speed

    Behavior on shownSpeed {
        // Moves at a fixed rate (km/h per second) rather than a fixed duration,
        // so large and small changes feel proportional — just like a real needle.
        SmoothedAnimation {
            velocity: 60          // 60 km/h per second: 0→120 in 2 s, 120→60 in 1 s
            easing.type: Easing.InOutQuad
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
            z: 1
            anchors.fill: parent
            fontFamily: root.fontFamily
            minSpeed: root.minSpeed
            maxSpeed: root.maxSpeed
            startDeg: root.startDeg
            sweepDeg: root.sweepDeg
            opacity: root.mainAreaMode === "map" ? 0.0 : 1.0
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
        outlineStyle: root.mainAreaMode === "music"
        opacity: root.mainAreaMode === "map" ? 0.0 : 1.0
        Behavior on opacity { NumberAnimation { duration: 400; easing.type: Easing.InOutCubic } }
    }

    MainArea {
        id: mainArea
            z: 2
        anchors.fill: parent
        speed: root.shownSpeed
        odometer: root.odometer
        trip: root.trip
        unitText: root.profileUnit
        fontFamily: root.fontFamily
        mode: root.mainAreaMode
        statusText: root.statusText
        warningText: root.warningText
        warningActive: root.warningActive
        connected: (typeof vehicleState !== "undefined") ? vehicleState.connected : true
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
            root.speed = _seq[_idx]
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
