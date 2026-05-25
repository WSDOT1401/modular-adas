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

    // cluster | carplay | bluetooth | status
    property string mainAreaMode: "cluster"
    property string statusText: ""
    property string warningText: ""
    property bool warningActive: false

    property real shownSpeed: speed

    Behavior on shownSpeed {
        NumberAnimation {
            duration: 110
            easing.type: Easing.OutCubic
        }
    }

    DialFace {
        z: 0
        anchors.fill: parent
        fontFamily: root.fontFamily
        minSpeed: root.minSpeed
        maxSpeed: root.maxSpeed
        startDeg: root.startDeg
        sweepDeg: root.sweepDeg
    }

    Needle {
        z: 2
        anchors.fill: parent
        speed: root.shownSpeed
        minSpeed: root.minSpeed
        maxSpeed: root.maxSpeed
        startDeg: root.startDeg
        sweepDeg: root.sweepDeg
    }

    MainArea {
        id: mainArea
        z: 1
        anchors.fill: parent
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
        interval: 2200
        running: root.demoMode
        repeat: true
        onTriggered: {
            const demos = [23, 40, 60, 88, 120, 160, 200, 240, 0]
            const idx = Math.floor(Math.random() * demos.length)
            root.speed = demos[idx]
        }
    }

    function nextMainAreaMode() {
        mainArea.nextMode()
        root.mainAreaMode = mainArea.mode
    }

    onSpeedChanged: shownSpeed = speed
}
