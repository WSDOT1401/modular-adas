import QtQuick

Item {
    id: root

    property real odometer: 0
    property real trip: 0
    property string fontFamily: "Sans Serif"
    property string statusText: ""
    property bool connected: true

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
                    ctx.fillText(digits[i], x + cw / 2, y + ch / 2 + 3.2 * scale)
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
                    ctx.fillText(str[i], x + tw / 2, y + th / 2 + 2.8 * scale)
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
    }

    onOdometerChanged: classicCanvas.requestPaint()
    onTripChanged: classicCanvas.requestPaint()
    onFontFamilyChanged: classicCanvas.requestPaint()
    onStatusTextChanged: classicCanvas.requestPaint()
    onConnectedChanged: classicCanvas.requestPaint()

    onWidthChanged: classicCanvas.requestPaint()
    onHeightChanged: classicCanvas.requestPaint()
}
