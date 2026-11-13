import QtQuick
import QtQuick.Window
import QtCore
import "Scenarios.js" as Scenarios

// Picks the layout for the screen shape, scales it to the real panel, and
// routes driver input (rotary encoder over UDP, or the keyboard on a desk).
Window {
    id: win

    readonly property bool roundShape: settings.shape !== "rect"
    readonly property real designW: roundShape ? 720 : 960
    readonly property real designH: 720
    property bool menuOpen: false

    // The monitor chosen by --screen (main.cpp). Set before the window is shown,
    // so full screen lands on that monitor.
    screen: Qt.application.screens[startupScreen]
    width: designW
    height: designH
    visible: true
    visibility: startFullScreen ? Window.FullScreen : Window.Windowed
    color: "#000000"
    title: "ADAS display"

    Settings {
        id: settings
        category: "display"
        property string shape: "round"   // "round" | "rect"
    }

    // ---- the screen ----------------------------------------------------------
    Item {
        id: stage
        width: win.designW
        height: win.designH
        anchors.centerIn: parent
        scale: Math.min(win.width / width, win.height / height)

        Loader {
            id: layout
            anchors.fill: parent
            sourceComponent: win.roundShape ? roundLayout : rectLayout
        }

        SettingsMenu {
            id: menu
            anchors.fill: parent
            open: win.menuOpen
            laneOn: adas.laneEnabled
            fcwOn: adas.fcwEnabled
            signsOn: adas.signsEnabled
            roundShape: win.roundShape
            demoOn: demo.running
            onToggleFeature: name => adas.toggleFeature(name)
            onToggleShape: settings.shape = win.roundShape ? "rect" : "round"
            onToggleDemo: demo.toggle()
            onCloseRequested: win.menuOpen = false
        }
    }

    Component {
        id: roundLayout
        RoundLayout { st: adas }
    }
    Component {
        id: rectLayout
        RectLayout { st: adas }
    }

    // ---- driver input --------------------------------------------------------
    // The one place that decides what each control does. Today:
    //   hold   open / close settings
    //   press  hide the current caution or info alert (in the menu: change,
    //          e.g. switch a safety feature on or off)
    //   turn   move through the menu (unused while driving, for now)
    function handleInput(name) {
        if (name === "long_press") {
            menuOpen = !menuOpen
            return
        }
        if (menuOpen) {
            menu.handle(name)
            return
        }
        if (name === "press") adas.acknowledge()
    }

    Connections {
        target: adas
        function onInputEvent(name) { win.handleInput(name) }
    }

    Shortcut { sequences: ["Right", "Down"]; context: Qt.ApplicationShortcut; onActivated: win.handleInput("rotate_cw") }
    Shortcut { sequences: ["Left", "Up"]; context: Qt.ApplicationShortcut; onActivated: win.handleInput("rotate_ccw") }
    Shortcut { sequences: ["Return", "Enter", "Space"]; context: Qt.ApplicationShortcut; onActivated: win.handleInput("press") }
    Shortcut { sequences: ["M", "Escape"]; context: Qt.ApplicationShortcut; onActivated: win.handleInput("long_press") }

    // ---- demo / bench scenarios ------------------------------------------------
    // Replays a built-in scenario every second (which also keeps the ADAS
    // "online"). "cycle" steps through all of them, four seconds each.
    Timer {
        id: demo
        property string fixed: ""
        property int tick: 0
        interval: 1000
        repeat: true
        triggeredOnStart: true
        function toggle() {
            if (running) { stop(); return }
            fixed = ""
            tick = 0
            start()
        }
        onTriggered: {
            const name = fixed !== "" ? fixed
                       : Scenarios.names[Math.floor(tick / 4) % Scenarios.names.length]
            adas.applyJsonString(Scenarios.payload(name))
            tick++
        }
    }

    // ---- start-up --------------------------------------------------------------
    Component.onCompleted: {
        if (startupShape !== "") settings.shape = startupShape
        if (startupScenario === "cycle") demo.toggle()
        else if (startupScenario !== "") { demo.fixed = startupScenario; demo.start() }
    }

    Timer {
        running: snapshotPath !== ""
        interval: 1500
        onTriggered: stage.grabToImage(function(result) {
            result.saveToFile(snapshotPath)
            Qt.quit()
        })
    }
}
