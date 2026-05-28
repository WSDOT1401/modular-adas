import QtQuick
import "../map" as MapWidgets

Item {
    id: root

    property real speed: 0
    property string unitText: "km/h"
    property string fontFamily: "Sans Serif"

    readonly property real s: Math.min(width, height) / 560

    // Driven by the carplay sidecar server via carplay_status.json (polled by VehicleState)
    readonly property string carplayStatus: vehicleState.carplayStatus

    // True when CarPlay video is actually rendering
    readonly property bool carplayPlaying:
        carplayLoader.status === Loader.Ready && carplayLoader.item &&
        carplayLoader.item.isPlaying

    // ── Video area (same geometry as old placeholder) ─────────────────────
    Rectangle {
        id: videoArea
        width: 386 * root.s
        height: 238 * root.s
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: -26 * root.s
        color: "#000000"
        radius: 10 * root.s
        clip: true

        // CarPlayVideo.qml imports QtMultimedia; Loader handles the case
        // where the module is absent (Windows dev machine) without crashing.
        Loader {
            id: carplayLoader
            anchors.fill: parent
            source: "CarPlayVideo.qml"
            onStatusChanged: {
                if (status === Loader.Error)
                    console.warn("[MapPage] QtMultimedia unavailable — CarPlay video disabled")
            }
        }

        // ── Overlay: shown when CarPlay is not streaming ──────────────────
        Rectangle {
            anchors.fill: parent
            color: "#0d0c0b"
            visible: !root.carplayPlaying
            radius: parent.radius

            Column {
                anchors.centerIn: parent
                spacing: 8 * root.s

                Canvas {
                    width: 36 * root.s
                    height: 36 * root.s
                    anchors.horizontalCenter: parent.horizontalCenter
                    onPaint: {
                        const ctx = getContext("2d")
                        const cx = width / 2, cy = height / 2
                        ctx.clearRect(0, 0, width, height)
                        ctx.strokeStyle = "#5b5650"
                        ctx.lineWidth = 2 * root.s
                        ctx.beginPath()
                        ctx.arc(cx, cy, width * 0.42, 0, Math.PI * 2)
                        ctx.stroke()
                        // Phone icon — rounded rect via arcTo (roundRect not in Qt 6.6)
                        const rx = cx - 5 * root.s, ry = cy - 8 * root.s
                        const rw = 10 * root.s, rh = 16 * root.s, rr = 2 * root.s
                        ctx.fillStyle = "#3a3835"
                        ctx.beginPath()
                        ctx.moveTo(rx + rr, ry)
                        ctx.lineTo(rx + rw - rr, ry)
                        ctx.arcTo(rx + rw, ry,      rx + rw, ry + rr,      rr)
                        ctx.lineTo(rx + rw, ry + rh - rr)
                        ctx.arcTo(rx + rw, ry + rh,  rx + rw - rr, ry + rh, rr)
                        ctx.lineTo(rx + rr, ry + rh)
                        ctx.arcTo(rx,       ry + rh,  rx, ry + rh - rr,     rr)
                        ctx.lineTo(rx, ry + rr)
                        ctx.arcTo(rx,       ry,       rx + rr, ry,           rr)
                        ctx.closePath()
                        ctx.fill()
                    }
                }

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: root.carplayStatus === "connecting" ? "CONNECTING…"
                        : root.carplayStatus === "error"      ? "CARPLAY ERROR"
                        :                                        "AWAITING CARPLAY"
                    font.family: root.fontFamily
                    font.pixelSize: Math.round(9 * root.s)
                    font.letterSpacing: 1.2
                    color: root.carplayStatus === "error" ? "#c0392b" : "#4a4845"
                }
            }
        }

        // ── Touch forwarding to carplay server ────────────────────────────
        MultiPointTouchArea {
            anchors.fill: parent
            enabled: root.carplayPlaying

            onPressed:  (touchPoints) => forwardTouch("pressed",  touchPoints)
            onUpdated:  (touchPoints) => forwardTouch("moved",    touchPoints)
            onReleased: (touchPoints) => forwardTouch("released", touchPoints)

            function forwardTouch(action, points) {
                if (points.length === 0) return
                const tp = points[0]
                touchBridge.sendTouch(action, tp.x / videoArea.width, tp.y / videoArea.height)
            }
        }
    }

    // ── Touch bridge (QML → TCP :9002 → carplay server) ──────────────────
    QtObject {
        id: touchBridge
        function sendTouch(action, nx, ny) {
            // On Pi: carplay server listens on TCP :9002 for {"action":…,"x":…,"y":…}
        }
    }

    // Large digital speed readout below the video area
    MapWidgets.DigitalSpeedReadout {
        id: speedReadout
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: videoArea.bottom
        anchors.topMargin: 8 * root.s
        speed: root.speed
        unitText: root.unitText
        fontFamily: root.fontFamily
        scaleFactor: root.s
    }
}
