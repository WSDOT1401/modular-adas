import QtQuick

Item {
    id: root

    // ── Public properties ──────────────────────────────────────────────
    property real speed: 0
    property real odometer: 87266
    property real trip: 0
    property string unitText: "km/h"
    property string fontFamily: "Sans Serif"
    property string mode: "classic"  // classic | music | map  (aliases: cluster/status→classic, bluetooth→music, carplay→map)
    property string statusText: ""
    property string warningText: ""
    property bool warningActive: false
    property bool connected: true

    // ── Internal transition state ──────────────────────────────────────
    readonly property var availableModes: ["classic", "music", "map"]
    property int currentModeIndex: 0
    property bool animationsEnabled: false

    function nextMode() {
        const isWrap = currentModeIndex === availableModes.length - 1
        if (isWrap) animationsEnabled = false
        currentModeIndex = (currentModeIndex + 1) % availableModes.length
        mode = availableModes[currentModeIndex]
        if (isWrap) Qt.callLater(function() { animationsEnabled = true })
    }

    function previousMode() {
        const isWrap = currentModeIndex === 0
        if (isWrap) animationsEnabled = false
        currentModeIndex = (currentModeIndex - 1 + availableModes.length) % availableModes.length
        mode = availableModes[currentModeIndex]
        if (isWrap) Qt.callLater(function() { animationsEnabled = true })
    }

    // Respond to external mode sets (alias resolution)
    onModeChanged: {
        const aliases = { "cluster": "classic", "status": "classic", "bluetooth": "music", "carplay": "map" }
        const resolved = aliases[mode] !== undefined ? aliases[mode] : mode
        const newIdx = availableModes.indexOf(resolved)
        if (newIdx >= 0 && newIdx !== currentModeIndex) currentModeIndex = newIdx
    }

    Component.onCompleted: {
        const aliases = { "cluster": "classic", "status": "classic", "bluetooth": "music", "carplay": "map" }
        const resolved = aliases[mode] !== undefined ? aliases[mode] : mode
        const idx = availableModes.indexOf(resolved)
        currentModeIndex = idx >= 0 ? idx : 0
        Qt.callLater(function() { animationsEnabled = true })
    }

    clip: true

    // Scale factor shared by the persistent overlay items
    readonly property real _s: Math.min(width, height) / 560

    // ── Page 0: Classic ───────────────────────────────────────────────
    Item {
        id: classicPage
        readonly property int pageIndex: 0
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: parent.width
        x: (pageIndex - root.currentModeIndex) * parent.width
        Behavior on x {
            enabled: root.animationsEnabled
            NumberAnimation { duration: 420; easing.type: Easing.OutCubic }
        }

        Canvas {
            id: classicCanvas
            anchors.fill: parent

            onPaint: {
                const ctx = getContext("2d")
                const W = width
                const H = height
                const cx = W / 2
                const cy = H / 2
                const scale = Math.min(W, H) / 560

                function roundedRectPath(x, y, w, h, r) {
                    const rr = Math.max(0, Math.min(r, w / 2, h / 2))
                    ctx.beginPath()
                    ctx.moveTo(x + rr, y)
                    ctx.lineTo(x + w - rr, y)
                    ctx.quadraticCurveTo(x + w, y, x + w, y + rr)
                    ctx.lineTo(x + w, y + h - rr)
                    ctx.quadraticCurveTo(x + w, y + h, x + w - rr, y + h)
                    ctx.lineTo(x + rr, y + h)
                    ctx.quadraticCurveTo(x, y + h, x, y + h - rr)
                    ctx.lineTo(x, y + rr)
                    ctx.quadraticCurveTo(x, y, x + rr, y)
                    ctx.closePath()
                }

                function drawOdometer(km) {
                    const cw = 29 * scale
                    const ch = 28 * scale
                    const digits = String(Math.floor(km)).padStart(6, "0")
                    const totalW = cw * 6
                    const y = cy - 75 * scale
                    const left = cx - totalW / 2

                    ctx.fillStyle = "#11100f"
                    ctx.strokeStyle = "#5f5a53"
                    ctx.lineWidth = 1 * scale
                    roundedRectPath(left - 6 * scale, y - 4 * scale, totalW + 12 * scale, ch + 8 * scale, 3 * scale)
                    ctx.fill()
                    ctx.stroke()

                    for (let i = 0; i < 6; i++) {
                        const x = left + i * cw
                        ctx.fillStyle = "#070707"
                        ctx.fillRect(x, y, cw - 1 * scale, ch)
                        ctx.strokeStyle = "#2a2927"
                        ctx.lineWidth = 0.6 * scale
                        ctx.strokeRect(x, y, cw - 1 * scale, ch)

                        ctx.beginPath()
                        ctx.moveTo(x, y + ch / 2)
                        ctx.lineTo(x + cw - 1 * scale, y + ch / 2)
                        ctx.strokeStyle = "#151515"
                        ctx.lineWidth = 0.5 * scale
                        ctx.stroke()

                        ctx.font = `500 ${Math.round(29 * scale)}px '${root.fontFamily}'`
                    ctx.fillStyle = "#d9d9d5"
                    ctx.textAlign = "center"
                    ctx.textBaseline = "middle"
                    ctx.fillText(digits[i], x + cw / 2, y + ch / 2 + 1 * scale)
                }

                ctx.font = `600 ${Math.round(15 * scale)}px '${root.fontFamily}'`
                ctx.fillStyle = "#deddd9"
                ctx.textAlign = "center"
                ctx.fillText("km", cx, y - 14 * scale)
            }

            function drawTrip(v) {
                const tw = 29 * scale
                const th = 28 * scale
                const str = String(Math.floor(v)).padStart(3, "0")
                const y = cy + 52 * scale
                const left = cx - (tw * 3) / 2

                ctx.fillStyle = "#0f0f0f"
                ctx.strokeStyle = "#4f4a44"
                ctx.lineWidth = 0.8 * scale
                roundedRectPath(left - 5 * scale, y - 3 * scale, tw * 3 + 10 * scale, th + 6 * scale, 3 * scale)
                ctx.fill()
                ctx.stroke()

                for (let i = 0; i < 3; i++) {
                    const x = left + i * tw
                    ctx.fillStyle = "#050505"
                    ctx.fillRect(x, y, tw - 1 * scale, th)
                    ctx.strokeStyle = "#222"
                    ctx.lineWidth = 0.5 * scale
                    ctx.strokeRect(x, y, tw - 1 * scale, th)

                    ctx.font = `500 ${Math.round(29 * scale)}px '${root.fontFamily}'`
                    ctx.fillStyle = i === 2 ? "#f0ece4" : "#cfccc5"
                    ctx.textAlign = "center"
                    ctx.textBaseline = "middle"
                    ctx.fillText(str[i], x + tw / 2, y + th / 2 + 0.8 * scale)
                }
            }

            function drawStatusIndicator() {
                if (root.statusText.length === 0)
                    return

                const r = 4.5 * scale
                const x = cx + 76 * scale
                const y = cy - 88 * scale

                ctx.beginPath()
                ctx.arc(x, y, r, 0, Math.PI * 2)
                ctx.fillStyle = root.connected ? "#7dd36a" : "#cf5c5c"
                ctx.fill()

                ctx.textAlign = "left"
                ctx.textBaseline = "middle"
                ctx.fillStyle = "#c6c1b9"
                ctx.font = `500 ${Math.round(9 * scale)}px '${root.fontFamily}'`
                ctx.fillText(root.statusText, x + 8 * scale, y)
            }

            ctx.reset()
            ctx.clearRect(0, 0, W, H)
            drawOdometer(root.odometer)
            drawTrip(root.trip)
            drawStatusIndicator()
        }

        Connections {
            target: root
            function onOdometerChanged() { classicCanvas.requestPaint() }
            function onTripChanged() { classicCanvas.requestPaint() }
            function onFontFamilyChanged() { classicCanvas.requestPaint() }
            function onStatusTextChanged() { classicCanvas.requestPaint() }
            function onConnectedChanged() { classicCanvas.requestPaint() }
        }

        onWidthChanged: classicCanvas.requestPaint()
        onHeightChanged: classicCanvas.requestPaint()
    }
    }

    // ── Page 1: Music ─────────────────────────────────────────────────
    Item {
        id: musicPage
        readonly property int pageIndex: 1
        readonly property real s: Math.min(parent.width, parent.height) / 560
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: parent.width
        x: (pageIndex - root.currentModeIndex) * parent.width
        Behavior on x {
            enabled: root.animationsEnabled
            NumberAnimation { duration: 420; easing.type: Easing.OutCubic }
        }

        // Album art
        Rectangle {
            id: albumArt
            width: 128 * musicPage.s
            height: width
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -34 * musicPage.s
            radius: 10 * musicPage.s
            color: "#1b1a18"
            border.color: "#47403a"
            border.width: 1

            Canvas {
                anchors.fill: parent
                Component.onCompleted: requestPaint()
                onPaint: {
                    const ctx = getContext("2d")
                    const W = width, H = height
                    ctx.clearRect(0, 0, W, H)
                    // Subtle record grooves
                    ctx.strokeStyle = "rgba(255,255,255,0.035)"
                    ctx.lineWidth = 0.8
                    for (let r = 22; r < H / 2 - 6; r += 7) {
                        ctx.beginPath()
                        ctx.arc(W / 2, H / 2, r, 0, Math.PI * 2)
                        ctx.stroke()
                    }
                    // Music note glyph
                    ctx.fillStyle = "#6e6760"
                    ctx.font = `${Math.round(H * 0.42)}px sans-serif`
                    ctx.textAlign = "center"
                    ctx.textBaseline = "middle"
                    ctx.fillText("♪", W / 2, H / 2 + H * 0.02)
                }
            }
        }

        Text {
            id: musicTitle
            text: "No Track"
            color: "#efede8"
            font.pixelSize: Math.round(16 * musicPage.s)
            font.family: root.fontFamily
            font.weight: Font.Medium
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: albumArt.bottom
            anchors.topMargin: 13 * musicPage.s
        }

        Text {
            text: "Bluetooth Audio"
            color: "#8f897f"
            font.pixelSize: Math.round(10 * musicPage.s)
            font.family: root.fontFamily
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: musicTitle.bottom
            anchors.topMargin: 4 * musicPage.s
        }

        // Progress bar
        Rectangle {
            id: progressTrack
            width: 148 * musicPage.s
            height: 3 * musicPage.s
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: musicTitle.bottom
            anchors.topMargin: 22 * musicPage.s
            color: "#2d2b28"
            radius: 1.5 * musicPage.s

            Rectangle {
                width: 0
                height: parent.height
                color: "#c8b890"
                radius: parent.radius
                NumberAnimation on width {
                    from: 0
                    to: progressTrack.width
                    duration: 14000
                    loops: Animation.Infinite
                    running: true
                }
            }
        }

        // Connection status pill
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: progressTrack.bottom
            anchors.topMargin: 10 * musicPage.s
            spacing: 5 * musicPage.s

            Rectangle {
                width: 6 * musicPage.s
                height: width
                radius: width / 2
                color: root.connected ? "#52aee0" : "#4a4540"
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: root.connected ? "Connected" : "Disconnected"
                color: root.connected ? "#70a8cc" : "#5e5852"
                font.pixelSize: Math.round(9 * musicPage.s)
                font.family: root.fontFamily
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    // ── Page 2: Map ───────────────────────────────────────────────────
    Item {
        id: mapPage
        readonly property int pageIndex: 2
        readonly property real s: Math.min(parent.width, parent.height) / 560
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: parent.width
        x: (pageIndex - root.currentModeIndex) * parent.width
        Behavior on x {
            enabled: root.animationsEnabled
            NumberAnimation { duration: 420; easing.type: Easing.OutCubic }
        }

        // Center CarPlay placeholder rectangle
        Rectangle {
            id: carplayPlaceholder
            width: 386 * mapPage.s
            height: 238 * mapPage.s
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -26 * mapPage.s
            color: "#1a1816"
            border.color: "#2e2b28"
            border.width: 2 * mapPage.s
            radius: 10 * mapPage.s

            Rectangle {
                width: 2 * mapPage.s
                height: parent.height - 36 * mapPage.s
                anchors.left: parent.left
                anchors.leftMargin: 24 * mapPage.s
                anchors.verticalCenter: parent.verticalCenter
                color: "#5b5650"
                opacity: 0.38
            }

            Rectangle {
                width: 3 * mapPage.s
                height: parent.height * 0.84
                radius: width / 2
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.horizontalCenterOffset: 22 * mapPage.s
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: 6 * mapPage.s
                rotation: -29
                color: "#d9d2c8"
                opacity: 0.34
            }

            Rectangle {
                width: 3 * mapPage.s
                height: parent.height * 0.54
                radius: width / 2
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.horizontalCenterOffset: 50 * mapPage.s
                anchors.verticalCenter: parent.verticalCenter
                anchors.verticalCenterOffset: -16 * mapPage.s
                rotation: 33
                color: "#e8e1d6"
                opacity: 0.34
            }
        }

        // Large digital speed below the placeholder
        Item {
            id: speedReadout
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: carplayPlaceholder.bottom
            anchors.topMargin: 18 * mapPage.s
            width: speedValue.width + speedUnit.width + 12 * mapPage.s
            height: Math.max(speedValue.height, speedUnit.height)

            Text {
                id: speedValue
                anchors.left: parent.left
                anchors.bottom: parent.bottom
                text: Math.round(root.speed)
                color: "#efede8"
                font.pixelSize: Math.round(64 * mapPage.s)
                font.family: root.fontFamily
                font.weight: Font.Light
            }

            Text {
                id: speedUnit
                anchors.left: speedValue.right
                anchors.leftMargin: 12 * mapPage.s
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 8 * mapPage.s
                text: root.unitText
                color: "#c8c1b8"
                font.pixelSize: Math.round(20 * mapPage.s)
                font.family: root.fontFamily
                font.weight: Font.Medium
            }
        }
    }

    // ── Persistent bottom labels (classic + music only) ───────────────
    Text {
        z: 5
        visible: root.mode !== "map"
        text: root.unitText
        color: "#efede8"
        font.family: root.fontFamily
        font.pixelSize: Math.round(22 * root._s)
        font.weight: Font.DemiBold
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: 130 * root._s
    }
    Text {
        z: 5
        visible: root.mode !== "map"
        text: "124 542 82 67"
        color: "#c6c1b9"
        font.family: root.fontFamily
        font.pixelSize: Math.round(10 * root._s)
        font.weight: Font.DemiBold
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: 148 * root._s
    }
    Text {
        z: 5
        visible: root.mode !== "map"
        text: "VDO"
        color: "#dfddd8"
        font.family: root.fontFamily
        font.pixelSize: Math.round(12 * root._s)
        font.weight: Font.Bold
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: 165 * root._s
    }

    // ── Warning overlay (floats above all pages) ──────────────────────
    Rectangle {
        id: warningOverlay
        z: 10
        readonly property real s: Math.min(parent.width, parent.height) / 560
        width: 180 * s
        height: 26 * s
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: 88 * s
        color: "#d9911818"
        border.color: "#ff8f8f"
        border.width: 1
        radius: 4 * s
        opacity: root.warningActive && root.warningText.length > 0 ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }

        Text {
            anchors.centerIn: parent
            text: root.warningText
            color: "#ffe4e4"
            font.pixelSize: Math.round(11 * warningOverlay.s)
            font.family: root.fontFamily
            font.weight: Font.DemiBold
        }
    }
}
