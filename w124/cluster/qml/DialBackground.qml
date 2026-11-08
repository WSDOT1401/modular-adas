import QtQuick

Item {
    id: root
    property real minSpeed: 20
    property real maxSpeed: 260
    property real startDeg: 140
    property real sweepDeg: 260
    property string fontFamily: "Sans Serif"

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
            const R = 250 * scale

            function toRad(d) { return d * Math.PI / 180 }
            function speedToAngle(v) {
                const clamped = Math.max(root.minSpeed, Math.min(root.maxSpeed, v))
                const t = (clamped - root.minSpeed) / (root.maxSpeed - root.minSpeed)
                return toRad(root.startDeg + t * root.sweepDeg)
            }
            function ring(r, c, w) {
                ctx.beginPath()
                ctx.arc(cx, cy, r, 0, Math.PI * 2)
                ctx.strokeStyle = c
                ctx.lineWidth = w
                ctx.stroke()
            }

            ctx.reset()
            ctx.clearRect(0, 0, W, H)

            // Background gradient
            const g = ctx.createRadialGradient(cx, cy - 24 * scale, 30 * scale, cx, cy, R)
            g.addColorStop(0, "#30302f")
            g.addColorStop(0.45, "#242423")
            g.addColorStop(1, "#141413")
            ctx.beginPath()
            ctx.arc(cx, cy, R, 0, Math.PI * 2)
            ctx.fillStyle = g
            ctx.fill()

            ring(R - 1 * scale, "#0f0e0d", 2.2 * scale)
            ring(R - 12 * scale, "#2d2c2a", 1 * scale)
            ring(R + 5 * scale, "#3a3732", 1.2 * scale)

            // Vignette
            const vignette = ctx.createRadialGradient(cx, cy, R * 0.5, cx, cy, R * 1.03)
            vignette.addColorStop(0, "rgba(0,0,0,0)")
            vignette.addColorStop(1, "rgba(0,0,0,0.33)")
            ctx.beginPath()
            ctx.arc(cx, cy, R, 0, Math.PI * 2)
            ctx.fillStyle = vignette
            ctx.fill()
        }
    }

    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()
    onFontFamilyChanged: canvas.requestPaint()
    onMinSpeedChanged: canvas.requestPaint()
    onMaxSpeedChanged: canvas.requestPaint()
    onStartDegChanged: canvas.requestPaint()
    onSweepDegChanged: canvas.requestPaint()
}
