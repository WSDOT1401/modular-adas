import QtQuick

Item {
    id: root

    property real speed: 23
    property real minSpeed: 20
    property real maxSpeed: 260
    property real startDeg: 140
    property real sweepDeg: 260

    // When true the rim pointer is shown instead of the solid needle
    property bool outlineStyle: false

    // Convert a speed value to the rotation angle in degrees.
    // Both canvases are drawn at 0 ° (pointing east) and rotated here —
    // no canvas repaints during motion, only a GPU transform per frame.
    function speedToDeg(v) {
        const clamped = Math.max(minSpeed, Math.min(maxSpeed, v))
        const t = (clamped - minSpeed) / (maxSpeed - minSpeed)
        return startDeg + t * sweepDeg
    }

    // ── Solid needle (classic W124 orange) ───────────────────────────────────
    Canvas {
        id: solidCanvas
        anchors.fill: parent
        opacity: root.outlineStyle ? 0.0 : 1.0

        // GPU rotation — no repaints while the needle moves
        rotation: root.speedToDeg(root.speed)
        transformOrigin: Item.Center

        Behavior on opacity {
            NumberAnimation { duration: 450; easing.type: Easing.InOutCubic }
        }

        onPaint: {
            const ctx = getContext("2d")
            const W = width, H = height
            const cx = W / 2, cy = H / 2
            const scale = Math.min(W, H) / 560
            const nL = 240 * scale
            const nW = 8.5  * scale

            ctx.reset()
            ctx.clearRect(0, 0, W, H)

            // Draw at angle 0 (pointing east). QML rotation handles actual angle.
            ctx.save()
            ctx.translate(cx, cy)
            ctx.shadowColor = "rgba(255, 153, 38, 0.45)"
            ctx.shadowBlur  = 8 * scale

            ctx.beginPath()
            ctx.moveTo(0, nW * 0.62)
            ctx.lineTo(0, -nW * 0.62)
            ctx.lineTo(nL * 0.78, -nW * 0.72)
            ctx.lineTo(nL * 0.95, -nW * 0.28)
            ctx.lineTo(nL * 0.95,  nW * 0.28)
            ctx.lineTo(nL * 0.78,  nW * 0.72)
            ctx.closePath()
            ctx.fillStyle = "#f5932e"
            ctx.fill()

            ctx.shadowBlur = 0

            ctx.beginPath()
            ctx.moveTo(nL * 0.12, -nW * 0.22)
            ctx.lineTo(nL * 0.86, -nW * 0.14)
            ctx.lineTo(nL * 0.86,  nW * 0.14)
            ctx.lineTo(nL * 0.12,  nW * 0.22)
            ctx.closePath()
            ctx.fillStyle = "#ffbe5a"
            ctx.fill()

            ctx.restore()

            // Hub is a circle — rotationally symmetric, looks correct at any angle
            ctx.beginPath()
            ctx.arc(cx, cy, 26 * scale, 0, Math.PI * 2)
            ctx.fillStyle = "#141311"
            ctx.fill()
            ctx.strokeStyle = "#5f5649"
            ctx.lineWidth = 1.4 * scale
            ctx.stroke()
        }
    }

    // ── Rim pointer (peripheral needle, orange vintage) ─────────────────────
    Canvas {
        id: outlineCanvas
        anchors.fill: parent
        opacity: root.outlineStyle ? 1.0 : 0.0

        // GPU rotation — same principle as solidCanvas
        rotation: root.speedToDeg(root.speed)
        transformOrigin: Item.Center

        Behavior on opacity {
            NumberAnimation { duration: 450; easing.type: Easing.InOutCubic }
        }

        onPaint: {
            const ctx = getContext("2d")
            const W = width, H = height
            const cx = W / 2, cy = H / 2
            const scale = Math.min(W, H) / 560
            const R     = 250 * scale

            const nW        = 8.5  * scale
            const outerBase = R -   7 * scale
            const innerEnd  = R - 120 * scale
            const len       = outerBase - innerEnd
            const wideX     = outerBase - len * 0.20

            ctx.reset()
            ctx.clearRect(0, 0, W, H)

            // Draw at angle 0 (pointing east). QML rotation handles actual angle.
            ctx.save()
            ctx.translate(cx, cy)
            ctx.shadowColor = "rgba(255, 153, 38, 0.55)"
            ctx.shadowBlur  = 9 * scale

            ctx.beginPath()
            ctx.moveTo(outerBase,  nW * 0.62)
            ctx.lineTo(outerBase, -nW * 0.62)
            ctx.lineTo(wideX,     -nW * 0.72)
            ctx.lineTo(innerEnd,  -nW * 0.26)
            ctx.lineTo(innerEnd,   nW * 0.26)
            ctx.lineTo(wideX,      nW * 0.72)
            ctx.closePath()
            ctx.fillStyle = "#f5932e"
            ctx.fill()

            ctx.shadowBlur = 0

            ctx.beginPath()
            ctx.moveTo(outerBase - 4 * scale, 0)
            ctx.lineTo(innerEnd  + 8 * scale, 0)
            ctx.strokeStyle = "#ffbe5a"
            ctx.lineWidth   = 1.4 * scale
            ctx.lineCap     = "round"
            ctx.stroke()

            ctx.restore()
        }
    }

    // Only repaint on layout changes — NOT on speed changes
    function _repaintAll() {
        solidCanvas.requestPaint()
        outlineCanvas.requestPaint()
    }

    onWidthChanged:  _repaintAll()
    onHeightChanged: _repaintAll()
}
