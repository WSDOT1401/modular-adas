import QtQuick

Item {
    id: root

    property real speed: 23
    property real minSpeed: 20
    property real maxSpeed: 260
    property real startDeg: 140
    property real sweepDeg: 260

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

            function toRad(d) { return d * Math.PI / 180 }
            function speedToAngle(v) {
                const clamped = Math.max(root.minSpeed, Math.min(root.maxSpeed, v))
                const t = (clamped - root.minSpeed) / (root.maxSpeed - root.minSpeed)
                return toRad(root.startDeg + t * root.sweepDeg)
            }

            const nA = speedToAngle(root.speed)
            const nL = 240 * scale
            const nW = 8.5 * scale

            ctx.reset()
            ctx.clearRect(0, 0, W, H)

            ctx.save()
            ctx.translate(cx, cy)
            ctx.rotate(nA)
            ctx.shadowColor = "rgba(255, 153, 38, 0.45)"
            ctx.shadowBlur = 8 * scale

            ctx.beginPath()
            ctx.moveTo(0, nW * 0.62)
            ctx.lineTo(0, -nW * 0.62)
            ctx.lineTo(nL * 0.78, -nW * 0.72)
            ctx.lineTo(nL * 0.95, -nW * 0.28)
            ctx.lineTo(nL * 0.95, nW * 0.28)
            ctx.lineTo(nL * 0.78, nW * 0.72)
            ctx.closePath()
            ctx.fillStyle = "#f5932e"
            ctx.fill()

            ctx.shadowBlur = 0

            ctx.beginPath()
            ctx.moveTo(nL * 0.12, -nW * 0.22)
            ctx.lineTo(nL * 0.86, -nW * 0.14)
            ctx.lineTo(nL * 0.86, nW * 0.14)
            ctx.lineTo(nL * 0.12, nW * 0.22)
            ctx.closePath()
            ctx.fillStyle = "#ffbe5a"
            ctx.fill()

            ctx.restore()

            ctx.beginPath()
            ctx.arc(cx, cy, 26 * scale, 0, Math.PI * 2)
            ctx.fillStyle = "#141311"
            ctx.fill()
            ctx.strokeStyle = "#5f5649"
            ctx.lineWidth = 1.4 * scale
            ctx.stroke()
        }
    }

    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()
    onSpeedChanged: canvas.requestPaint()
    onMinSpeedChanged: canvas.requestPaint()
    onMaxSpeedChanged: canvas.requestPaint()
    onStartDegChanged: canvas.requestPaint()
    onSweepDegChanged: canvas.requestPaint()
}
