import QtQuick
import "../classic" as Classic

Item {
    id: root

    property real odometer: 0
    property real trip: 0
    property string fontFamily: "Sans Serif"
    property string statusText: ""
    property bool connected: true
    property bool mockDemo: false
    property real shownOdometer: odometer
    property real shownTrip: trip

    Behavior on shownOdometer {
        SmoothedAnimation {
            // km/s; smooth carry motion without jittery step updates
            velocity: 0.28
            easing.type: Easing.Linear
        }
    }

    Behavior on shownTrip {
        id: behavior_shownTrip
        SmoothedAnimation {
            velocity: 0.28
            easing.type: Easing.Linear
        }
    }

    readonly property real s: Math.min(width, height) / 560

    Component.onCompleted: {
        shownOdometer = odometer
        shownTrip = trip
    }

    onOdometerChanged: {
        if (!mockDemo) shownOdometer = odometer
    }

    onTripChanged: {
        if (!mockDemo) {
            if (trip < shownTrip) {
                // Reset — bypass SmoothedAnimation and snap instantly
                behavior_shownTrip.enabled = false
                shownTrip = trip
                behavior_shownTrip.enabled = true
            } else {
                shownTrip = trip
            }
        }
    }

    Timer {
        id: demoTimer
        interval: 300
        repeat: true
        running: root.mockDemo
        onTriggered: {
            // Update a target value periodically; SmoothedAnimation handles
            // frame-to-frame interpolation for needle-like smooth motion.
            const delta = 0.085
            root.shownTrip += delta
            if (root.shownTrip >= 1000)
                root.shownTrip -= 1000
            root.shownOdometer += delta
        }
    }

    Classic.OdometerDisplay {
        anchors.fill: parent
        odometer: root.shownOdometer
        fontFamily: root.fontFamily
        centerX: width / 2
        centerY: height / 2
        scaleFactor: root.s
    }

    Classic.TripDisplay {
        anchors.fill: parent
        trip: root.shownTrip
        fontFamily: root.fontFamily
        centerX: width / 2
        centerY: height / 2
        scaleFactor: root.s
    }

    Classic.HundredMeterCounter {
        anchors.fill: parent
        trip: root.shownTrip
        fontFamily: root.fontFamily
        centerX: width / 2
        centerY: height / 2
        scaleFactor: root.s
    }

    Row {
        visible: root.statusText.length > 0
        anchors.verticalCenter: parent.verticalCenter
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.horizontalCenterOffset: 92 * root.s
        anchors.verticalCenterOffset: -88 * root.s
        spacing: 6 * root.s

        Rectangle {
            width: 9 * root.s
            height: width
            radius: width / 2
            color: root.connected ? "#7dd36a" : "#cf5c5c"
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            text: root.statusText
            color: "#c6c1b9"
            font.pixelSize: Math.round(9 * root.s)
            font.family: root.fontFamily
            font.weight: Font.Medium
            anchors.verticalCenter: parent.verticalCenter
        }
    }
}
