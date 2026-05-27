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
            const y = cy + 52 * scale
            const raw = Math.max(0, root.trip) * 10
            const whole = Math.floor(raw)
            const tenths = whole % 10
            const frac = raw - whole

            // Align to odometer digit 6 (rightmost drum):
            // odometer left is cx - 3*tw, so digit[5] starts at +5*tw.
            const odoLeft = cx - 3 * tw
            const x = odoLeft + 5 * tw

            ctx.reset()
            ctx.clearRect(0, 0, width, height)

            // Outer housing
            ctx.fillStyle = "#0f0f0f"
            ctx.strokeStyle = "#4f4a44"
            ctx.lineWidth = 0.8 * scale
            roundedRectPath(x - 5 * scale, y - 3 * scale, tw + 10 * scale, th + 6 * scale, 3 * scale)
            ctx.fill()
            ctx.stroke()

            // White 100 m drum
            ctx.fillStyle = "#f2efe8"
            ctx.fillRect(x, y, tw - 1 * scale, th)
            ctx.strokeStyle = "#5e5952"
            ctx.lineWidth = 0.6 * scale
            ctx.strokeRect(x, y, tw - 1 * scale, th)

            ctx.font = `600 ${Math.round(29 * scale)}px '${root.fontFamily}'`
            ctx.fillStyle = "#121212"
            ctx.textAlign = "center"
            ctx.textBaseline = "middle"

            const baseY = y + th / 2 + 2.8 * scale
            const prev = (tenths + 9) % 10
            const next = (tenths + 1) % 10
            ctx.save()
            ctx.beginPath()
            ctx.rect(x, y, tw - 1 * scale, th)
            ctx.clip()
            ctx.fillText(String(prev), x + tw / 2, baseY - (1 + frac) * th)
            ctx.fillText(String(tenths), x + tw / 2, baseY - frac * th)
            ctx.fillText(String(next), x + tw / 2, baseY + (1 - frac) * th)
            ctx.restore()
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
