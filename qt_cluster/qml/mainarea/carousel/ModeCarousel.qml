import QtQuick

Item {
    id: root

    property string mode: "classic"
    property real pageWidth: 0

    readonly property var availableModes: ["classic", "data", "map"]
    property int currentModeIndex: 0
    property bool animationsEnabled: false
    property real wrapShift: 0
    property int wrapDirection: 0   // 1 = next wrap (map->classic), -1 = previous wrap (classic->map)
    property bool wrapInProgress: false
    property int pendingModeIndex: -1
    property bool internalModeChange: false

    signal resolvedMode(string mode)

    function resolveModeName(m) {
        const aliases = { "cluster": "classic", "status": "classic", "bluetooth": "data", "music": "data", "carplay": "map" }
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
        resolvedMode(mode)
    }

    function initializeFromMode() {
        const resolved = resolveModeName(mode)
        const idx = availableModes.indexOf(resolved)
        currentModeIndex = idx >= 0 ? idx : 0
        mode = availableModes[currentModeIndex]
        Qt.callLater(function() { animationsEnabled = true })
    }

    function applyExternalMode(newMode) {
        if (internalModeChange || wrapInProgress) return
        const resolved = resolveModeName(newMode)
        const idx = availableModes.indexOf(resolved)
        if (idx >= 0 && idx !== currentModeIndex) {
            currentModeIndex = idx
        }
        if (mode !== resolved && idx >= 0) {
            mode = resolved
        }
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
            wrapAnim.to = -pageWidth
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
            wrapAnim.to = pageWidth
            wrapAnim.restart()
            return
        }

        currentModeIndex = (currentModeIndex - 1 + n) % n
        setModeInternal(currentModeIndex)
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
}
