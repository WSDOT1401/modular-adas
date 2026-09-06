import QtQuick

Item {
    id: root

    property real   oilTemp:      -1.0   // °C; negative = unknown / not wired
    property real   outsideTemp: -999.0   // °C; ≤ −99 = unknown
    property real   voltage:        0.0   // V;  < 1 = unknown
    property string fontFamily: "Sans Serif"

    readonly property real s: Math.min(width, height) / 560

    // ── Inline row component ───────────────────────────────────────
    component DataRow: Column {
        property string label:     ""
        property string valueText: "–"
        property string unit:      ""
        property bool   warn:      false

        spacing: 1 * root.s
        anchors.horizontalCenter: parent.horizontalCenter

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: label
            color: "#aaaaaa"
            font.pixelSize: Math.round(13 * root.s)
            font.family: root.fontFamily
            font.letterSpacing: 2.0
        }

        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 4 * root.s

            Text {
                text: valueText
                color: warn ? "#e05050" : "#ffffff"
                font.pixelSize: Math.round(42 * root.s)
                font.family: root.fontFamily
                font.weight: Font.Light
                Behavior on color { ColorAnimation { duration: 400 } }
            }
            Text {
                text: unit
                color: warn ? "#c04040" : "#cccccc"
                font.pixelSize: Math.round(18 * root.s)
                font.family: root.fontFamily
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 6 * root.s
                Behavior on color { ColorAnimation { duration: 400 } }
            }
        }
    }

    // ── Three sensor rows ──────────────────────────────────────────
    Column {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: -10 * root.s
        spacing: 2 * root.s

        DataRow {
            label:     "OIL TEMP"
            valueText: root.oilTemp < 0
                       ? "–"
                       : Math.round(root.oilTemp) + ""
            unit:      "°C"
            warn:      root.oilTemp > 120
        }

        DataRow {
            label:     "OUTSIDE"
            valueText: root.outsideTemp <= -99
                       ? "–"
                       : (root.outsideTemp >= 0 ? "+" : "") + Math.round(root.outsideTemp) + ""
            unit:      "°C"
            warn:      root.outsideTemp > -99 && root.outsideTemp < 4
        }

        DataRow {
            label:     "BATTERY"
            valueText: root.voltage < 1.0
                       ? "–"
                       : root.voltage.toFixed(1)
            unit:      "V"
            warn:      root.voltage >= 1.0 && (root.voltage < 11.5 || root.voltage > 15.0)
        }
    }
}
