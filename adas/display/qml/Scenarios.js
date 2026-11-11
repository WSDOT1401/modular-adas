.pragma library

// Bench scenarios, matching tools/demo_sender.py. Each is a full datagram, so
// replaying one every second also keeps the ADAS "online".

var names = ["cruise", "lane_left", "lane_right", "fcw", "overspeed", "new_sign", "fault", "feature_off", "following"]

function payload(name) {
    var p = {
        speed: 82,
        speed_limit: 90,
        lane_warning: false,
        lane_direction: "none",
        fcw_warning: false,
        fcw_ttc: 0,
        lead_vehicle: false,
        system_fault: "",
        module_status: { lane: "on", fcw: "on", signs: "on" }
    }
    switch (name) {
    case "lane_left":
        p.speed = 84; p.lane_warning = true; p.lane_direction = "left"; break
    case "lane_right":
        p.speed = 84; p.lane_warning = true; p.lane_direction = "right"; break
    case "fcw":
        p.speed = 76; p.fcw_warning = true; p.fcw_ttc = 1.2; p.lead_vehicle = true; break
    case "overspeed":
        p.speed = 103; break
    case "new_sign":
        p.speed = 58; p.speed_limit = 60; p.sign_seen = "speed_limit"; break
    case "fault":
        p.speed = 80; p.system_fault = "camera_blocked"
        p.module_status = { lane: "paused", fcw: "paused", signs: "paused" }
        break
    case "following":
        p.speed = 74; p.lead_vehicle = true; break
    case "feature_off":
        p.module_status = { lane: "off", fcw: "on", signs: "on" }; break
    }
    return JSON.stringify(p)
}
