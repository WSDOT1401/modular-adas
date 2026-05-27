import QtQuick

Item {
    id: root

    property real odometer: 0
    property string fontFamily: "Sans Serif"
    property real centerX: width / 2
    property real centerY: height / 2
    property real scaleFactor: Math.min(width, height) / 560

    Canvas {
        id: canvas
        anchors.fill: parent

        onPaint: {
            const ctx = getContext("2d")
            const cx = root.centerX
            const cy = root.centerY
            const scale = root.scaleFactor

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

            const cw = 29 * scale
            const ch = 28 * scale
            const value = Math.max(0, root.odometer)
            const totalW = cw * 6
            const y = cy - 75 * scale
            const left = cx - totalW / 2

            function drawRollingDigit(x, digit, frac) {
                const baseY = y + ch / 2 + 3.2 * scale
                ctx.save()
                ctx.beginPath()
                ctx.rect(x, y, cw - 1 * scale, ch)
                ctx.clip()

                ctx.font = `500 ${Math.round(29 * scale)}px '${root.fontFamily}'`
                ctx.fillStyle = "#d9d9d5"
                ctx.textAlign = "center"
                ctx.textBaseline = "middle"

                const prev = (digit + 9) % 10
                const next = (digit + 1) % 10
                ctx.fillText(String(prev), x + cw / 2, baseY - (1 + frac) * ch)
                ctx.fillText(String(digit), x + cw / 2, baseY - frac * ch)
                ctx.fillText(String(next), x + cw / 2, baseY + (1 - frac) * ch)

                ctx.restore()
            }

            // Recursive carry: a digit scrolls only when ALL digits below it
            // are simultaneously at 9 and rolling toward 0 — true Geneva-drive behaviour.
            // lowerPow < 1 means we've reached the sub-km (tenths) level: use its
            // fractional part directly as the scroll fraction.
            function carryFrac(value, placePow) {
                const lowerPow = placePow / 10
                const lowerRaw = value / lowerPow
                const lowerDigit = Math.floor(lowerRaw) % 10
                if (lowerDigit !== 9) return 0
                if (lowerPow < 1) return lowerRaw - Math.floor(lowerRaw)
                return carryFrac(value, lowerPow)
            }

            ctx.reset()
            ctx.clearRect(0, 0, width, height)

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

                const placePow = Math.pow(10, 5 - i)
                const raw = value / placePow
                const whole = Math.floor(raw)
                const digit = whole % 10

                const frac = carryFrac(value, placePow)
                drawRollingDigit(x, digit, frac)
            }

            ctx.font = `600 ${Math.round(15 * scale)}px '${root.fontFamily}'`
            ctx.fillStyle = "#deddd9"
            ctx.textAlign = "center"
            ctx.fillText("km", cx, y - 14 * scale)
        }
    }

    onOdometerChanged: canvas.requestPaint()
    onFontFamilyChanged: canvas.requestPaint()
    onCenterXChanged: canvas.requestPaint()
    onCenterYChanged: canvas.requestPaint()
    onScaleFactorChanged: canvas.requestPaint()
    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()
}
