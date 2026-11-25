// Settings.qml - the Settings window. Made by Nur Al Mahtab.
import QtQuick
import QtQuick.Window

Window {
    id: win
    width: 900
    height: 740
    minimumWidth: 780
    minimumHeight: 520
    visible: true
    color: "#F3F3F7"
    title: sc.appName + " Settings"

    property int page: 0
    property bool autostart: false
    property string confirming: ""          // "wipe" or "reset": two-step confirmation for destructive buttons
    readonly property string fontFam: "Inter, Segoe UI Variable Display, Segoe UI"
    readonly property color accent: "#0A84C8"
    readonly property color ink: "#17171C"
    readonly property color sub: "#6B6B75"
    readonly property var v: sc.values
    readonly property var pages: ["General", "Voice", "Listening", "AI brain", "Claude Code", "Privacy", "About"]
    readonly property var icons: ["", "", "", "", "", "", ""]

    Component.onCompleted: autostart = sc.autostartOn()
    Connections { target: sc; function onToast(msg) { toastTimer.restart() } }
    Timer { id: toastTimer; interval: 5000; onTriggered: sc.clearMessage() }

    // ---------------------------------------------------------------- sidebar
    Rectangle {
        id: side
        width: 200; height: parent.height; color: "#E9E9EF"
        Text { x: 22; y: 22; text: sc.appName; color: win.ink; font.family: win.fontFam; font.pixelSize: 22; font.weight: Font.Bold }
        Text { x: 22; y: 52; text: "Settings"; color: win.sub; font.family: win.fontFam; font.pixelSize: 13 }
        Column {
            x: 10; y: 92; width: parent.width - 20; spacing: 2
            Repeater {
                model: win.pages
                delegate: Rectangle {
                    required property int index
                    required property string modelData
                    width: parent.width; height: 38; radius: 10
                    color: win.page === index ? "#FFFFFF" : (ma.containsMouse ? "#F1F1F6" : "transparent")
                    Text { x: 14; anchors.verticalCenter: parent.verticalCenter; text: win.icons[index]
                        font.family: "Segoe Fluent Icons"; font.pixelSize: 15
                        color: win.page === index ? win.accent : win.sub }
                    Text { x: 44; anchors.verticalCenter: parent.verticalCenter; text: modelData
                        font.family: win.fontFam; font.pixelSize: 14; font.weight: win.page === index ? Font.DemiBold : Font.Normal
                        color: win.ink }
                    MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; onClicked: { win.page = index; win.confirming = "" } }
                }
            }
        }
        Text { x: 22; y: parent.height - 34; text: sc.credit; color: win.accent
            font.family: win.fontFam; font.pixelSize: 12; font.weight: Font.Medium }
    }

    // ---------------------------------------------------------------- content
    Item {
        x: side.width; width: parent.width - side.width; height: parent.height

        Text { id: heading; x: 36; y: 26; text: win.pages[win.page]; color: win.ink
            font.family: win.fontFam; font.pixelSize: 26; font.weight: Font.Bold }

        // restart banner
        Rectangle {
            visible: sc.restartNeeded; anchors.right: parent.right; anchors.rightMargin: 36; y: 30
            width: bannerText.implicitWidth + 28; height: 30; radius: 15; color: "#FFF1D6"
            Text { id: bannerText; anchors.centerIn: parent; text: "Some changes apply after you restart " + sc.appName
                color: "#8A5A00"; font.family: win.fontFam; font.pixelSize: 12; font.weight: Font.Medium }
        }

        Flickable {
            id: flick
            x: 0; y: 78; width: parent.width; height: parent.height - 78 - 56
            contentWidth: width; contentHeight: pageHolder.childrenRect.height + 240
            clip: true; boundsBehavior: Flickable.StopAtBounds
            Item {
                id: pageHolder
                x: 36; width: flick.width - 72

                // ============ GENERAL ============
                Column { visible: win.page === 0; width: parent.width; spacing: 0
                    SRow { title: "Your name"; desc: "What " + sc.appName + " calls you in replies."
                        Rectangle { width: 220; height: 36; radius: 10; color: "#fff"; border.color: nameIn.activeFocus ? win.accent : "#CFCFD8"
                            TextInput { id: nameIn; anchors.fill: parent; anchors.margins: 10; text: win.v.address; clip: true
                                font.family: win.fontFam; font.pixelSize: 14; color: win.ink
                                onEditingFinished: sc.set("address", text) } } }
                    SRow { title: "Start with Windows"; desc: "Open " + sc.appName + " automatically when you sign in."
                        Switch2 { checked: win.autostart; onToggled: { win.autostart = on; sc.setAutostart(on) } } }
                    SRow { title: "Hide when idle"; desc: "After a few seconds of nothing, Jarvis slides up out of sight. Move the mouse to the very top edge of the screen to bring it back. It also comes back by itself for reminders, approvals and \"Hey Jarvis\"."
                        Switch2 { checked: win.v.autohide; onToggled: sc.set("autohide", on) } }
                    SRow { visible: win.v.autohide; title: "Hide after"; desc: "How long it waits before sliding away."
                        Slid { from: 2; to: 60; step: 1; value: win.v.autohide_seconds; suffix: " sec"; onMoved: sc.set("autohide_seconds", v) } }
                    SRow { title: "Position"; desc: "Drag Jarvis left or right by any empty part of it. It remembers where you put it."
                        Btn { label: "Put back in the middle"; onClicked: sc.resetNotchPosition() } }
                    SRow { title: "Fall asleep after"; desc: "When idle, the notch dims and shows the moon."
                        Slid { from: 1; to: 60; step: 1; value: win.v.sleep_after_minutes; suffix: " min"; onMoved: sc.set("sleep_after_minutes", v) } }
                    SRow { title: "Do not disturb"; desc: "Stay asleep and silent. Reminders wait until you turn this off."
                        Switch2 { checked: win.v.dnd; onToggled: sc.set("dnd", on) } }
                    SRow { title: "Weather city"; desc: win.v.weather_place !== "" ? "Showing: " + win.v.weather_place + ". Only the city name is sent, to Open-Meteo." : "Type a city for the Widgets weather. Only the name is sent, to Open-Meteo."
                        Rectangle { width: 220; height: 36; radius: 10; color: "#fff"; border.color: cityIn.activeFocus ? win.accent : "#CFCFD8"
                            TextInput { id: cityIn; anchors.fill: parent; anchors.margins: 10; text: win.v.weather_city; clip: true
                                font.family: win.fontFam; font.pixelSize: 14; color: win.ink; onEditingFinished: sc.setWeatherCity(text) } } }
                    SRow { title: "Temperature unit"; desc: ""
                        Seg { options: ["C", "F"]; labels: ["Celsius", "Fahrenheit"]; current: win.v.weather_units; onPicked: sc.set("weather_units", value) } }
                    SRow { title: "Favourite sites"; desc: "Shown in the Menu panel, like youtube.com, github.com. Up to eight."
                        Rectangle { width: 320; height: 36; radius: 10; color: "#fff"; border.color: sitesIn.activeFocus ? win.accent : "#CFCFD8"
                            TextInput { id: sitesIn; anchors.fill: parent; anchors.margins: 10; text: win.v.websites.map(function(u) { return u.replace(/^https?:\/\//, "") }).join(", "); clip: true
                                font.family: win.fontFam; font.pixelSize: 13; color: win.ink; onEditingFinished: sc.set("websites", text) } } }
                    SRow { title: "World clocks"; desc: "Up to four, like London=Europe/London, Tokyo=Asia/Tokyo."
                        Rectangle { width: 320; height: 36; radius: 10; color: "#fff"; border.color: clkIn.activeFocus ? win.accent : "#CFCFD8"
                            TextInput { id: clkIn; anchors.fill: parent; anchors.margins: 10; text: win.v.clocks.join(", "); clip: true
                                font.family: win.fontFam; font.pixelSize: 13; color: win.ink; onEditingFinished: sc.set("clocks", text) } } }
                    SRow { title: "Keep the screen on too"; desc: "When keeping the laptop awake, also stop the display from turning off."
                        Switch2 { checked: win.v.awake_display; onToggled: sc.set("awake_display", on) } }
                    SRow { title: "Stay awake while Claude Code works"; desc: "No sleeping mid-task. Released two minutes after Claude is idle."
                        Switch2 { checked: win.v.awake_claude; onToggled: sc.set("awake_claude", on) } }
                    SRow { title: "Stay awake during focus sessions"; desc: "Released when the session ends or you stop it."
                        Switch2 { checked: win.v.awake_focus; onToggled: sc.set("awake_focus", on) } }
                    SRow { title: "Lid and sleep settings"; desc: "Keep awake cannot stop the lid from sleeping the laptop. That is a Windows setting."
                        Btn { label: "Open Windows settings"; onClicked: sc.openPowerSettings() } }
                    SRow { title: "Greeting"; desc: "A short hello the first time it starts each day."
                        Switch2 { checked: win.v.greeting; onToggled: sc.set("greeting", on) } }
                }

                // ============ VOICE ============
                Column { visible: win.page === 1; width: parent.width; spacing: 0
                    SRow { title: "Speak replies"; desc: "Voice always speaks when you used your voice."
                        Seg { options: ["off", "voice", "always"]; labels: ["Never", "By voice", "Always"]; current: win.v.speak_replies
                            onPicked: sc.set("speak_replies", value) } }
                    SRow { title: "Personality"; desc: "Changes the voice's wording and greeting."
                        Seg { options: sc.personas; labels: ["Butler", "Friendly", "Neutral", "Minimal"]; current: win.v.persona
                            onPicked: sc.set("persona", value) } }
                    SRow { title: "Speed"; desc: "How fast replies are spoken."
                        Row { spacing: 14
                            Slid { from: 0.8; to: 1.4; step: 0.05; value: win.v.voice_speed; suffix: "x"; decimals: 2; onMoved: sc.set("voice_speed", v) }
                            Btn { label: "Preview"; onClicked: sc.previewVoice() } } }
                }

                // ============ LISTENING ============
                Column { visible: win.page === 2; width: parent.width; spacing: 0
                    SRow { title: "Wake word"; desc: "Say “" + "Hey " + sc.appName + "” to talk hands-free. The microphone listens locally; nothing is saved."
                        Switch2 { checked: win.v.wake_word; onToggled: sc.set("wake_word", on) } }
                    SRow { title: "Command key"; desc: "Hold to give a command."
                        Combo { options: sc.keyChoices; current: win.v.ptt_command_key; onPicked: sc.set("ptt_command_key", value) } }
                    SRow { title: "Dictate key"; desc: "Hold to type what you say into any app."
                        Combo { options: sc.keyChoices; current: win.v.ptt_dictate_key; onPicked: sc.set("ptt_dictate_key", value) } }
                    SRow { title: "Microphone"; desc: "Which input to use."
                        Combo { width: 280; options: sc.mics; current: win.v.mic_device; onPicked: sc.set("mic_device", value) } }
                    SRow { title: "Speech model"; desc: "Smaller is faster. Larger understands more but is slow on this PC."
                        Seg { options: sc.sttChoices; labels: ["Fast", "Balanced", "Accurate"]; current: win.v.stt_model; onPicked: sc.set("stt_model", value) } }
                }

                // ============ AI BRAIN ============
                Column { visible: win.page === 3; width: parent.width; spacing: 0
                    SRow { title: "Status"; desc: win.v.llm_provider === "local" ? "Runs fully on this PC. Without it, commands still work; with it, " + sc.appName + " also answers questions and writes for you." : "Questions go to the cloud service you chose. Commands still run on this PC, and if the service cannot be reached the local brain answers (if installed)."
                        Text { text: sc.brainStatus; font.family: win.fontFam; font.pixelSize: 14; font.weight: Font.DemiBold
                            color: (sc.brainStatus === "Installed" || sc.brainStatus === "Cloud ready") ? "#1E9E5B" : win.ink } }
                    SRow { title: "Brain source"; desc: sc.cloudNote
                        Seg { options: sc.providers.map(function(p) { return p.id }); labels: sc.providers.map(function(p) { return p.label })
                            current: win.v.llm_provider; onPicked: sc.set("llm_provider", value) } }
                    SRow { visible: win.v.llm_provider !== "local"; title: "Model name"; desc: sc.cloudModelHint !== "" ? "Leave empty to use " + sc.cloudModelHint + ". Names change over time." : "Required: the model name your service uses."
                        Rectangle { width: 230; height: 36; radius: 10; color: "#fff"; border.color: "#CFCFD8"; clip: true
                            TextInput { anchors.fill: parent; anchors.margins: 9; text: win.v.cloud_model; font.family: win.fontFam; font.pixelSize: 13; color: win.ink; selectByMouse: true; clip: true
                                onEditingFinished: sc.set("cloud_model", text) } } }
                    SRow { visible: win.v.llm_provider === "custom"; title: "Web address"; desc: "An OpenAI-compatible service, for example https://api.example.com/v1"
                        Rectangle { width: 260; height: 36; radius: 10; color: "#fff"; border.color: "#CFCFD8"; clip: true
                            TextInput { anchors.fill: parent; anchors.margins: 9; text: win.v.cloud_base; font.family: win.fontFam; font.pixelSize: 13; color: win.ink; selectByMouse: true; clip: true
                                onEditingFinished: sc.set("cloud_base", text) } } }
                    SRow { visible: win.v.llm_provider !== "local"; title: "API key"; desc: (sc.cloudHasKey ? "A key is saved in Windows. " : (sc.cloudKeysUrl !== "" ? "Get one at " + sc.cloudKeysUrl + ". " : "")) + "It is stored in Windows Credential Manager, never in a file."
                        Row { spacing: 8
                            Rectangle { width: 170; height: 36; radius: 10; color: "#fff"; border.color: "#CFCFD8"; clip: true
                                TextInput { id: apiKey; anchors.fill: parent; anchors.margins: 9; echoMode: TextInput.Password; font.family: win.fontFam; font.pixelSize: 13; color: win.ink; selectByMouse: true; clip: true }
                                Text { visible: apiKey.text === ""; anchors.verticalCenter: parent.verticalCenter; x: 9; text: sc.cloudHasKey ? "saved" : "paste key"; font.family: win.fontFam; font.pixelSize: 13; color: "#9A9AA5" } }
                            Btn { label: "Save"; kind: "primary"; enabled: apiKey.text.trim() !== ""; onClicked: { sc.saveApiKey(apiKey.text); apiKey.text = "" } }
                            Btn { label: "Test"; onClicked: sc.testCloud() }
                            Btn { label: "Remove"; kind: "danger"; enabled: sc.cloudHasKey; onClicked: sc.removeApiKey() } } }
                    SRow { visible: win.v.llm_provider !== "local" && sc.cloudResult !== ""; title: "Test result"
                        desc: sc.cloudResult
                        Text { text: sc.cloudResult.indexOf("Connected") === 0 ? "OK" : (sc.cloudResult.indexOf("Testing") === 0 ? "..." : "Problem"); font.family: win.fontFam; font.pixelSize: 14; font.weight: Font.DemiBold
                            color: sc.cloudResult.indexOf("Connected") === 0 ? "#1E9E5B" : (sc.cloudResult.indexOf("Testing") === 0 ? win.ink : "#B3261E") } }
                    SRow { visible: win.v.llm_provider === "local"; title: "Model"; desc: "Qwen3 1.7B is quick. The 4B model is smarter but slow on this PC."
                        Seg { options: sc.brainModels.map(function(m) { return m.id }); labels: sc.brainModels.map(function(m) { return m.name })
                            current: win.v.llm_model; onPicked: sc.set("llm_model", value) } }
                    SRow { title: "Add your own model"; desc: "Paste the full path of a .gguf file you already have. It is copied into Jarvis's own folder (up to 8)."
                        Row { spacing: 10
                            Rectangle { width: 220; height: 36; radius: 10; color: "#fff"; border.color: "#CFCFD8"; clip: true
                                TextInput { id: ggufPath; anchors.fill: parent; anchors.margins: 9; font.family: win.fontFam; font.pixelSize: 13; color: win.ink; selectByMouse: true; clip: true }
                                Text { visible: ggufPath.text === ""; anchors.verticalCenter: parent.verticalCenter; x: 9; text: "D:/models/my-model.gguf"; font.family: win.fontFam; font.pixelSize: 13; color: "#9A9AA5" } }
                            Btn { label: "Import"; kind: "primary"; enabled: ggufPath.text.trim() !== ""; onClicked: { sc.importModel(ggufPath.text); ggufPath.text = "" } } } }
                    SRow { title: "Download or remove"; desc: "Downloads once. The model unloads after ten idle minutes to free memory."
                        Row { spacing: 10
                            Btn { label: sc.brainStatus === "Installed" ? "Re-download" : "Download"; kind: "primary"
                                enabled: sc.brainStatus.indexOf("Downloading") !== 0; onClicked: sc.downloadBrain() }
                            Btn { label: "Remove"; kind: "danger"; enabled: sc.brainStatus === "Installed"; onClicked: sc.removeBrain() } } }
                }

                // ============ CLAUDE CODE ============
                Column { visible: win.page === 4; width: parent.width; spacing: 0
                    SRow { title: "Claude Code"; desc: "Shows what Claude is doing and lets you approve actions from the notch. Your own hooks are never touched."
                        Btn { label: sc.claudeConnected ? "Disconnect" : "Connect"; kind: sc.claudeConnected ? "danger" : "primary"
                            onClicked: sc.claudeConnected ? sc.disconnectClaude() : sc.connectClaude() } }
                    SRow { title: "Claude Code on the web"; desc: "See what Claude is doing on claude.ai/code. Needs the Jarvis browser extension (in the extension folder). Only a state and a short label are sent, never your conversation."
                        Switch2 { checked: win.v.claude_web; onToggled: sc.set("claude_web", on) } }
                    SRow { visible: win.v.claude_web; title: "Pairing code"; desc: "Paste this into the extension's options page. Regenerate it any time to lock a browser out."
                        Row { spacing: 10
                            Rectangle { width: 130; height: 36; radius: 10; color: "#fff"; border.color: "#CFCFD8"
                                Text { anchors.centerIn: parent; text: sc.pairCode; font.family: "Consolas"; font.pixelSize: 16; font.weight: Font.DemiBold; color: win.ink } }
                            Btn { label: "New code"; onClicked: sc.regenPairCode() } } }
                    SRow { title: "Approval timeout"; desc: "If you don't answer, Claude Code's own prompt appears. Nothing is ever auto-approved."
                        Slid { from: 5; to: 120; step: 5; value: win.v.claude_approval_timeout; suffix: " s"; onMoved: sc.set("claude_approval_timeout", v) } }
                    SRow { title: "Hide commands and file names"; desc: "Show only “Running a command” instead of the command itself."
                        Switch2 { checked: win.v.claude_hide_details; onToggled: sc.set("claude_hide_details", on) } }
                    SRow { title: "Stay quiet when the terminal is in front"; desc: "No prompts or speech if you're already looking at Claude."
                        Switch2 { checked: win.v.claude_quiet_when_focused; onToggled: sc.set("claude_quiet_when_focused", on) } }
                    SRow { title: "Speak when Claude finishes"; desc: ""
                        Switch2 { checked: win.v.speak_done; onToggled: sc.set("speak_done", on) } }
                    SRow { title: "Speak when Claude needs you"; desc: ""
                        Switch2 { checked: win.v.speak_needs; onToggled: sc.set("speak_needs", on) } }
                    SRow { title: "Speak when Claude hits an error"; desc: ""
                        Switch2 { checked: win.v.speak_error; onToggled: sc.set("speak_error", on) } }
                    SRow { title: "Run the Claude bridge"; desc: "The local listener that receives Claude Code events. Applies after a restart."
                        Switch2 { checked: win.v.claude_bridge; onToggled: sc.set("claude_bridge", on) } }
                }

                // ============ PRIVACY ============
                Column { visible: win.page === 5; width: parent.width; spacing: 0
                    SRow { title: "Synced lyrics"; desc: "Asks lrclib.net for lyrics using only the song title, artist and length. Off keeps music fully offline."
                        Switch2 { checked: win.v.lyrics; onToggled: sc.set("lyrics", on) } }
                    SRow { title: "Clipboard shelf"; desc: "Keeps your recent copies for the notch's Shelf. Memory only: never saved to disk. Passwords and anything marked \u201Cdo not record\u201D are skipped."
                        Row { spacing: 12
                            Btn { label: "Clear"; onClicked: sc.clearShelf() }
                            Switch2 { checked: win.v.shelf_enabled; onToggled: sc.set("shelf_enabled", on) } } }
                    SRow { title: "Export my data"; desc: "Saves your list, reminders and settings as a readable file in Documents."
                        Btn { label: "Export"; onClicked: sc.exportData() } }
                    SRow { title: "Erase my list and reminders"; desc: "Permanently deletes them. Settings are kept."
                        Row { spacing: 8
                            Btn { label: win.confirming === "wipe" ? "Yes, erase" : "Erase..."; kind: "danger"
                                onClicked: { if (win.confirming === "wipe") { sc.wipeData(); win.confirming = "" } else win.confirming = "wipe" } }
                            Btn { visible: win.confirming === "wipe"; label: "Cancel"; onClicked: win.confirming = "" } } }
                    SRow { title: "Reset all settings"; desc: "Back to defaults. Your list and reminders are kept."
                        Row { spacing: 8
                            Btn { label: win.confirming === "reset" ? "Yes, reset" : "Reset..."; kind: "danger"
                                onClicked: { if (win.confirming === "reset") { sc.resetSettings(); win.confirming = "" } else win.confirming = "reset" } }
                            Btn { visible: win.confirming === "reset"; label: "Cancel"; onClicked: win.confirming = "" } } }
                    Text { width: parent.width; topPadding: 22; wrapMode: Text.WordWrap; color: win.sub
                        font.family: win.fontFam; font.pixelSize: 12
                        text: "Audio is kept in memory only and discarded as soon as it is transcribed. Speech recognition, the wake word, the voice and the AI brain all run on this PC. There is no account and no telemetry." }
                }

                // ============ ABOUT ============
                Column { visible: win.page === 6; width: parent.width; spacing: 10
                    Text { text: sc.appName + "  " + sc.version; color: win.ink; font.family: win.fontFam; font.pixelSize: 20; font.weight: Font.DemiBold }
                    Text { text: sc.credit; color: win.accent; font.family: win.fontFam; font.pixelSize: 15; font.weight: Font.DemiBold }
                    Text { width: parent.width; wrapMode: Text.WordWrap; color: win.sub; font.family: win.fontFam; font.pixelSize: 13
                        text: "A local-first voice assistant that lives in your notch. Hold a key and talk, or say the wake word. It dictates into any app, keeps your list, sets reminders, plays music, and shows what Claude Code is doing." }
                    Text { width: parent.width; wrapMode: Text.WordWrap; color: win.sub; font.family: win.fontFam; font.pixelSize: 12
                        text: "Built with Qt, faster-whisper, Piper, openWakeWord, llama.cpp and Qwen3. See LICENSE for third-party licences." }
                    Btn { label: "Open my data folder"; onClicked: sc.openFolder() }
                }
            }
        }

        // toast
        Rectangle {
            visible: sc.message !== ""; anchors.horizontalCenter: parent.horizontalCenter; y: parent.height - 52
            width: Math.min(parent.width - 72, toastText.implicitWidth + 40); height: 38; radius: 19; color: "#1B1B20"
            Text { id: toastText; anchors.centerIn: parent; width: parent.width - 32; elide: Text.ElideMiddle
                horizontalAlignment: Text.AlignHCenter; text: sc.message; color: "#fff"; font.family: win.fontFam; font.pixelSize: 13 }
        }
    }

    // ---------------------------------------------------------------- building blocks
    component SRow: Item {
        id: row
        property string title: ""
        property string desc: ""
        default property alias control: holder.data
        width: parent ? parent.width : 600
        height: Math.max(66, textCol.height + 26)
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: "#E4E4EA" }
        Column { id: textCol; y: 14; width: parent.width - holder.width - 40; spacing: 3
            Text { text: row.title; color: win.ink; font.family: win.fontFam; font.pixelSize: 14; font.weight: Font.DemiBold }
            Text { visible: row.desc !== ""; width: parent.width; text: row.desc; wrapMode: Text.WordWrap
                color: win.sub; font.family: win.fontFam; font.pixelSize: 12 } }
        Item { id: holder; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            width: childrenRect.width; height: childrenRect.height }
    }

    component Switch2: Item {
        id: sw
        property bool checked: false
        signal toggled(bool on)
        width: 46; height: 26
        Rectangle { anchors.fill: parent; radius: 13; color: sw.checked ? "#34C759" : "#C9C9D1"; Behavior on color { ColorAnimation { duration: 120 } }
            Rectangle { y: 2; x: sw.checked ? 22 : 2; width: 22; height: 22; radius: 11; color: "#fff"; Behavior on x { NumberAnimation { duration: 120 } } } }
        MouseArea { anchors.fill: parent; onClicked: sw.toggled(!sw.checked) }
    }

    component Seg: Row {
        id: seg
        property var options: []
        property var labels: []
        property string current: ""
        signal picked(string value)
        spacing: 4
        Repeater { model: seg.options
            delegate: Rectangle { required property int index; required property string modelData
                width: lbl.implicitWidth + 26; height: 32; radius: 16
                color: seg.current === modelData ? "#17171C" : (sm.containsMouse ? "#E0E0E8" : "#E9E9EF")
                Text { id: lbl; anchors.centerIn: parent; text: seg.labels[index] !== undefined ? seg.labels[index] : modelData
                    color: seg.current === modelData ? "#fff" : win.ink; font.family: win.fontFam; font.pixelSize: 13; font.weight: Font.Medium }
                MouseArea { id: sm; anchors.fill: parent; hoverEnabled: true; onClicked: seg.picked(modelData) } } }
    }

    component Slid: Row {
        id: sl
        property real from: 0
        property real to: 1
        property real step: 0.1
        property real value: 0
        property string suffix: ""
        property int decimals: 0
        signal moved(real v)
        spacing: 12
        Item { width: 180; height: 26; anchors.verticalCenter: parent.verticalCenter
            Rectangle { y: 10; width: parent.width; height: 6; radius: 3; color: "#D9D9E0"
                Rectangle { width: parent.width * Math.max(0, Math.min(1, (sl.value - sl.from) / (sl.to - sl.from))); height: 6; radius: 3; color: win.accent } }
            Rectangle { x: (parent.width - 18) * Math.max(0, Math.min(1, (sl.value - sl.from) / (sl.to - sl.from))); y: 4; width: 18; height: 18; radius: 9
                color: "#fff"; border.color: "#B8B8C2" }
            MouseArea { anchors.fill: parent
                function pick(mx) {
                    var f = Math.max(0, Math.min(1, mx / width)); var raw = sl.from + f * (sl.to - sl.from)
                    sl.moved(Math.round(raw / sl.step) * sl.step) }
                onPressed: (m) => pick(m.x)
                onPositionChanged: (m) => { if (pressed) pick(m.x) } } }
        Text { anchors.verticalCenter: parent.verticalCenter; width: 56; text: Number(sl.value).toFixed(sl.decimals) + sl.suffix
            color: win.ink; font.family: win.fontFam; font.pixelSize: 13; font.weight: Font.Medium }
    }

    component Btn: Rectangle {
        id: b
        property string label: ""
        property string kind: "plain"
        signal clicked()
        width: bl.implicitWidth + 30; height: 34; radius: 17
        opacity: b.enabled ? 1 : 0.4
        color: kind === "primary" ? "#17171C" : (kind === "danger" ? "#FBE4E2" : "#E9E9EF")
        scale: bm.pressed ? 0.96 : 1
        Behavior on scale { NumberAnimation { duration: 80 } }
        Text { id: bl; anchors.centerIn: parent; text: b.label; font.family: win.fontFam; font.pixelSize: 13; font.weight: Font.DemiBold
            color: b.kind === "primary" ? "#fff" : (b.kind === "danger" ? "#B3261E" : win.ink) }
        MouseArea { id: bm; anchors.fill: parent; enabled: b.enabled; onClicked: b.clicked() }
    }

    component Combo: Item {
        id: cb
        property var options: []
        property string current: ""
        signal picked(string value)
        width: 190; height: 36
        Rectangle { anchors.fill: parent; radius: 10; color: "#fff"; border.color: pop.visible ? win.accent : "#CFCFD8"
            Text { x: 12; width: parent.width - 36; anchors.verticalCenter: parent.verticalCenter; text: cb.current; elide: Text.ElideRight
                color: win.ink; font.family: win.fontFam; font.pixelSize: 13 }
            Text { anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: "▾"; color: win.sub }
            MouseArea { anchors.fill: parent; onClicked: pop.visible = !pop.visible } }
        Rectangle { id: pop; visible: false; y: 40; width: parent.width; height: Math.min(cb.options.length, 6) * 32 + 8; radius: 10; z: 99
            color: "#fff"; border.color: "#CFCFD8"
            Column { x: 4; y: 4; width: parent.width - 8
                Repeater { model: cb.options
                    delegate: Rectangle { required property string modelData; width: parent.width; height: 32; radius: 8
                        color: pm.containsMouse ? "#EEF3FA" : "transparent"
                        Text { x: 10; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 20; elide: Text.ElideRight; text: modelData
                            color: win.ink; font.family: win.fontFam; font.pixelSize: 13; font.weight: modelData === cb.current ? Font.DemiBold : Font.Normal }
                        MouseArea { id: pm; anchors.fill: parent; hoverEnabled: true; onClicked: { pop.visible = false; cb.picked(modelData) } } } } } }
    }

    Shortcut { sequence: "Escape"; onActivated: win.close() }
}
