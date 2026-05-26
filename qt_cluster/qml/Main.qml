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

    // Hold-timer: panel opens after holding space for 600 ms
    Timer {
        id: holdTimer
        interval: 600
        repeat: false
        onTriggered: root.settingsVisible = true
    }

    // ── Keyboard handling ─────────────────────────────────────────
    Item {
        anchors.fill: parent
        focus: true

        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Space && !event.isAutoRepeat) {
                holdTimer.restart()
                event.accepted = true
            } else if ((event.key === Qt.Key_Right || event.key === Qt.Key_M || event.key === Qt.Key_Tab) && !event.isAutoRepeat) {
                gauge.nextMainAreaMode()
                event.accepted = true
            } else if (event.key === Qt.Key_Left && !event.isAutoRepeat) {
                gauge.previousMainAreaMode()
                event.accepted = true
            }
        }

        Keys.onReleased: function(event) {
            if (event.key === Qt.Key_Space && !event.isAutoRepeat) {
                holdTimer.stop()
                root.settingsVisible = false
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
    }

    // ── Settings overlay ──────────────────────────────────────────
    SettingsPanel {
        id: settingsPanel
        anchors.fill: parent
        visible: root.settingsVisible
        selectedMaxSpeed: vehicleState.profileMaxSpeed
        selectedUnit: vehicleState.profileUnit

        onSelectedMaxSpeedChanged: vehicleState.profileMaxSpeed = selectedMaxSpeed
        onSelectedUnitChanged: vehicleState.profileUnit = selectedUnit
    }

    onSettingsVisibleChanged: {
        if (settingsVisible) {
            settingsPanel.selectedMaxSpeed = vehicleState.profileMaxSpeed
            settingsPanel.selectedUnit = vehicleState.profileUnit
        }
    }
}
