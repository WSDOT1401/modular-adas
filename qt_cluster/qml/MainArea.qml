import QtQuick

Item {
    id: root

    property real odometer: 87266
    property real trip: 0
    property string unitText: "km/h"
    property string fontFamily: "Sans Serif"
    property string mode: "cluster" // cluster | carplay | bluetooth | status
    property string statusText: ""
    property string warningText: ""
    property bool warningActive: false
    property bool connected: true

    readonly property var availableModes: ["cluster", "carplay", "bluetooth", "status"]

    function nextMode() {
        const idx = availableModes.indexOf(mode)
        mode = availableModes[(idx + 1) % availableModes.length]
    }

    Canvas {
        id: canvas
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

            function drawClusterTexts() {
                ctx.fillStyle = "#efede8"
                ctx.textAlign = "center"
                ctx.textBaseline = "middle"
                ctx.font = `600 ${Math.round(22 * scale)}px '${root.fontFamily}'`
                ctx.fillText(root.unitText, cx, cy + 130 * scale)

                ctx.font = `600 ${Math.round(10 * scale)}px '${root.fontFamily}'`
                ctx.fillStyle = "#c6c1b9"
                ctx.fillText("124 542 82 67", cx, cy + 148 * scale)

                ctx.font = `700 ${Math.round(12 * scale)}px '${root.fontFamily}'`
                ctx.fillStyle = "#dfddd8"
                ctx.fillText("VDO", cx, cy + 165 * scale)
            }

            function drawModePlaceholder() {
                const boxW = 250 * scale
                const boxH = 115 * scale
                const x = cx - boxW / 2
                const y = cy - boxH / 2

                ctx.fillStyle = "rgba(12, 12, 13, 0.92)"
                ctx.strokeStyle = "#4a4642"
                ctx.lineWidth = 1 * scale
                roundedRectPath(x, y, boxW, boxH, 8 * scale)
                ctx.fill()
                ctx.stroke()

                ctx.textAlign = "center"
                ctx.textBaseline = "middle"
                ctx.fillStyle = "#efede8"
                ctx.font = `600 ${Math.round(22 * scale)}px '${root.fontFamily}'`
                ctx.fillText(root.mode.toUpperCase(), cx, cy - 12 * scale)

                ctx.fillStyle = "#bab5ae"
                ctx.font = `500 ${Math.round(12 * scale)}px '${root.fontFamily}'`
                ctx.fillText("Main area placeholder", cx, cy + 14 * scale)
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

            function drawWarningOverlay() {
                if (!root.warningActive || root.warningText.length === 0)
                    return

                const boxW = 180 * scale
                const boxH = 26 * scale
                const x = cx - boxW / 2
                const y = cy + 88 * scale

                ctx.fillStyle = "rgba(145, 24, 24, 0.66)"
                ctx.strokeStyle = "#ff8f8f"
                ctx.lineWidth = 1 * scale
                roundedRectPath(x, y, boxW, boxH, 4 * scale)
                ctx.fill()
                ctx.stroke()

                ctx.textAlign = "center"
                ctx.textBaseline = "middle"
                ctx.fillStyle = "#ffe4e4"
                ctx.font = `600 ${Math.round(11 * scale)}px '${root.fontFamily}'`
                ctx.fillText(root.warningText, cx, y + boxH / 2)
            }

            ctx.reset()
            ctx.clearRect(0, 0, W, H)

            if (root.mode === "cluster") {
                drawOdometer(root.odometer)
                drawTrip(root.trip)
                drawClusterTexts()
            } else {
                drawModePlaceholder()
            }

            drawStatusIndicator()
            drawWarningOverlay()
        }
    }

    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()
    onOdometerChanged: canvas.requestPaint()
    onTripChanged: canvas.requestPaint()
    onUnitTextChanged: canvas.requestPaint()
    onFontFamilyChanged: canvas.requestPaint()
    onModeChanged: canvas.requestPaint()
    onStatusTextChanged: canvas.requestPaint()
    onWarningTextChanged: canvas.requestPaint()
    onWarningActiveChanged: canvas.requestPaint()
    onConnectedChanged: canvas.requestPaint()
}
