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

            ctx.reset()
            ctx.clearRect(0, 0, W, H)

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
