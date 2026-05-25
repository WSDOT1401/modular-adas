import QtQuick

Item {
    id: root

    property string fontFamily: "Sans Serif"
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
            function drawStripedMarker() {
                // Midway between 60 and 50.
                const a = speedToAngle(55)
                const midX = cx + (R - 14 * scale) * Math.cos(a)
                const midY = cy + (R - 14 * scale) * Math.sin(a)

                ctx.save()
                ctx.translate(midX, midY)
                ctx.rotate(a + Math.PI / 2)

                const w = 24 * scale
                const h = 30 * scale
                ctx.fillStyle = "#1a1713"
                ctx.fillRect(-w / 2, -h / 2, w, h)
                ctx.strokeStyle = "#5d564d"
                ctx.lineWidth = 0.8 * scale
                ctx.strokeRect(-w / 2, -h / 2, w, h)

                for (let x = -w / 2; x < w / 2 + 8 * scale; x += 6 * scale) {
                    ctx.beginPath()
                    ctx.moveTo(x, h / 2)
                    ctx.lineTo(x + 9 * scale, -h / 2)
                    ctx.strokeStyle = "#f3c34e"
                    ctx.lineWidth = 2.2 * scale
                    ctx.stroke()
                }

                ctx.restore()
            }

            ctx.reset()
            ctx.clearRect(0, 0, W, H)

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

            drawStripedMarker()

            for (let v = root.minSpeed; v <= root.maxSpeed; v += 10) {
                const a = speedToAngle(v)
                const major = v % 20 === 0
                const inner = R - 38 * scale
                const outer = R - 8 * scale

                const x1 = cx + inner * Math.cos(a)
                const y1 = cy + inner * Math.sin(a)
                const x2 = cx + outer * Math.cos(a)
                const y2 = cy + outer * Math.sin(a)

                ctx.beginPath()
                ctx.moveTo(x1, y1)
                ctx.lineTo(x2, y2)
                ctx.strokeStyle = major ? "#f1efeb" : "#cbcac6"
                ctx.lineWidth = major ? 8 * scale : 4 * scale
                ctx.lineCap = "butt"
                ctx.stroke()

                if (major) {
                    const fontSize = 37 * scale
                    const halfH = fontSize * 0.5
                    const halfW = fontSize * 0.62
                    const margin = 4 * scale
                    const gap = margin
                              + halfH * Math.abs(Math.sin(a))
                              + halfW * Math.abs(Math.cos(a))
                    const lr = inner - gap

                    const topLabel = Math.abs(Math.cos(a)) < 0.16
                    let xNudge = topLabel ? 0 : -6.0 * scale
                    if (root.maxSpeed >= 300 && v === 180) {
                        xNudge = -1.5 * scale
                    }

                    const lx = cx + lr * Math.cos(a) + xNudge
                    const ly = cy + lr * Math.sin(a)
                    ctx.font = `500 ${Math.round(fontSize)}px '${root.fontFamily}'`
                    ctx.fillStyle = "#efede8"
                    ctx.textAlign = "center"
                    ctx.textBaseline = "middle"
                    ctx.fillText(String(v), lx, ly)
                }
            }

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
