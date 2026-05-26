import QtQuick
import "mainarea/pages" as Pages

Item {
    id: root

    // ── Public properties ──────────────────────────────────────────────
    property real speed: 0
    property real odometer: 87266
    property real trip: 0
    property string unitText: "km/h"
    property string fontFamily: "Sans Serif"
    property string mode: "classic"  // classic | music | map  (aliases: cluster/status→classic, bluetooth→music, carplay→map)
    property string statusText: ""
    property string warningText: ""
    property bool warningActive: false
    property bool connected: true

    // ── Internal transition state ──────────────────────────────────────
    readonly property var availableModes: ["classic", "music", "map"]
    property int currentModeIndex: 0
    property bool animationsEnabled: false
    property real wrapShift: 0
    property int wrapDirection: 0   // 1 = next wrap (map->classic), -1 = previous wrap (classic->map)
    property bool wrapInProgress: false
    property int pendingModeIndex: -1
    property bool internalModeChange: false

    function resolveModeName(m) {
        const aliases = { "cluster": "classic", "status": "classic", "bluetooth": "music", "carplay": "map" }
        return aliases[m] !== undefined ? aliases[m] : m
    }

    function pageDelta(pageIndex) {
        let d = pageIndex - currentModeIndex
        const n = availableModes.length

        if (wrapInProgress) {
            if (wrapDirection === 1 && pageIndex < currentModeIndex) d += n
            if (wrapDirection === -1 && pageIndex > currentModeIndex) d -= n
        }

        return d
    }

    function setModeInternal(newIndex) {
        internalModeChange = true
        mode = availableModes[newIndex]
        internalModeChange = false
    }

    function nextMode() {
        if (wrapInProgress) return

        const n = availableModes.length
        const isWrap = currentModeIndex === n - 1
        if (isWrap) {
            pendingModeIndex = 0
            wrapDirection = 1
            wrapInProgress = true
            setModeInternal(pendingModeIndex)
            wrapAnim.to = -width
            wrapAnim.restart()
            return
        }

        currentModeIndex = (currentModeIndex + 1) % n
        setModeInternal(currentModeIndex)
    }

    function previousMode() {
        if (wrapInProgress) return

        const n = availableModes.length
        const isWrap = currentModeIndex === 0
        if (isWrap) {
            pendingModeIndex = n - 1
            wrapDirection = -1
            wrapInProgress = true
            setModeInternal(pendingModeIndex)
            wrapAnim.to = width
            wrapAnim.restart()
            return
        }

        currentModeIndex = (currentModeIndex - 1 + n) % n
        setModeInternal(currentModeIndex)
    }

    // Respond to external mode sets (alias resolution)
    onModeChanged: {
        if (internalModeChange || wrapInProgress) return
        const resolved = resolveModeName(mode)
        const newIdx = availableModes.indexOf(resolved)
        if (newIdx >= 0 && newIdx !== currentModeIndex) currentModeIndex = newIdx
    }

    Component.onCompleted: {
        const resolved = resolveModeName(mode)
        const idx = availableModes.indexOf(resolved)
        currentModeIndex = idx >= 0 ? idx : 0
        Qt.callLater(function() { animationsEnabled = true })
    }

    NumberAnimation {
        id: wrapAnim
        target: root
        property: "wrapShift"
        from: 0
        duration: 420
        easing.type: Easing.OutCubic
        onFinished: {
            if (!root.wrapInProgress) return
            root.currentModeIndex = root.pendingModeIndex
            root.wrapShift = 0
            root.wrapDirection = 0
            root.wrapInProgress = false
            root.pendingModeIndex = -1
        }
    }

    clip: true

    // Scale factor shared by the persistent overlay items
    readonly property real _s: Math.min(width, height) / 560

    // ── Page 0: Classic ───────────────────────────────────────────────
    Item {
        id: classicPage
        readonly property int pageIndex: 0
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: parent.width
        x: root.pageDelta(pageIndex) * parent.width + root.wrapShift
        Behavior on x {
            enabled: root.animationsEnabled && !root.wrapInProgress
            NumberAnimation { duration: 420; easing.type: Easing.OutCubic }
        }

        Pages.ClassicPage {
            anchors.fill: parent
            odometer: root.odometer
            trip: root.trip
            fontFamily: root.fontFamily
            statusText: root.statusText
            connected: root.connected
        }
    }

    // ── Page 1: Music ─────────────────────────────────────────────────
    Item {
        id: musicPage
        readonly property int pageIndex: 1
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: parent.width
        x: root.pageDelta(pageIndex) * parent.width + root.wrapShift
        Behavior on x {
            enabled: root.animationsEnabled && !root.wrapInProgress
            NumberAnimation { duration: 420; easing.type: Easing.OutCubic }
        }

        Pages.MusicPage {
            anchors.fill: parent
            connected: root.connected
            fontFamily: root.fontFamily
        }
    }

    // ── Page 2: Map ───────────────────────────────────────────────────
    Item {
        id: mapPage
        readonly property int pageIndex: 2
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: parent.width
        x: root.pageDelta(pageIndex) * parent.width + root.wrapShift
        Behavior on x {
            enabled: root.animationsEnabled && !root.wrapInProgress
            NumberAnimation { duration: 420; easing.type: Easing.OutCubic }
        }

        Pages.MapPage {
            anchors.fill: parent
            speed: root.speed
            unitText: root.unitText
            fontFamily: root.fontFamily
        }
    }

    // ── Persistent bottom labels (classic + music only) ───────────────
    Text {
        z: 5
        visible: root.mode !== "map"
        text: root.unitText
        color: "#efede8"
        font.family: root.fontFamily
        font.pixelSize: Math.round(22 * root._s)
        font.weight: Font.DemiBold
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: 130 * root._s
    }
    Text {
        z: 5
        visible: root.mode !== "map"
        text: "124 542 82 67"
        color: "#c6c1b9"
        font.family: root.fontFamily
        font.pixelSize: Math.round(10 * root._s)
        font.weight: Font.DemiBold
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: 148 * root._s
    }
    Text {
        z: 5
        visible: root.mode !== "map"
        text: "VDO"
        color: "#dfddd8"
        font.family: root.fontFamily
        font.pixelSize: Math.round(12 * root._s)
        font.weight: Font.Bold
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: 165 * root._s
    }

    // ── Warning overlay (floats above all pages) ──────────────────────
    Rectangle {
        id: warningOverlay
        z: 10
        readonly property real s: Math.min(parent.width, parent.height) / 560
        width: 180 * s
        height: 26 * s
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: 88 * s
        color: "#d9911818"
        border.color: "#ff8f8f"
        border.width: 1
        radius: 4 * s
        opacity: root.warningActive && root.warningText.length > 0 ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }

        Text {
            anchors.centerIn: parent
            text: root.warningText
            color: "#ffe4e4"
            font.pixelSize: Math.round(11 * warningOverlay.s)
            font.family: root.fontFamily
            font.weight: Font.DemiBold
        }
    }
}
