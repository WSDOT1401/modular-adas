import QtQuick

Item {
    id: root

    property real trip: 0
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

            const tw = 29 * scale
            const th = 28 * scale
            const value = Math.max(0, root.trip)
            const y = cy + 52 * scale
            const left = cx - (tw * 3) / 2

            function drawRollingDigit(x, digit, frac, color) {
                const baseY = y + th / 2 + 2.8 * scale
                ctx.save()
                ctx.beginPath()
                ctx.rect(x, y, tw - 1 * scale, th)
                ctx.clip()

                ctx.font = `500 ${Math.round(29 * scale)}px '${root.fontFamily}'`
                ctx.fillStyle = color
                ctx.textAlign = "center"
                ctx.textBaseline = "middle"

                const prev = (digit + 9) % 10
                const next = (digit + 1) % 10
                ctx.fillText(String(prev), x + tw / 2, baseY - (1 + frac) * th)
                ctx.fillText(String(digit), x + tw / 2, baseY - frac * th)
                ctx.fillText(String(next), x + tw / 2, baseY + (1 - frac) * th)

                ctx.restore()
            }

            // Recursive carry: same Geneva-drive logic as OdometerDisplay.
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

                const placePow = Math.pow(10, 2 - i)
                const raw = value / placePow
                const whole = Math.floor(raw)
                const digit = whole % 10

                const frac = carryFrac(value, placePow)
                drawRollingDigit(x, digit, frac, i === 2 ? "#f0ece4" : "#cfccc5")
            }
        }
    }

    onTripChanged: canvas.requestPaint()
    onFontFamilyChanged: canvas.requestPaint()
    onCenterXChanged: canvas.requestPaint()
    onCenterYChanged: canvas.requestPaint()
    onScaleFactorChanged: canvas.requestPaint()
    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()
}
