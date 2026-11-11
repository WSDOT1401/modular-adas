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

    function levelColor(level) {
        switch (level) {
        case "info": return info
        case "caution": return caution
        case "warning": return warning
        case "system": return system
        default: return text
        }
    }

    // 4:3 banner: background, title and detail colours per level.
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
    function bannerSub(level) {
        switch (level) {
        case "info": return "#8FB6D4"
        case "caution": return "#3D2A00"
        case "warning": return "#3A0A0A"
        case "system": return "#9AA3AB"
        default: return textDim
        }
    }

    // A speed-limit sign id such as "speed_limit_60". The layouts light up
    // the limit sign itself instead of showing the same sign twice.
    function isLimitSign(id) { return /^speed_limit_[0-9]+$/.test(id || "") }

    // Sign class ids (adas/vision) to words. Unknown ids are shown tidied up.
    function signLabel(id) {
        if (isLimitSign(id)) return "Speed limit " + id.slice(12)
        const names = {
            "stop": "Stop",
            "give_way": "Give way",
            "no_entry": "No entry",
            "no_u_turn": "No U-turn",
            "no_parking": "No parking"
        }
        if (names[id] !== undefined) return names[id]
        if (!id) return ""
        const words = id.replace(/_/g, " ")
        return words.charAt(0).toUpperCase() + words.slice(1)
    }

    function faultText(id) {
        switch (id) {
        case "camera_blocked": return "Camera view blocked"
        case "camera_lost": return "Camera not found"
        case "overheating": return "Computer too hot"
        default: return "ADAS fault"
        }
    }

    function ttcText(s) {
        return s.fcwTtc > 0 ? "Time to collision " + s.fcwTtc.toFixed(1) + " s" : "Brake now"
    }

    // The line under the road view (round) and the banner (4:3).
    function title(s) {
        switch (s.reason) {
        case "fcw": return "Vehicle ahead"
        case "lane_left": return "Drifting left"
        case "lane_right": return "Drifting right"
        case "overspeed": return "Over the limit"
        case "sign": return signLabel(s.signSeen)
        case "fault": return faultText(s.systemFault)
        case "adas_offline": return "ADAS not running"
        default: return ""
        }
    }
    function detail(s) {
        switch (s.reason) {
        case "fcw": return ttcText(s)
        case "lane_left":
        case "lane_right": return "Steer back into your lane"
        case "overspeed": return Math.round(s.speed - s.speedLimit) + " km/h above " + s.speedLimit
        case "sign": return "Sign just passed"
        case "fault": return "Lane, collision and sign alerts paused"
        case "adas_offline": return "No data from the vision service"
        default: return ""
        }
    }
    function bannerTitle(s) {
        if (s.reason === "fcw") return "BRAKE"
        if (s.reason === "none") return "ADAS active"
        return title(s)
    }
    function bannerDetail(s) {
        if (s.reason === "fcw") return "Vehicle ahead · " + ttcText(s).toLowerCase()
        if (s.reason === "none") return "Watching lanes, traffic ahead and signs"
        return detail(s)
    }
}
