// Onboarding.qml - first-run tour + setup. Made by Nur Al Mahtab.
import QtQuick
import QtQuick.Shapes
import QtQuick.Window

Window {
    id: win
    width: 780
    height: 600
    visible: true
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    title: ob.appName + " setup"
    x: Screen.virtualX + Math.round((Screen.width - width) / 2)
    y: Screen.virtualY + Math.round((Screen.height - height) / 2)

    property int step: 0
    property bool dark: false
    readonly property color accent: "#0A84C8"
    readonly property string fontFam: "Inter, Segoe UI Variable Display, Segoe UI"

    readonly property var steps: [
        { t: "Meet " + ob.appName, s: ob.appName + " lives at the top of your screen.", d: "meet" },
        { t: "Always close", s: "It stays tiny until you need it.", d: "close" },
        { t: "Take " + ob.appName + " anywhere", s: "It follows you across desktops and apps.", d: "anywhere" },
        { t: "One click away", s: "Hover or click to open Command, Dictate and Write.", d: "click" },
        { t: "Just say \"" + ob.wakePhrase + "\"", s: "Or hold Right Ctrl. Your words appear as you speak.", d: "say" },
        { t: "Working on it. Done.", s: "Quick tasks stay small, so you can keep going.", d: "work" },
        { t: "It asks first", s: "Before it does anything risky, it checks with you.", d: "asks" },
        { t: "Your to-do list", s: "Add things by voice. Tick them off and see what's done.", d: "todo" },
        { t: "Focus, then a break", s: "Say \"Start a focus session\". The break follows by itself.", d: "focus" },
        { t: "Music, with lyrics", s: "See the song, sing along, and pause or skip from the notch.", d: "music" },
        { t: "Windows, in the notch", s: "Volume, brightness, charging and reminders show up here.", d: "windows" },
        { t: "Dictate anywhere", s: "Hold Right Alt and talk. Text appears in the app you're in.", d: "dictate" },
        { t: "How should I address you?", s: "I'll use it now and then in a short reply.", d: "name", kind: "name" },
        { t: "Private by design", s: "Everything runs on this PC. Your audio is deleted as soon as it's transcribed.", d: "name", kind: "privacy" },
        { t: "Give " + ob.appName + " a brain", s: ob.hardware + " (" + ob.ramText + ")", d: "name", kind: "brain" },
        { t: "Connect Claude Code", s: "Optional. See what Claude is doing and approve actions from the notch.", d: "claude", kind: "claude" },
        { t: "You're all set", s: ob.appName + " lives at the top of your screen. Try one of these.", d: "done", kind: "done" }
    ]
    readonly property var cur: steps[step]
    readonly property real stageH: cur.kind !== undefined && cur.kind !== "done" ? 170 : 250

    Rectangle {
        id: card
        anchors.fill: parent
        anchors.margins: 14
        radius: 30
        color: "#F5F5F8"
        border.color: "#D9D9E0"; border.width: 1

        // ------- stage: a mini desktop with the live notch demo -------
        Rectangle {
            id: stage
            x: 14; y: 14; width: parent.width - 28; height: win.stageH; radius: 20; clip: true
            Behavior on height { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
            gradient: Gradient {
                GradientStop { position: 0; color: "#C9D6F2" }
                GradientStop { position: 1; color: "#E9DDF5" }
            }
            Shape { // soft wallpaper swoosh
                anchors.fill: parent; preferredRendererType: Shape.CurveRenderer
                ShapePath { strokeWidth: -1; fillColor: "#8C8FB4F0"
                    startX: -20; startY: 250
                    PathCubic { x: 760; y: 120; control1X: 200; control1Y: 90; control2X: 520; control2Y: 250 }
                    PathLine { x: 760; y: 260 } PathLine { x: -20; y: 260 } }
            }
            Loader { id: demo; anchors.fill: parent; sourceComponent: demoFor(win.cur.d); onLoaded: if (item) item.restart() }
        }

        // ------- text -------
        Text {
            id: title
            y: 14 + win.stageH + 22; width: parent.width; horizontalAlignment: Text.AlignHCenter
            text: win.cur.t; color: "#17171C"
            font.family: win.fontFam; font.pixelSize: 26; font.weight: Font.Bold
        }
        Text {
            y: 14 + win.stageH + 62; x: 60; width: parent.width - 120; horizontalAlignment: Text.AlignHCenter
            text: win.cur.s; color: "#5E5E68"; wrapMode: Text.WordWrap
            font.family: win.fontFam; font.pixelSize: 14
        }

        // ------- step content -------
        Item {
            x: 80; y: 14 + win.stageH + 112; width: parent.width - 160; height: 120

            // name
            Row {
                visible: win.cur.kind === "name"; anchors.horizontalCenter: parent.horizontalCenter; spacing: 12
                Rectangle { width: 260; height: 40; radius: 12; color: "#FFFFFF"; border.color: nameIn.activeFocus ? win.accent : "#CFCFD8"
                    TextInput { id: nameIn; anchors.fill: parent; anchors.margins: 12; text: ob.address; clip: true
                        font.family: win.fontFam; font.pixelSize: 15; color: "#17171C"; onEditingFinished: ob.setAddress(text) } }
                Rectangle { width: 90; height: 40; radius: 12; color: "#17171C"
                    Text { anchors.centerIn: parent; text: "Preview"; color: "#fff"; font.family: win.fontFam; font.pixelSize: 13; font.weight: Font.DemiBold }
                    MouseArea { anchors.fill: parent; onClicked: { ob.setAddress(nameIn.text); ob.preview("Good evening, {name}. All systems are running smoothly.") } } }
            }
            // privacy
            Column {
                visible: win.cur.kind === "privacy"; anchors.horizontalCenter: parent.horizontalCenter; spacing: 12; width: 420
                Toggle { label: "Listen for \"" + ob.wakePhrase + "\""; checked: ob.wake; onToggled: ob.setWake(on) }
                Toggle { label: "Start with Windows"; checked: false; onToggled: ob.setAutostart(on) }
                Row { spacing: 12
                    Text { text: "Microphone"; color: "#17171C"; font.family: win.fontFam; font.pixelSize: 14; width: 150; anchors.verticalCenter: parent.verticalCenter }
                    Text { text: ob.mics[0]; color: "#5E5E68"; font.family: win.fontFam; font.pixelSize: 14 } }
            }
            // brain
            Item {
                visible: win.cur.kind === "brain"; anchors.fill: parent
                Column { x: 0; width: 330; spacing: 6
                    Repeater { model: ob.models
                        delegate: Rectangle { required property var modelData; width: 330; height: 34; radius: 10; color: "#EDEDF2"
                            Text { x: 12; anchors.verticalCenter: parent.verticalCenter; text: modelData.name + "  " + modelData.size
                                color: "#17171C"; font.family: win.fontFam; font.pixelSize: 13; font.weight: Font.DemiBold }
                            Text { anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
                                text: "Coming soon"; color: "#8A8A94"; font.family: win.fontFam; font.pixelSize: 12 } } }
                    Rectangle { width: 330; height: 34; radius: 10; color: "#FFFFFF"; border.color: win.accent; border.width: 2
                        Text { x: 12; anchors.verticalCenter: parent.verticalCenter; text: "Not now (everything else works without one)"
                            color: "#17171C"; font.family: win.fontFam; font.pixelSize: 12; font.weight: Font.DemiBold } }
                }
                Column { x: 350; width: 270; spacing: 3
                    Text { text: "ANY PC"; color: "#8A8A94"; font.family: win.fontFam; font.pixelSize: 10; font.weight: Font.Bold }
                    Repeater { model: ["Voice commands", "Dictation in any app", "Music, timers, to-dos and the notch", "Claude Code approvals"]
                        delegate: Text { required property string modelData; text: "✓  " + modelData; color: "#17171C"; font.family: win.fontFam; font.pixelSize: 12 } }
                    Text { topPadding: 6; text: "WITH A MODEL (LATER)"; color: "#8A8A94"; font.family: win.fontFam; font.pixelSize: 10; font.weight: Font.Bold }
                    Repeater { model: ["Answers to questions", "Write and rewrite", "Summaries", "Commands said any way you like"]
                        delegate: Text { required property string modelData; text: "•  " + modelData; color: "#6B6B75"; font.family: win.fontFam; font.pixelSize: 12 } }
                }
            }
            // claude
            Column {
                visible: win.cur.kind === "claude"; anchors.horizontalCenter: parent.horizontalCenter; spacing: 12
                Rectangle { width: 240; height: 42; radius: 21; color: ob.claudeConnected ? "#34D399" : "#17171C"; anchors.horizontalCenter: parent.horizontalCenter
                    Text { anchors.centerIn: parent; text: ob.claudeConnected ? "Connected ✓" : "Connect Claude Code"; color: ob.claudeConnected ? "#000" : "#fff"
                        font.family: win.fontFam; font.pixelSize: 14; font.weight: Font.DemiBold }
                    MouseArea { anchors.fill: parent; onClicked: ob.connectClaude() } }
                Text { text: "Your settings are backed up first. Disconnect any time from the tray icon."; color: "#6B6B75"
                    font.family: win.fontFam; font.pixelSize: 12; anchors.horizontalCenter: parent.horizontalCenter }
            }
            // all set
            Column {
                visible: win.cur.kind === "done"; anchors.horizontalCenter: parent.horizontalCenter; spacing: 10
                Grid { columns: 2; spacing: 10; anchors.horizontalCenter: parent.horizontalCenter
                    Repeater { model: ["\"Start a focus session\"", "\"What's on my list?\"", "\"Play Billie Jean on Spotify\"", "\"Take a screenshot\""]
                        delegate: Rectangle { required property string modelData; width: 250; height: 34; radius: 12; color: "#FFFFFF"; border.color: "#E0E0E8"
                            Text { anchors.centerIn: parent; text: modelData; color: "#17171C"; font.family: win.fontFam; font.pixelSize: 12 } } } }
                Text { text: "Ask \"What can you do?\" any time."; color: "#6B6B75"; font.family: win.fontFam; font.pixelSize: 12; anchors.horizontalCenter: parent.horizontalCenter }
                Text { text: ob.credit; color: win.accent; font.family: win.fontFam; font.pixelSize: 13; font.weight: Font.DemiBold; anchors.horizontalCenter: parent.horizontalCenter }
            }
        }

        // ------- footer -------
        Text { // back
            visible: win.step > 0; x: 28; y: parent.height - 52; text: "‹ Back"; color: "#6B6B75"
            font.family: win.fontFam; font.pixelSize: 14
            MouseArea { anchors.fill: parent; anchors.margins: -10; onClicked: win.step-- }
        }
        Text { // skip
            visible: win.step < steps.length - 1; anchors.right: parent.right; anchors.rightMargin: 28; y: parent.height - 52
            text: "Skip"; color: "#8A8A94"; font.family: win.fontFam; font.pixelSize: 14
            MouseArea { anchors.fill: parent; anchors.margins: -10; onClicked: ob.finish() }
        }
        Rectangle {
            id: cont
            width: 200; height: 44; radius: 22; color: "#1B1B20"; anchors.horizontalCenter: parent.horizontalCenter
            y: parent.height - 66
            scale: cm.pressed ? 0.96 : 1
            Behavior on scale { NumberAnimation { duration: 90 } }
            Text { anchors.centerIn: parent; text: win.step === steps.length - 1 ? "Start using " + ob.appName : "Continue"; color: "#fff"
                font.family: win.fontFam; font.pixelSize: 14; font.weight: Font.DemiBold }
            MouseArea { id: cm; anchors.fill: parent; onClicked: win.step === steps.length - 1 ? ob.finish() : win.step++ }
        }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter; y: parent.height - 16; spacing: 6
            Repeater { model: steps.length
                delegate: Rectangle { required property int index; width: index === win.step ? 14 : 5; height: 5; radius: 2.5
                    color: index === win.step ? "#17171C" : "#C4C4CC"; Behavior on width { NumberAnimation { duration: 140 } } } }
        }
    }

    // drag the window by its card
    MouseArea { anchors.fill: parent; z: -1; property point p
        onPressed: (m) => p = Qt.point(m.x, m.y)
        onPositionChanged: (m) => { if (pressed) { win.x += m.x - p.x; win.y += m.y - p.y } } }
    Shortcut { sequence: "Right"; onActivated: if (win.step < steps.length - 1) win.step++ }
    Shortcut { sequence: "Left"; onActivated: if (win.step > 0) win.step-- }
    Shortcut { sequence: "Escape"; onActivated: ob.finish() }

    // ------------------------------------------------------------------ pieces
    component Toggle: Item {
        id: tg
        property string label: ""
        property bool checked: false
        signal toggled(bool on)
        width: 420; height: 30
        Text { text: tg.label; color: "#17171C"; font.family: win.fontFam; font.pixelSize: 14; anchors.verticalCenter: parent.verticalCenter }
        Rectangle { anchors.right: parent.right; width: 46; height: 26; radius: 13; anchors.verticalCenter: parent.verticalCenter
            color: tg.checked ? "#34C759" : "#C9C9D1"; Behavior on color { ColorAnimation { duration: 120 } }
            Rectangle { y: 2; x: tg.checked ? 22 : 2; width: 22; height: 22; radius: 11; color: "#fff"; Behavior on x { NumberAnimation { duration: 120 } } } }
        MouseArea { anchors.fill: parent; onClicked: { tg.checked = !tg.checked; tg.toggled(tg.checked) } }
    }

    component Eyes: Item {
        width: 40; height: 22
        property color tint: "#fff"
        property bool happy: false
        Repeater { model: 2
            delegate: Rectangle { required property int index; x: 5 + index * 20; y: 4; width: 7; height: happy ? 3 : 14; radius: 3.5; color: tint
                Behavior on height { NumberAnimation { duration: 80 } } } }
    }

    // A tiny notch used by every demo. Content goes inside.
    component MiniNotch: Item {
        id: mn
        property real w: 180
        property real h: 36
        property bool panel: false
        default property alias content: inner.data
        anchors.horizontalCenter: parent.horizontalCenter
        y: 0; width: w; height: h
        Behavior on w { NumberAnimation { duration: 280; easing.type: Easing.OutBack; easing.overshoot: 0.7 } }
        Behavior on h { NumberAnimation { duration: 280; easing.type: Easing.OutBack; easing.overshoot: 0.7 } }
        Rectangle { anchors.fill: parent; color: mn.panel ? "#0B0B0E" : "#000"; radius: 24
            Rectangle { x: 0; y: 0; width: parent.width; height: 24; color: parent.color } }
        Item { id: inner; anchors.fill: parent }
    }

    function demoFor(key) {
        switch (key) {
        case "meet": return dMeet
        case "close": return dClose
        case "anywhere": return dAnywhere
        case "click": return dClick
        case "say": return dSay
        case "work": return dWork
        case "asks": return dAsks
        case "todo": return dTodo
        case "focus": return dFocus
        case "music": return dMusic
        case "windows": return dWindows
        case "dictate": return dDictate
        case "claude": return dClaude
        default: return dBig
        }
    }

    Component { id: dBig; Item { function restart() {}
        Rectangle { anchors.centerIn: parent; width: 150; height: 80; radius: 40; color: "#111"
            Eyes { anchors.centerIn: parent; scale: 2.0; happy: win.cur.kind === "done" } } } }

    Component { id: dMeet; Item { function restart() {}
        MiniNotch { w: 210; h: 56; Eyes { anchors.centerIn: parent; anchors.verticalCenterOffset: -2; scale: 1.2 } } } }

    Component { id: dClose; Item { id: r; property bool out: false; function restart() { tm.restart() }
        Timer { id: tm; interval: 1100; repeat: true; running: true; onTriggered: r.out = !r.out }
        MiniNotch { w: 180; h: r.out ? 36 : 4; clip: true; Eyes { anchors.centerIn: parent; anchors.verticalCenterOffset: -2; opacity: r.out ? 1 : 0 } } } }

    Component { id: dAnywhere; Item { id: r; property bool out: false; function restart() { tm.restart() }
        Timer { id: tm; interval: 1500; repeat: true; running: true; onTriggered: r.out = !r.out }
        MiniNotch { visible: !r.out; w: 180; h: 36; Eyes { anchors.centerIn: parent; anchors.verticalCenterOffset: -2 } }
        Rectangle { visible: r.out; x: parent.width / 2 - 70; y: 80; width: 140; height: 100; radius: 30; color: "#0B0B0E"
            Eyes { x: 50; y: 22; scale: 1.2 }
            Row { x: 34; y: 66; spacing: 14
                Repeater { model: ["↖", "♫", "✎"]
                    delegate: Text { required property string modelData; text: modelData; color: "#fff"; font.pixelSize: 16 } } } } } }

    Component { id: dClick; Item { id: r; property int i: 0; function restart() { tm.restart() }
        readonly property var names: [["Dictate", "Talk, and your words appear where you type."], ["Write", "Say what you need, and it writes it for you."], ["Widgets", "The time around the world, your list, battery and weather."], ["Controls", "Volume, brightness, Wi-Fi, power mode and a screenshot."]]
        Timer { id: tm; interval: 1400; repeat: true; running: true; onTriggered: r.i = (r.i + 1) % 4 }
        MiniNotch { w: 520; h: 140; panel: true
            Row { x: 26; y: 14; spacing: 8
                Repeater { model: 3; delegate: Rectangle { required property int index; width: 30; height: 30; radius: 15
                    color: (r.i === 0 && index === 1) || (r.i === 1 && index === 2) ? "#fff" : "#1A1A1F" } } }
            Rectangle { x: 26; y: 62; width: 76; height: 40; radius: 20; color: "#17171C"; Eyes { anchors.centerIn: parent; scale: 0.8 } }
            Column { x: 120; y: 62; spacing: 4
                Text { text: r.names[r.i][0]; color: "#fff"; font.family: win.fontFam; font.pixelSize: 16; font.weight: Font.DemiBold }
                Text { text: r.names[r.i][1]; color: "#9A9AA3"; font.family: win.fontFam; font.pixelSize: 11; width: 370; elide: Text.ElideRight } } } } }

    Component { id: dSay; Item { id: r; property string full: "Remind me to call Mom at six"; property int n: 0; function restart() { n = 0; tm.restart() }
        Timer { id: tm; interval: 70; repeat: true; running: true; onTriggered: { r.n = (r.n + 1) % (r.full.length + 25) } }
        MiniNotch { w: 420; h: 44
            Eyes { x: 20; anchors.verticalCenter: parent.verticalCenter; anchors.verticalCenterOffset: -2 }
            Text { x: 76; anchors.verticalCenter: parent.verticalCenter; text: r.full.substring(0, Math.min(r.n, r.full.length)); color: "#fff"
                font.family: win.fontFam; font.pixelSize: 13; font.weight: Font.Medium } } } }

    Component { id: dWork; Item { id: r; property bool done: false; function restart() { tm.restart() }
        Timer { id: tm; interval: 1500; repeat: true; running: true; onTriggered: r.done = !r.done }
        MiniNotch { w: r.done ? 260 : 300; h: 44
            Eyes { x: 20; anchors.verticalCenter: parent.verticalCenter; anchors.verticalCenterOffset: -2; tint: r.done ? "#fff" : "#5CE1FF"; happy: r.done }
            Text { x: 76; anchors.verticalCenter: parent.verticalCenter; text: r.done ? "Done" : "Working on it"; color: "#fff"
                font.family: win.fontFam; font.pixelSize: 13; font.weight: Font.Medium }
            Text { visible: r.done; anchors.right: parent.right; anchors.rightMargin: 18; anchors.verticalCenter: parent.verticalCenter; text: "✓"; color: "#34D399"; font.pixelSize: 17 } } } }

    Component { id: dAsks; Item { function restart() {}
        MiniNotch { w: 450; h: 96; panel: true
            Eyes { x: 24; y: 20; tint: "#fff" }
            Text { x: 84; y: 16; text: "Send the slides to Sam?"; color: "#fff"; font.family: win.fontFam; font.pixelSize: 14; font.weight: Font.DemiBold }
            Text { x: 84; y: 38; text: "I will only do it if you say so."; color: "#9A9AA3"; font.family: win.fontFam; font.pixelSize: 12 }
            Row { anchors.right: parent.right; anchors.rightMargin: 24; y: 56; spacing: 8
                Rectangle { width: 74; height: 28; radius: 14; color: "#24242A"; Text { anchors.centerIn: parent; text: "Not now"; color: "#fff"; font.pixelSize: 12; font.weight: Font.DemiBold } }
                Rectangle { width: 74; height: 28; radius: 14; color: "#fff"; Text { anchors.centerIn: parent; text: "Confirm"; color: "#000"; font.pixelSize: 12; font.weight: Font.DemiBold } } } } } }

    Component { id: dTodo; Item { id: r; property int done: 1; function restart() { tm.restart() }
        Timer { id: tm; interval: 1200; repeat: true; running: true; onTriggered: r.done = r.done % 4 + 1 }
        MiniNotch { w: 520; h: 150; panel: true
            Column { x: 30; y: 28
                Text { text: "To-do"; color: "#9A9AA3"; font.pixelSize: 11 }
                Text { text: r.done + "/4"; color: "#fff"; font.pixelSize: 36; font.weight: Font.DemiBold } }
            Column { x: 190; y: 22; spacing: 8
                Repeater { model: ["Buy coffee beans", "Book the dentist", "Reply to Sam", "Call Mom at six"]
                    delegate: Row { required property int index; required property string modelData; spacing: 10
                        Rectangle { width: 16; height: 16; radius: 8; color: index < r.done ? "#34D399" : "transparent"; border.color: index < r.done ? "#34D399" : "#5E5E66"; border.width: 1.5 }
                        Text { text: modelData; color: index < r.done ? "#5E5E66" : "#fff"; font.pixelSize: 13; font.strikeout: index < r.done } } } } } } }

    Component { id: dFocus; Item { id: r; property int s: 300; function restart() { s = 300; tm.restart() }
        Timer { id: tm; interval: 120; repeat: true; running: true; onTriggered: r.s = r.s > 0 ? r.s - 7 : 300 }
        MiniNotch { w: 520; h: 130; panel: true
            Shape { x: 40; y: 28; width: 74; height: 74; preferredRendererType: Shape.CurveRenderer
                ShapePath { strokeWidth: 6; strokeColor: "#1F1F25"; fillColor: "transparent"; PathAngleArc { centerX: 37; centerY: 37; radiusX: 31; radiusY: 31; startAngle: 0; sweepAngle: 360 } }
                ShapePath { strokeWidth: 6; strokeColor: "#34D399"; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                    PathAngleArc { centerX: 37; centerY: 37; radiusX: 31; radiusY: 31; startAngle: -90; sweepAngle: 360 * Math.max(0.02, r.s / 300) } } }
            Text { x: 140; y: 34; text: Math.floor(Math.max(0, r.s) / 60) + ":" + ("0" + Math.max(0, r.s) % 60).slice(-2); color: "#fff"; font.pixelSize: 38; font.weight: Font.DemiBold }
            Text { x: 142; y: 80; text: "Focus time"; color: "#9A9AA3"; font.pixelSize: 12 } } } }

    Component { id: dMusic; Item { function restart() {}
        MiniNotch { w: 520; h: 150; panel: true
            Rectangle { anchors.fill: parent; radius: 24; gradient: Gradient { GradientStop { position: 0; color: "#3A1712" } GradientStop { position: 1; color: "#1A0B09" } } }
            Rectangle { x: 30; y: 28; width: 60; height: 60; radius: 12; gradient: Gradient { GradientStop { position: 0; color: "#FFB347" } GradientStop { position: 1; color: "#E5484D" } } }
            Column { x: 106; y: 32; spacing: 2
                Text { text: "Golden Hour"; color: "#fff"; font.pixelSize: 15; font.weight: Font.DemiBold }
                Text { text: "The Quiet Hours"; color: "#D9A79F"; font.pixelSize: 12 } }
            Column { x: 300; y: 36; spacing: 8
                Text { text: "The light comes in low"; color: "#8A5A53"; font.pixelSize: 12 }
                Text { text: "And everything slows"; color: "#fff"; font.pixelSize: 14; font.weight: Font.DemiBold }
                Text { text: "We follow it home"; color: "#8A5A53"; font.pixelSize: 12 } } } } }

    Component { id: dWindows; Item { id: r; property int i: 0; function restart() { tm.restart() }
        Timer { id: tm; interval: 1500; repeat: true; running: true; onTriggered: r.i = (r.i + 1) % 3 }
        MiniNotch { w: 380; h: r.i === 2 ? 70 : 44; panel: r.i === 2
            Eyes { x: 20; y: r.i === 2 ? 16 : 11 }
            Text { visible: r.i === 0; x: 76; anchors.verticalCenter: parent.verticalCenter; text: "Volume"; color: "#fff"; font.pixelSize: 13 }
            Rectangle { visible: r.i === 0; x: 200; anchors.verticalCenter: parent.verticalCenter; width: 120; height: 5; radius: 2.5; color: "#2B2B31"
                Rectangle { width: 66; height: 5; radius: 2.5; color: "#fff" } }
            Text { visible: r.i === 1; x: 76; anchors.verticalCenter: parent.verticalCenter; text: "Charging  ·  70%"; color: "#fff"; font.pixelSize: 13 }
            Text { visible: r.i === 2; x: 76; y: 14; text: "Time for water"; color: "#fff"; font.pixelSize: 14; font.weight: Font.DemiBold }
            Text { visible: r.i === 2; x: 76; y: 36; text: "3 of 8 glasses today"; color: "#9A9AA3"; font.pixelSize: 12 } } } }

    Component { id: dDictate; Item { id: r; property string full: "Hey Sam, I'm running fifteen minutes late."; property int n: 0; function restart() { n = 0; tm.restart() }
        Timer { id: tm; interval: 60; repeat: true; running: true; onTriggered: r.n = (r.n + 1) % (r.full.length + 30) }
        MiniNotch { w: 300; h: 44
            Rectangle { x: 14; anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4; color: "#FF3B30" }
            Eyes { x: 32; anchors.verticalCenter: parent.verticalCenter; anchors.verticalCenterOffset: -2 }
            Text { x: 92; anchors.verticalCenter: parent.verticalCenter; text: "Listening"; color: "#fff"; font.pixelSize: 13 } }
        Rectangle { x: parent.width / 2 - 170; y: 100; width: 340; height: 110; radius: 10; color: "#fff"; border.color: "#D0D0D8"
            Text { x: 14; y: 14; width: 312; wrapMode: Text.WordWrap; text: r.full.substring(0, Math.min(r.n, r.full.length)) + (r.n % 10 < 5 ? "|" : ""); color: "#17171C"; font.pixelSize: 14 } } } }

    Component { id: dClaude; Item { id: r; property int i: 0; function restart() { tm.restart() }
        Timer { id: tm; interval: 1600; repeat: true; running: true; onTriggered: r.i = (r.i + 1) % 3 }
        MiniNotch { w: r.i === 1 ? 480 : 440; h: r.i === 1 ? 92 : 44; panel: r.i === 1
            Eyes { x: 20; y: r.i === 1 ? 18 : 11; tint: r.i === 0 ? "#5CE1FF" : r.i === 1 ? "#FFB340" : "#34D399"; happy: r.i === 2 }
            Text { x: 76; y: r.i === 1 ? 16 : 14; text: r.i === 0 ? "Claude is editing server.ts" : r.i === 1 ? "Claude needs your permission" : "Claude finished in 4m 12s"; color: "#fff"; font.pixelSize: 13; font.weight: Font.DemiBold }
            Row { visible: r.i === 1; anchors.right: parent.right; anchors.rightMargin: 24; y: 54; spacing: 8
                Rectangle { width: 64; height: 28; radius: 14; color: "#24242A"; Text { anchors.centerIn: parent; text: "Deny"; color: "#fff"; font.pixelSize: 12; font.weight: Font.DemiBold } }
                Rectangle { width: 74; height: 28; radius: 14; color: "#FFB340"; Text { anchors.centerIn: parent; text: "Approve"; color: "#000"; font.pixelSize: 12; font.weight: Font.DemiBold } } } } } }
}
