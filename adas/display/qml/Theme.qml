pragma Singleton
import QtQuick

// Colours and wording in one place. Alert colours differ in lightness as well
// as hue, so they stay distinct for colour-blind drivers and in sunlight.
QtObject {
    readonly property color bg: "#050607"
    readonly property color panel: "#0A0D10"
    readonly property color road: "#0B0F13"
    readonly property color track: "#161B20"
    readonly property color text: "#F2F4F5"
    readonly property color textDim: "#8B949C"
    readonly property color line: "#C9D1D8"
    readonly property color lineOff: "#4A525A"
    readonly property color car: "#E8ECEF"
    readonly property color muted: "#5B636B"

    readonly property color info: "#7CC4FF"
    readonly property color caution: "#FFB020"
    readonly property color warning: "#FF4D3D"
    readonly property color system: "#C4CBD1"

    readonly property color signRed: "#E0261B"
    // A safety feature switched on and working (telltale green).
    readonly property color active: "#4FD08A"

    function levelColor(level) {
        switch (level) {
        case "info": return info
        case "caution": return caution
        case "warning": return warning
        case "system": return system
        default: return text
        }
    }

    // 4:3 banner: background and foreground colours per level.
    function bannerBg(level) {
        switch (level) {
        case "info": return "#0D1B26"
        case "caution": return caution
        case "warning": return warning
        case "system": return "#1A1E22"
        default: return "#0B0E11"
        }
    }
    function bannerFg(level) {
        switch (level) {
        case "info": return "#9CD3FF"
        case "caution": return "#1A1000"
        case "warning": return "#1A0404"
        default: return "#E6EBEF"
        }
    }
    // A speed-limit sign: the detector's single "speed_limit" class (the
    // number travels separately, in speed_limit), or an id with the value in
    // it, "speed_limit_60". The layouts light up
    // the limit sign itself instead of showing the same sign twice.
    function isLimitSign(id) { return /^speed_limit(_[0-9]+)?$/.test(id || "") }

    // Sign class ids to words. The ids are the Thai fine classes in
    // adas/experiments/traffic-sign_recognition/classes.py; any other id is
    // shown tidied up ("left_curve" -> "Left curve").
    function signLabel(id) {
        if (isLimitSign(id)) return id.length > 12 ? "Speed limit " + id.slice(12) : "Speed limit"
        const names = {
            "no_right_u_turn": "No U-turn",
            "no_stopping_parking": "No stopping",
            "keep_left_or_right": "Keep left or right",
            "reserved_for_bus": "Bus lane",
            "t_junction_left": "Junction on the left",
            "t_junction_right": "Junction on the right",
            "u_turn": "U-turn ahead"
        }
        if (names[id] !== undefined) return names[id]
        if (!id) return ""
        const words = id.replace(/_/g, " ")
        return words.charAt(0).toUpperCase() + words.slice(1)
    }

    // The camera can't see: blocked, or not found at all.
    function isCameraFault(id) { return id === "camera_blocked" || id === "camera_lost" }

    // The only alerts spelled out. Everything else is shown, not written:
    // the rim, the road view and the feature icons carry it.
    function title(s) {
        if (s.reason === "fault" && isCameraFault(s.systemFault)) return "CAMERA VIEW BLOCKED"
        if (s.reason === "overspeed") return "OVERSPEED"
        return ""
    }
}
