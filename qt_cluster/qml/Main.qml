import QtQuick
import QtQuick.Window

Window {
    id: root
    width: 900
    height: 900
    visible: true
    color: "#000000"
    title: "W124 Speedometer"

    flags: Qt.FramelessWindowHint

    property bool kioskMode: true

    // ── Settings panel visibility ─────────────────────────────────
    property bool settingsVisible: false
    property bool _justOpened: false

    // Hold-timer: panel opens after holding space for 600 ms
    Timer {
        id: holdTimer
        interval: 600
        repeat: false
        onTriggered: {
            root.settingsVisible = true
            root._justOpened = true
        }
    }

    // Hold-timer: trip resets after holding R for 600 ms
    Timer {
        id: tripResetTimer
        interval: 600
        repeat: false
        onTriggered: vehicleState.resetTrip()
    }

    // ── Keyboard handling ─────────────────────────────────────────
    Item {
        anchors.fill: parent
        focus: true

        Keys.onPressed: function(event) {
            if (root.settingsVisible) {
                if (event.key === Qt.Key_Up && !event.isAutoRepeat) {
                    settingsPanel.navigateUp()
                    event.accepted = true
                } else if (event.key === Qt.Key_Down && !event.isAutoRepeat) {
                    settingsPanel.navigateDown()
                    event.accepted = true
                } else if (event.key === Qt.Key_Left && !event.isAutoRepeat) {
                    settingsPanel.navigateLeft()
                    event.accepted = true
                } else if (event.key === Qt.Key_Right && !event.isAutoRepeat) {
                    settingsPanel.navigateRight()
                    event.accepted = true
                } else if (event.key === Qt.Key_Space && !event.isAutoRepeat) {
                    event.accepted = true   // let release handler close it
                }
                return
            }
            if (event.key === Qt.Key_Space && !event.isAutoRepeat) {
                if (!root.settingsVisible)
                    holdTimer.restart()
                event.accepted = true
            } else if ((event.key === Qt.Key_Right || event.key === Qt.Key_M || event.key === Qt.Key_Tab) && !event.isAutoRepeat) {
                gauge.nextMainAreaMode()
                event.accepted = true
            } else if (event.key === Qt.Key_Left && !event.isAutoRepeat) {
                gauge.previousMainAreaMode()
                event.accepted = true
            } else if (event.key === Qt.Key_R && !event.isAutoRepeat) {
                tripResetTimer.restart()
                event.accepted = true
            }
        }

        Keys.onReleased: function(event) {
            if (event.key === Qt.Key_Space && !event.isAutoRepeat) {
                holdTimer.stop()
                if (root.settingsVisible) {
                    if (root._justOpened) {
                        root._justOpened = false   // release that ended the hold — ignore
                    } else {
                        root.settingsVisible = false
                    }
                }
                event.accepted = true
            } else if (event.key === Qt.Key_R && !event.isAutoRepeat) {
                tripResetTimer.stop()
                event.accepted = true
            }
        }
    }

    // ── Gauge ─────────────────────────────────────────────────────
    SpeedoGauge {
        id: gauge
        anchors.centerIn: parent
        width: Math.min(parent.width, parent.height)
        height: width
        speed: vehicleState.speed
        odometer: vehicleState.odometer
        trip: vehicleState.trip
        demoMode: vehicleState.source !== "state"
        profileMaxSpeed: vehicleState.profileMaxSpeed
        profileUnit: vehicleState.profileUnit
        settingsOpen: root.settingsVisible

        Component.onCompleted: gauge.mainAreaMode = vehicleState.profilePage
        onMainAreaModeChanged: vehicleState.profilePage = gauge.mainAreaMode
    }

    // ── Settings overlay ──────────────────────────────────────────
    SettingsPanel {
        id: settingsPanel
        anchors.fill: parent
        visible: root.settingsVisible
        speed: vehicleState.speed
        fontFamily: gauge.fontFamily
        selectedMaxSpeed: vehicleState.profileMaxSpeed
        selectedUnit: vehicleState.profileUnit
        selectedSpeedSource: vehicleState.speedSource

        onSelectedMaxSpeedChanged:    vehicleState.profileMaxSpeed = selectedMaxSpeed
        onSelectedUnitChanged:        vehicleState.profileUnit = selectedUnit
        onSelectedSpeedSourceChanged: vehicleState.speedSource = selectedSpeedSource
    }

    onSettingsVisibleChanged: {
        if (settingsVisible) {
            settingsPanel.selectedMaxSpeed    = vehicleState.profileMaxSpeed
            settingsPanel.selectedUnit        = vehicleState.profileUnit
            settingsPanel.selectedSpeedSource = vehicleState.speedSource
            settingsPanel.open()
        }
    }
}
