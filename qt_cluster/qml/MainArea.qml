import QtQuick
import "mainarea/pages" as Pages
import "mainarea/carousel" as Carousel

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

    function nextMode() {
        carousel.nextMode()
    }

    function previousMode() {
        carousel.previousMode()
    }

    onModeChanged: carousel.applyExternalMode(mode)

    Carousel.ModeCarousel {
        id: carousel
        mode: root.mode
        pageWidth: root.width

        Component.onCompleted: initializeFromMode()
        onResolvedMode: function(newMode) {
            if (root.mode !== newMode)
                root.mode = newMode
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
        x: carousel.pageDelta(pageIndex) * parent.width + carousel.wrapShift
        Behavior on x {
            enabled: carousel.animationsEnabled && !carousel.wrapInProgress
            NumberAnimation { duration: 420; easing.type: Easing.OutCubic }
        }
        opacity: carousel.mode === "classic" ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

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
        x: carousel.pageDelta(pageIndex) * parent.width + carousel.wrapShift
        Behavior on x {
            enabled: carousel.animationsEnabled && !carousel.wrapInProgress
            NumberAnimation { duration: 420; easing.type: Easing.OutCubic }
        }
        opacity: carousel.mode === "music" ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

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
        x: carousel.pageDelta(pageIndex) * parent.width + carousel.wrapShift
        Behavior on x {
            enabled: carousel.animationsEnabled && !carousel.wrapInProgress
            NumberAnimation { duration: 420; easing.type: Easing.OutCubic }
        }
        opacity: carousel.mode === "map" ? 1.0 : 0.0
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

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
        opacity: root.mode === "map" ? 0.0 : 1.0
        Behavior on opacity { NumberAnimation { duration: 400; easing.type: Easing.InOutCubic } }
        text: root.unitText
        color: "#efede8"
        font.family: root.fontFamily
        font.pixelSize: Math.round(22 * root._s)
        font.weight: Font.DemiBold
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: 130 * root._s
    }
    Row {
        z: 5
        opacity: root.mode === "map" ? 0.0 : 1.0
        Behavior on opacity { NumberAnimation { duration: 400; easing.type: Easing.InOutCubic } }
        spacing: 3 * root._s
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: 153 * root._s

        Image {
            source: "qrc:/qt/qml/W124Cluster/assets/images/speedo_logo.png"
            height: Math.round(8 * root._s)
            width: height
            fillMode: Image.PreserveAspectFit
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: "124 542 82 67"
            color: "#c6c1b9"
            font.family: root.fontFamily
            font.pixelSize: Math.round(10 * root._s)
            font.weight: Font.DemiBold
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    Text {
        z: 5
        opacity: root.mode === "map" ? 0.0 : 1.0
        Behavior on opacity { NumberAnimation { duration: 400; easing.type: Easing.InOutCubic } }
        text: "VDO"
        color: "#dfddd8"
        font.family: root.fontFamily
        font.pixelSize: Math.round(12 * root._s)
        font.weight: Font.Bold
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: 170 * root._s
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
