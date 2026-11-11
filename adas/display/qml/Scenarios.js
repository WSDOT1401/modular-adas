.pragma library

// Bench scenarios, matching tools/demo_sender.py. Each is a full datagram, so
// replaying one every second also keeps the ADAS "online".

var names = ["cruise", "lane_left", "lane_right", "fcw", "overspeed", "new_sign", "fault"]

function payload(name) {
    var p = {
        speed: 82,
        speed_limit: 90,
        lane_warning: false,
        lane_direction: "none",
        fcw_warning: false,
        fcw_ttc: 0,
        system_fault: "",
        module_status: { lane: "on", fcw: "on", signs: "on" }
    }
    switch (name) {
    case "lane_left":
        p.speed = 84; p.lane_warning = true; p.lane_direction = "left"; break
    case "lane_right":
        p.speed = 84; p.lane_warning = true; p.lane_direction = "right"; break
    case "fcw":
        p.speed = 76; p.fcw_warning = true; p.fcw_ttc = 1.2; break
    case "overspeed":
        p.speed = 103; break
    case "new_sign":
        p.speed = 58; p.speed_limit = 60; p.sign_seen = "speed_limit_60"; break
    case "fault":
        p.speed = 80; p.system_fault = "camera_blocked"
        p.module_status = { lane: "paused", fcw: "paused", signs: "paused" }
        break
    }
    return JSON.stringify(p)
}
