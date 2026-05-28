import QtQuick
import QtMultimedia
import "../map" as MapWidgets

Item {
    id: root

    property real speed: 0
    property string unitText: "km/h"
    property string fontFamily: "Sans Serif"

    readonly property real s: Math.min(width, height) / 560

    // ── CarPlay status socket ─────────────────────────────────────────────
    // Reads newline-delimited JSON from the carplay server on :9003
    property string carplayStatus: "waiting"   // waiting | connecting | active | error

    Timer {
        id: statusPoller
        interval: 1500
        repeat: true
        running: true
        onTriggered: statusSocket.reconnectIfNeeded()
    }

    QtObject {
        id: statusSocket

        property var socket: null

        function reconnectIfNeeded() {
            if (socket && socket.state !== "unconnected") return
            tryConnect()
        }

        function tryConnect() {
            var s = Qt.createQmlObject('import QtQml 2.15; QtObject {}', root)
            // Use QML TcpSocket if available; otherwise fall back to polling state.json
            // On Pi this is handled by the GStreamer pipeline status
        }
    }

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

        // ── Live CarPlay video (GStreamer pipeline, Pi only) ──────────────
        // Pipeline: Qt reads H264 from TCP :9001, GStreamer decodes, appsink feeds VideoOutput
        MediaPlayer {
            id: carplayPlayer

            // gst-pipeline: reads raw H264 stream from the carplay server TCP socket
            source: "gst-pipeline: tcpclientsrc host=127.0.0.1 port=9001 " +
                    "! h264parse ! avdec_h264 ! videoconvert ! appsink name=qtvideosink"

            videoOutput: carplayVideo
            audioOutput: AudioOutput { volume: 1.0 }

            onPlaybackStateChanged: {
                if (playbackState === MediaPlayer.PlayingState)
                    root.carplayStatus = "active"
            }
            onErrorOccurred: {
                root.carplayStatus = "waiting"
            }
        }

        VideoOutput {
            id: carplayVideo
            anchors.fill: parent
            visible: carplayPlayer.playbackState === MediaPlayer.PlayingState
        }

        // ── Overlay: shown when CarPlay is not streaming ──────────────────
        Rectangle {
            anchors.fill: parent
            color: "#0d0c0b"
            visible: carplayPlayer.playbackState !== MediaPlayer.PlayingState
            radius: parent.radius

            Column {
                anchors.centerIn: parent
                spacing: 8 * root.s

                // CarPlay logo mark (simple ring + triangle)
                Canvas {
                    width: 36 * root.s
                    height: 36 * root.s
                    anchors.horizontalCenter: parent.horizontalCenter
                    onPaint: {
                        const ctx = getContext("2d")
                        const cx = width / 2, cy = height / 2, r = width * 0.42
                        ctx.clearRect(0, 0, width, height)
                        ctx.strokeStyle = "#5b5650"
                        ctx.lineWidth = 2 * root.s
                        ctx.beginPath()
                        ctx.arc(cx, cy, r, 0, Math.PI * 2)
                        ctx.stroke()
                        // simple phone icon hint
                        ctx.fillStyle = "#3a3835"
                        ctx.beginPath()
                        ctx.roundRect(cx - 5 * root.s, cy - 8 * root.s,
                                      10 * root.s, 16 * root.s, 2 * root.s)
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
            enabled: carplayPlayer.playbackState === MediaPlayer.PlayingState

            onPressed: (touchPoints) => forwardTouch("pressed", touchPoints)
            onUpdated: (touchPoints) => forwardTouch("moved",   touchPoints)
            onReleased: (touchPoints) => forwardTouch("released", touchPoints)

            function forwardTouch(action, points) {
                if (points.length === 0) return
                const tp = points[0]
                const nx = tp.x / videoArea.width
                const ny = tp.y / videoArea.height
                // Touch events are sent to carplay server via external socket
                // (handled by start_qt_kiosk.sh companion process)
                touchBridge.sendTouch(action, nx, ny)
            }
        }
    }

    // ── Touch bridge (QML → TCP :9002 → carplay server) ──────────────────
    QtObject {
        id: touchBridge
        function sendTouch(action, nx, ny) {
            // Placeholder: implement with Qt.createQmlObject socket or C++ bridge
            // On Pi the carplay server listens on TCP :9002 for JSON touch events:
            // {"action":"pressed","x":0.5,"y":0.3}
        }
    }

    // Large digital speed below the placeholder
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
