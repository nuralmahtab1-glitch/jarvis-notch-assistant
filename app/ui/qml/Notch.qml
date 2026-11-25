// Notch.qml - the whole notch UI. Made by Nur Al Mahtab.
import QtQuick
import QtQuick.Shapes
import QtQuick.Window

Window {
    id: win
    width: 640
    height: 380
    visible: true
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
    x: Screen.virtualX + Math.round((Screen.width - width) / 2)
    y: Screen.virtualY
    title: notch.appName

    // ---------------- design tokens ----------------
    QtObject {
        id: th
        readonly property color black: "#000000"
        readonly property color panel: "#0B0B0E"
        readonly property color capsule: "#17171C"
        readonly property color text1: "#F5F5F7"
        readonly property color text2: "#9A9AA3"
        readonly property color text3: "#5E5E66"
        readonly property color accent: "#5CE1FF"
        readonly property color good: "#34D399"
        readonly property color warn: "#FFB340"
        readonly property color bad: "#FF5C5C"
        readonly property color rec: "#FF3B30"
        readonly property color moon: "#FFD84D"
        readonly property string font: "Inter, Segoe UI Variable Text, Segoe UI"
        readonly property string icons: "Segoe Fluent Icons, Segoe MDL2 Assets"
        readonly property int flare: 12
        readonly property int radius: 26
    }

    readonly property string mode: notch.mode
    readonly property bool isTiny: mode === "idle" || mode === "sleeping" || mode === "peek"
    readonly property bool isPanel: mode === "expanded" || mode === "music" || mode === "focus" || mode === "todo"
    readonly property bool isCard: mode === "confirm" || mode === "claudeNeeds" || mode === "reminder" || mode === "claudeDone" || mode === "answer"
    readonly property bool isCompact: !isTiny && !isPanel && !isCard
    readonly property bool sleeping: mode === "sleeping"

    // Click shield: Approve/Deny/Confirm ignore clicks for a moment after a card appears, so a click
    // meant for the app underneath can never approve something by accident.
    property bool armed: true
    property string shieldMode: ""
    Connections {
        target: notch
        function onChanged() {
            if (notch.mode === win.shieldMode) return
            win.shieldMode = notch.mode
            if (notch.mode === "claudeNeeds" || notch.mode === "confirm") { win.armed = false; armTimer.restart() }
            else win.armed = true
        }
    }
    Timer { id: armTimer; interval: 700; onTriggered: win.armed = true }

    function stateColor() {
        if (mode === "claudeNeeds") return th.warn
        if (mode === "claudeError") return th.bad
        if (mode === "done" || mode === "claudeDone") return th.good
        if (mode === "recording") return th.rec
        if (mode.indexOf("claude") === 0 || mode === "working" || mode === "listening" || mode === "hearing") return th.accent
        return th.text1
    }

    // ---------------- the notch body ----------------
    Item {
        id: body
        x: Math.round((win.width - width) / 2)
        y: 0
        width: notch.boxW
        height: notch.boxH
        Behavior on width { NumberAnimation { duration: 280; easing.type: Easing.OutBack; easing.overshoot: 0.7 } }
        Behavior on height { NumberAnimation { duration: 280; easing.type: Easing.OutBack; easing.overshoot: 0.7 } }

        // Black shape with inverted top corners (melts into the bezel) and rounded bottom corners.
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                id: outline
                readonly property real w: body.width
                readonly property real h: body.height
                readonly property real r: th.flare
                readonly property real rad: Math.min(th.radius, h / 2)
                strokeWidth: -1
                fillColor: win.isPanel || win.isCard ? (win.mode === "music" ? "#2A110D" : th.panel) : th.black
                Behavior on fillColor { ColorAnimation { duration: 220 } }
                startX: 0; startY: 0
                PathArc { x: outline.r; y: outline.r; radiusX: outline.r; radiusY: outline.r; direction: PathArc.Clockwise }
                PathLine { x: outline.r; y: outline.h - outline.rad }
                PathArc { x: outline.r + outline.rad; y: outline.h; radiusX: outline.rad; radiusY: outline.rad; direction: PathArc.Counterclockwise }
                PathLine { x: outline.w - outline.r - outline.rad; y: outline.h }
                PathArc { x: outline.w - outline.r; y: outline.h - outline.rad; radiusX: outline.rad; radiusY: outline.rad; direction: PathArc.Counterclockwise }
                PathLine { x: outline.w - outline.r; y: outline.r }
                PathArc { x: outline.w; y: 0; radiusX: outline.r; radiusY: outline.r; direction: PathArc.Clockwise }
                PathLine { x: 0; y: 0 }
            }
        }

        HoverHandler { id: hh; onHoveredChanged: notch.bodyHover(hovered) }
        scale: sleeping ? sleepPulse.v : 1.0
        transformOrigin: Item.Top
        QtObject { id: sleepPulse; property real v: 1.0 }
        SequentialAnimation {
            running: win.sleeping; loops: Animation.Infinite
            NumberAnimation { target: sleepPulse; property: "v"; to: 1.015; duration: 2000; easing.type: Easing.InOutSine }
            NumberAnimation { target: sleepPulse; property: "v"; to: 1.0; duration: 2000; easing.type: Easing.InOutSine }
        }
        
        // ============ TINY (idle / peek / sleeping) ============
        Item {
            id: tinyLayer
            anchors.fill: parent
            visible: opacity > 0.01
            opacity: win.isTiny ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 140 } }
            Eyes {
                anchors.centerIn: parent
                anchors.verticalCenterOffset: -2
                mood: win.sleeping ? "sleep" : "normal"
                lookX: notch.lookX; lookY: notch.lookY
            }
            // moon + star (sleeping)
            Item {
                visible: win.sleeping
                x: 30; y: 8; width: 20; height: 20
                Rectangle { anchors.fill: parent; radius: 10; color: th.moon }
                Rectangle { x: 6; y: -2; width: 18; height: 18; radius: 9; color: th.black }
                Rectangle { x: 20; y: 2; width: 3; height: 3; radius: 1.5; color: th.moon; opacity: 0.9 }
            }
            // drifting z z
            Repeater {
                model: win.sleeping ? 2 : 0
                delegate: Text {
                    required property int index
                    text: "z"
                    color: th.text2
                    font.family: th.font
                    font.pixelSize: 10 + index * 4
                    font.weight: Font.DemiBold
                    x: 128 + index * 16
                    property real p: 0
                    y: 24 - p * 16 - index * 3
                    opacity: Math.sin(p * Math.PI) * (0.8 - index * 0.25)
                    SequentialAnimation on p {
                        loops: Animation.Infinite
                        running: win.sleeping
                        PauseAnimation { duration: index * 900 }
                        NumberAnimation { from: 0; to: 1; duration: 2600; easing.type: Easing.InOutSine }
                        PauseAnimation { duration: 600 }
                    }
                }
            }
        }

        // ============ COMPACT status pill ============
        Item {
            id: compactLayer
            anchors.fill: parent
            visible: opacity > 0.01
            opacity: win.isCompact ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 160 } }
            Eyes {
                x: th.flare + 14; anchors.verticalCenter: parent.verticalCenter
                scale: 0.85
                transformOrigin: Item.Left
                mood: win.mode === "done" || win.mode === "claudeDone" ? "happy"
                      : win.mode === "claudeError" ? "alert" : "normal"
                lookX: 0; lookY: 0
                tint: win.mode === "working" || win.mode === "claudeWorking" ? th.accent : "#FFFFFF"
            }
            Text {
                id: compactLabel
                x: th.flare + 14 + 52
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - x - th.flare - 56
                text: notch.title
                textFormat: Text.PlainText
                color: win.mode === "hearing" ? th.text1 : th.text1
                elide: Text.ElideRight
                font.family: th.font; font.pixelSize: 13; font.weight: Font.Medium
            }
            Text {
                visible: win.mode === "claudeWorking"
                anchors.right: parent.right; anchors.rightMargin: th.flare + 52
                anchors.verticalCenter: parent.verticalCenter
                text: notch.subtitle; color: th.text2
                font.family: th.font; font.pixelSize: 12
            }
            // right adornments
            Bars {
                visible: ["listening", "hearing", "speaking", "recording", "working", "claudeWorking"].indexOf(win.mode) >= 0
                anchors.right: parent.right; anchors.rightMargin: th.flare + 16
                anchors.verticalCenter: parent.verticalCenter
                barColor: win.mode === "recording" ? th.rec : win.stateColor()
            }
            Rectangle { // recording dot
                visible: win.mode === "recording"
                width: 8; height: 8; radius: 4; color: th.rec
                x: th.flare + 6; anchors.verticalCenter: parent.verticalCenter
                SequentialAnimation on opacity { loops: Animation.Infinite; running: win.mode === "recording"
                    NumberAnimation { to: 0.25; duration: 650 } NumberAnimation { to: 1; duration: 650 } }
            }
            Text {
                visible: win.mode === "done" || win.mode === "claudeDone"
                anchors.right: parent.right; anchors.rightMargin: th.flare + 16
                anchors.verticalCenter: parent.verticalCenter
                text: "✓"; color: th.good; font.pixelSize: 17; font.weight: Font.Bold
            }
            Text {
                visible: win.mode === "claudeError"
                anchors.right: parent.right; anchors.rightMargin: th.flare + 16
                anchors.verticalCenter: parent.verticalCenter
                text: "!"; color: th.bad; font.pixelSize: 17; font.weight: Font.Bold
            }
            Row { // volume slider
                visible: win.mode === "volume"
                anchors.right: parent.right; anchors.rightMargin: th.flare + 16
                anchors.verticalCenter: parent.verticalCenter
                spacing: 10
                Rectangle { width: 90; height: 5; radius: 2.5; color: "#2B2B31"
                    Rectangle { width: parent.width * 0.55; height: parent.height; radius: 2.5; color: th.text1 } }
                Text { text: "55"; color: th.text2; font.family: th.font; font.pixelSize: 12; anchors.verticalCenter: parent.verticalCenter }
            }
        }

        // ============ CARDS (confirm / needs you / reminder) ============
        Item {
            id: cardLayer
            anchors.fill: parent
            visible: opacity > 0.01
            opacity: win.isCard ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 180 } }
            Eyes {
                x: th.flare + 18; y: 18
                mood: win.mode === "claudeNeeds" || win.mode === "confirm" ? "alert" : (win.mode === "claudeDone" ? "happy" : "normal")
                lookX: 0; lookY: 0
                tint: win.mode === "claudeNeeds" ? th.warn : (win.mode === "claudeDone" ? th.good : "#FFFFFF")
            }
            Column {
                x: th.flare + 18 + 60; y: 14
                width: parent.width - x - th.flare - 18
                spacing: 3
                Text { text: notch.title; color: th.text1; width: parent.width; elide: Text.ElideRight
                    font.family: th.font; font.pixelSize: 14; font.weight: Font.DemiBold }
                Text { text: notch.subtitle; color: th.text2; width: parent.width; elide: Text.ElideRight
                    font.family: th.font; font.pixelSize: 12 }
            }
            Row {
                visible: win.mode === "claudeDone" || win.mode === "answer"
                anchors.right: parent.right; anchors.rightMargin: th.flare + 18
                anchors.verticalCenter: parent.verticalCenter
                Pill { label: "Dismiss"; fg: "#000000"; bg: th.good; onClicked: notch.act("dismiss") }
            }
            Row {
                visible: win.mode === "confirm" || win.mode === "claudeNeeds"
                anchors.right: parent.right; anchors.rightMargin: th.flare + 18
                anchors.bottom: parent.bottom; anchors.bottomMargin: 12
                spacing: 8
                Pill { enabled: win.armed; label: win.mode === "claudeNeeds" ? "Deny" : "Not now"; fg: th.text1; bg: "#24242A"; onClicked: notch.act(win.mode === "claudeNeeds" ? "deny" : "cancel") }
                Pill { enabled: win.armed; label: win.mode === "claudeNeeds" ? "Approve" : "Confirm"; fg: "#000000"; bg: win.mode === "claudeNeeds" ? th.warn : "#FFFFFF"; onClicked: notch.act(win.mode === "claudeNeeds" ? "approve" : "confirm") }
            }
            Row {
                visible: win.mode === "reminder"
                anchors.right: parent.right; anchors.rightMargin: th.flare + 18
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8
                Pill { label: "Snooze"; fg: th.text1; bg: "#24242A"; onClicked: notch.act("snooze") }
                Pill { label: "Dismiss"; fg: "#000000"; bg: th.accent; onClicked: notch.act("dismiss") }
            }
        }

        // ============ PANELS ============
        Item {
            id: panelLayer
            anchors.fill: parent
            visible: opacity > 0.01
            opacity: win.isPanel ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 200 } }

            // top row: mode buttons
            Row {
                x: th.flare + 18; y: 12; spacing: 8
                visible: win.mode === "expanded"
                RoundBtn { glyph: "pointer"; key: "command"; onClicked: notch.act("btn_command") }
                RoundBtn { glyph: ""; key: "dictate"; onClicked: notch.act("btn_dictate") }
                RoundBtn { glyph: ""; key: "write"; onClicked: notch.act("btn_write") }
            }
            // top row: clock + tabs
            Row {
                visible: win.mode === "expanded"
                anchors.right: parent.right; anchors.rightMargin: th.flare + 18
                y: 12; height: 34; spacing: 14
                Text { text: notch.clock; color: th.text3; anchors.verticalCenter: parent.verticalCenter
                    font.family: th.font; font.pixelSize: 11; font.features: { "tnum": 1 } }
                TabIcon { glyph: ""; key: "timer"; onClicked: notch.setMode("focus") }
                TabIcon { glyph: ""; key: "widgets"; onClicked: notch.setMode("todo") }
                TabIcon { glyph: ""; key: "shelf" }
                TabIcon { glyph: ""; key: "controls"; onClicked: notch.setMode("volume") }
                TabIcon { glyph: ""; key: "apps" }
                TabIcon { glyph: ""; key: "menu"; onClicked: notch.setMode("music") }
            }

            // ---- expanded: eyes capsule + title (page 0) / about (page 1) ----
            Item {
                visible: win.mode === "expanded"
                x: 0; y: 54; width: parent.width; height: 70
                Rectangle {
                    id: capsule
                    x: th.flare + 18; width: 84; height: 44; radius: 22; color: th.capsule
                    anchors.verticalCenter: undefined; y: 4
                    Eyes { anchors.centerIn: parent; lookX: notch.lookX * 0.6; lookY: notch.lookY * 0.6; scale: 0.8 }
                }
                Column {
                    visible: notch.page === 0
                    x: capsule.x + capsule.width + 22; y: 4
                    width: parent.width - x - th.flare - 18
                    spacing: 4
                    Text { text: notch.title; color: th.text1; width: parent.width; elide: Text.ElideRight
                        font.family: th.font; font.pixelSize: 17; font.weight: Font.DemiBold }
                    Text { text: notch.subtitle; color: th.text2; width: parent.width; elide: Text.ElideRight
                        font.family: th.font; font.pixelSize: 12 }
                }
                Column {
                    visible: notch.page === 1
                    x: capsule.x + capsule.width + 22; y: 4
                    spacing: 4
                    Text { text: notch.appName; color: th.text1
                        font.family: th.font; font.pixelSize: 17; font.weight: Font.DemiBold }
                    Text { text: notch.credit; color: th.accent
                        font.family: th.font; font.pixelSize: 12; font.weight: Font.Medium }
                }
            }
            Row {
                visible: win.mode === "expanded"
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom; anchors.bottomMargin: 12
                spacing: 6
                Repeater { model: 2
                    delegate: Rectangle { required property int index
                        width: 5; height: 5; radius: 2.5
                        color: notch.page === index ? th.text1 : th.text3
                        MouseArea { anchors.fill: parent; anchors.margins: -6; onClicked: notch.setPage(index) } } }
            }

            // ---- TODO ----
            Item {
                visible: win.mode === "todo"; anchors.fill: parent
                Eyes { x: th.flare + 20; y: 22; scale: 0.9; lookX: 0; lookY: 0 }
                Column {
                    x: th.flare + 20; y: 62
                    Text { text: "To-do"; color: th.text2; font.family: th.font; font.pixelSize: 12 }
                    Text { text: notch.todoDone + "/" + notch.todo.length; color: th.text1
                        font.family: th.font; font.pixelSize: 38; font.weight: Font.DemiBold }
                    Text { text: "Done today"; color: th.text3; font.family: th.font; font.pixelSize: 11 }
                }
                Column {
                    x: 190; y: 24; spacing: 9
                    Repeater {
                        model: notch.todo
                        delegate: Item { required property int index; required property var modelData
                            width: 300; height: 20
                            Rectangle { id: box; width: 17; height: 17; radius: 8.5; y: 1.5
                                color: modelData.done ? th.good : "transparent"
                                border.color: modelData.done ? th.good : th.text3; border.width: 1.5
                                Text { anchors.centerIn: parent; visible: modelData.done; text: "✓"; color: "#000"; font.pixelSize: 11; font.weight: Font.Bold } }
                            Text { x: 27; anchors.verticalCenter: parent.verticalCenter
                                text: modelData.text; color: modelData.done ? th.text3 : th.text1
                                font.family: th.font; font.pixelSize: 14; font.strikeout: modelData.done }
                            MouseArea { anchors.fill: parent; onClicked: notch.toggleTodo(index) }
                        }
                    }
                }
            }

            // ---- FOCUS ----
            Item {
                visible: win.mode === "focus"; anchors.fill: parent
                Eyes { x: th.flare + 20; y: 20; scale: 0.9; lookX: 0; lookY: 0 }
                Item {
                    id: ring
                    x: 150; y: 36; width: 76; height: 76
                    Shape {
                        anchors.fill: parent; preferredRendererType: Shape.CurveRenderer
                        ShapePath { strokeWidth: 6; strokeColor: "#1F1F25"; fillColor: "transparent"
                            PathAngleArc { centerX: 38; centerY: 38; radiusX: 32; radiusY: 32; startAngle: 0; sweepAngle: 360 } }
                        ShapePath { strokeWidth: 6; strokeColor: th.good; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                            PathAngleArc { centerX: 38; centerY: 38; radiusX: 32; radiusY: 32; startAngle: -90; sweepAngle: 360 * notch.focusFrac } }
                    }
                    Text { anchors.centerIn: parent; text: ""; font.family: th.icons; font.pixelSize: 22; color: th.text1 }
                }
                Column {
                    x: 250; y: 42; spacing: 2
                    Text { text: notch.focusText; color: th.text1; font.family: th.font; font.pixelSize: 40
                        font.weight: Font.DemiBold; font.features: { "tnum": 1 } }
                    Text { text: "Focus time"; color: th.text2; font.family: th.font; font.pixelSize: 12 }
                }
                Row {
                    anchors.right: parent.right; anchors.rightMargin: th.flare + 20
                    y: 60; spacing: 8
                    Pill { label: "Break"; fg: th.text1; bg: "#24242A"; onClicked: notch.act("focus_break") }
                    Pill { label: "Stop"; fg: "#FFFFFF"; bg: "#B3261E"; onClicked: notch.act("focus_stop") }
                }
            }

            // ---- MUSIC ----
            Item {
                visible: win.mode === "music"; anchors.fill: parent
                Rectangle { x: th.flare + 20; y: 22; width: 64; height: 64; radius: 12
                    gradient: Gradient { GradientStop { position: 0; color: "#FFB347" } GradientStop { position: 1; color: "#E5484D" } } }
                Column {
                    x: th.flare + 20 + 78; y: 26; spacing: 2
                    Text { text: notch.music.title; color: th.text1; font.family: th.font; font.pixelSize: 15; font.weight: Font.DemiBold }
                    Text { text: notch.music.artist; color: "#D9A79F"; font.family: th.font; font.pixelSize: 12 }
                }
                Item { x: th.flare + 20; y: 104; width: 270; height: 12
                    Rectangle { y: 4; width: parent.width; height: 4; radius: 2; color: "#4A2A25"
                        Rectangle { width: parent.width * notch.music.frac; height: 4; radius: 2; color: "#FF8A6B" } }
                    Text { y: -1; text: "1:05"; x: 0; visible: false }
                }
                Row { x: th.flare + 20 + 70; y: 128; spacing: 26
                    Text { text: ""; font.family: th.icons; font.pixelSize: 16; color: th.text1; MouseArea { anchors.fill: parent; anchors.margins: -8; onClicked: notch.act("media_prev") } }
                    Text { text: ""; font.family: th.icons; font.pixelSize: 20; color: th.text1; MouseArea { anchors.fill: parent; anchors.margins: -8; onClicked: notch.act("media_play") } }
                    Text { text: ""; font.family: th.icons; font.pixelSize: 16; color: th.text1; MouseArea { anchors.fill: parent; anchors.margins: -8; onClicked: notch.act("media_next") } }
                }
                Column {
                    x: 330; y: 34; spacing: 8; width: 190
                    Text { text: notch.music.lyrics[0] || ""; color: "#8A5A53"; font.family: th.font; font.pixelSize: 13 }
                    Text { text: notch.music.lyrics[1] || ""; color: "#FFFFFF"; font.family: th.font; font.pixelSize: 15; font.weight: Font.DemiBold }
                    Text { text: notch.music.lyrics[2] || ""; color: "#8A5A53"; font.family: th.font; font.pixelSize: 13 }
                }
            }
        }
    }

    // ---------------- reusable bits ----------------
    component Eyes: Item {
        id: eyes
        property string mood: "normal"
        property real lookX: 0
        property real lookY: 0
        property color tint: "#E4F7FF"
        property bool blinking: false
        width: 40; height: 22
        Timer { interval: 3200 + Math.random() * 3800; running: eyes.mood === "normal"; repeat: true
            onTriggered: { eyes.blinking = true; blinkOff.start(); interval = 3200 + Math.random() * 3800 } }
        Timer { id: blinkOff; interval: 130; onTriggered: eyes.blinking = false }
        Repeater {
            model: 2
            delegate: Item {
                required property int index
                x: 5 + index * 20 + eyes.lookX * 3
                y: 11 - height / 2 + eyes.lookY * 2
                width: 9; height: 14
                Behavior on x { NumberAnimation { duration: 90 } }
                Rectangle { // open eye
                    visible: eyes.mood === "normal" || eyes.mood === "alert"
                    anchors.horizontalCenter: parent.horizontalCenter; anchors.verticalCenter: parent.verticalCenter
                    width: eyes.mood === "alert" ? 10 : 12
                    height: eyes.blinking ? 1.6 : (eyes.mood === "alert" ? 11 : 7)
                    radius: height / 2; color: eyes.tint
                    Behavior on height { NumberAnimation { duration: 70 } }
                }
                Shape { // happy ^ or sleepy curve
                    visible: eyes.mood === "happy" || eyes.mood === "sleep"
                    anchors.centerIn: parent; width: 12; height: 8
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath { strokeWidth: 2.4; strokeColor: eyes.mood === "sleep" ? "#C9C9D0" : eyes.tint
                        fillColor: "transparent"; capStyle: ShapePath.RoundCap
                        startX: -1; startY: eyes.mood === "sleep" ? 1 : 7
                        PathArc { x: 11; y: eyes.mood === "sleep" ? 1 : 7; radiusX: 6; radiusY: 5
                            direction: eyes.mood === "sleep" ? PathArc.Counterclockwise : PathArc.Clockwise }
                    }
                }
            }
        }
    }

    component Bars: Item {
        id: bars
        property color barColor: "#FFFFFF"
        readonly property bool live: notch.level >= 0
        width: 27; height: 18
        Repeater { model: 5
            delegate: Rectangle { required property int index
                x: index * 6; width: 3; radius: 1.5; color: bars.barColor
                property real hh: 5
                readonly property real target: 4 + notch.level * (8 + (index * 5) % 9) * 1.4
                height: bars.live ? Math.min(18, target) : hh
                Behavior on height { enabled: bars.live; NumberAnimation { duration: 70 } }
                y: (bars.height - height) / 2
                SequentialAnimation on hh { loops: Animation.Infinite; running: bars.visible && !bars.live
                    NumberAnimation { to: 6 + ((index * 7) % 5) * 3; duration: 260 + index * 70; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 4; duration: 260 + index * 55; easing.type: Easing.InOutSine } }
            } }
    }

    component Pill: Rectangle {
        id: pill
        property string label: ""
        property color fg: "#FFFFFF"
        property color bg: "#24242A"
        signal clicked()
        width: lbl.implicitWidth + 28; height: 30; radius: 15; color: bg
        opacity: pill.enabled ? 1 : 0.35
        scale: pm.pressed ? 0.95 : 1
        Behavior on scale { NumberAnimation { duration: 90 } }
        Text { id: lbl; anchors.centerIn: parent; text: pill.label; color: pill.fg
            font.family: th.font; font.pixelSize: 12; font.weight: Font.DemiBold }
        MouseArea { id: pm; anchors.fill: parent; enabled: pill.enabled; onClicked: pill.clicked() }
    }

    component RoundBtn: Rectangle {
        id: rb
        property string glyph: ""
        property string key: ""
        signal clicked()
        width: 34; height: 34; radius: 17
        color: rm.containsMouse ? "#FFFFFF" : "#1A1A1F"
        Behavior on color { ColorAnimation { duration: 120 } }
        Text { visible: rb.glyph !== "pointer"; anchors.centerIn: parent; text: rb.glyph; font.family: th.icons; font.pixelSize: 15
            color: rm.containsMouse ? "#000000" : th.text1 }
        Shape { visible: rb.glyph === "pointer"; anchors.centerIn: parent; width: 10; height: 15
            preferredRendererType: Shape.CurveRenderer
            ShapePath { strokeWidth: 1.2; strokeColor: rm.containsMouse ? "#000000" : th.text1; fillColor: "transparent"; joinStyle: ShapePath.RoundJoin
                startX: 0; startY: 0
                PathLine { x: 0; y: 12 } PathLine { x: 3; y: 9.4 } PathLine { x: 5.2; y: 14 }
                PathLine { x: 7; y: 13.2 } PathLine { x: 4.9; y: 8.6 } PathLine { x: 8.8; y: 8.4 } PathLine { x: 0; y: 0 } } }
        MouseArea { id: rm; anchors.fill: parent; hoverEnabled: true
            onEntered: notch.hoverKey(rb.key); onExited: notch.hoverKey(""); onClicked: rb.clicked() }
    }

    component TabIcon: Item {
        id: ti
        property string glyph: ""
        property string key: ""
        signal clicked()
        width: 22; height: 34
        Text { anchors.centerIn: parent; text: ti.glyph; font.family: th.icons; font.pixelSize: 14
            color: tm.containsMouse ? "#FFFFFF" : th.text2; scale: tm.containsMouse ? 1.15 : 1
            Behavior on scale { NumberAnimation { duration: 100 } } }
        MouseArea { id: tm; anchors.fill: parent; hoverEnabled: true
            onEntered: notch.hoverKey(ti.key); onExited: notch.hoverKey(""); onClicked: ti.clicked() }
    }

    Shortcut { sequence: "Escape"; onActivated: notch.setMode("idle") }
}
