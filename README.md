# Jarvis

**Made by Nur Al Mahtab.**

A local-first voice assistant that lives in a "notch" at the top-centre of your Windows screen.
Hold a key and talk, or say "Hey Jarvis". It dictates into any app, keeps your list, sets reminders and
focus sessions, controls volume, plays music, talks back in a calm British voice, and shows live status
for **Claude Code** so you can approve actions from the notch. Everything runs on your PC. No account, no
telemetry, no cloud.

> "Jarvis" is a working name (one constant in `app/config.py`). It is also a trademarked character name, so
> rename it before you ever publish or sell this.

## Install it (Windows 10/11)

Run **`dist\JarvisSetup.exe`** (about 325 MB, one file). It is a normal setup wizard: Welcome, Licence, folder and
shortcut options, progress, Finish. It installs **for you only**, with **no administrator rights**, into
`%LOCALAPPDATA%\Programs\Jarvis`. Silent install for scripts:
`JarvisSetup.exe /S /D=C:\Some\Folder --no-launch` (also `--no-shortcuts`, `--desktop`, `--autostart`).

- **Uninstall:** Settings > Apps > Installed apps > Jarvis. It stops Jarvis, removes its Claude Code hooks (only its
  own), the start-with-Windows entry and the shortcuts, and asks whether to also delete your data and downloaded
  models (default: keep). It never deletes a folder that isn't a Jarvis install, and the installer refuses to
  install into a folder that already holds other files.
- **First start:** the setup tour opens. The British voice is bundled; the speech model (about 150 MB) downloads the
  first time, and the notch tells you. The optional AI brain is a separate download from the tray menu.
- **If something goes wrong:** the installed app writes `%APPDATA%\Jarvis\jarvis.log` (trimmed automatically).
- **Heads-up:** the installer is **not code-signed**, so Windows SmartScreen will say "unknown publisher" (click
  More info > Run anyway), and some antivirus tools are suspicious of any new program that listens for a hotkey and
  types text. Signing needs a paid certificate.

Build it yourself: `python packaging/build.py` (about 10 minutes; needs the project's `.venv`). It makes
`dist\Jarvis\` (the app) and `dist\JarvisSetup.exe`. Qt's unused parts (web engine, PDF, 3D, charts) are stripped out,
which took the app from 879 MB to about 630 MB.

## Run it from source

```powershell
cd jarvis
.venv\Scripts\python.exe run.py              # normal start (first run shows the setup tour)
.venv\Scripts\python.exe run.py --demo       # cycle through every notch state
.venv\Scripts\python.exe run.py --onboarding # show the setup tour again
.venv\Scripts\python.exe run.py --say "what time is it"   # pretend you said something (no mic)
```

First launch downloads nothing by itself: the speech model (`faster-whisper base.en`, ~150 MB) is fetched the
first time it is needed, and the British voice (Piper `en_GB-alan-medium`) lives in `models/piper/`.

Tray icon menu: **Settings...**, About, Download/Remove AI brain, Connect/Disconnect Claude Code, Do not disturb, Speak replies, Start with Windows,
Cycle demo states, Sleep, Quit.

## Using it

| Do this | What happens |
|---|---|
| Hold **Right Ctrl** and talk | Command mode. Release to run it. |
| Hold **Right Alt** and talk | Dictation. Cleaned text is typed into the focused app. |
| Say **"Hey Jarvis"** | Wake word (local). It stops listening when you stop talking. |
| Hover the top-centre of the screen | The notch peeks out; hover/click to expand. |
| "Remind me to call Mom at six" | Reminder card + spoken reminder. |
| "Start a focus session for 25 minutes" | Focus ring with Break/Stop. |
| "Add buy milk to my list" / "What's on my list?" | To-do card. |
| "Volume to 40", "Take a screenshot", "Open Spotify" | Does it. |
| "What's Claude doing?", "Approve", "Deny" | Claude Code status and approvals. |
| "Goodnight" | Notch falls asleep (moon and Zz). Wake it by hovering or speaking. |

A quick tap of a key (under a quarter second) is ignored, so normal Ctrl shortcuts never trigger it.

## Claude Code status (the notch shows what Claude is doing)

Use tray menu **Connect Claude Code...**. It shows exactly what will change in `~/.claude/settings.json`, backs the
file up first, keeps your own hooks, and tags its entries so **Disconnect** removes only its own.

- **Working** (live action + timer), **Needs you** (Approve / Deny), **Done** (duration + one-line summary), **Error**.
- It never auto-approves. If you do not answer within the timeout (default 30 s), or Jarvis is not running, Claude
  Code's own prompt appears as normal. If your terminal/VS Code is already in front, it stays out of the way.
- Risky actions (delete, force-push, installs, writes outside the project) are flagged and need a **tap**, never a
  voice "yes". Approve/Deny ignore clicks for 0.7 s after the card appears, so a click meant for the app beneath
  can't approve something by accident.
- Hooks call a tiny stdlib-only helper (`app/claude_bridge/hook.py`) that talks to a loopback-only, token-protected
  local server. If Jarvis is not running the helper exits silently and instantly.

## Apps (a launcher in the notch)

The grid icon opens your **pinned apps** (or say "show my apps"). The first time, it pins Explorer, Notepad,
Calculator, Settings and whichever of Chrome, Edge, VS Code, Discord, Word, Excel, PowerPoint, Spotify, Steam, OBS,
Slack and Zoom it finds in your Start menu. Each shows its real icon. Click to launch; hover to unpin (x); the **+**
tile opens a file picker; or **drop a program or shortcut** on the panel to pin it. Reset restores the defaults.
Only programs and shortcuts (`.exe .lnk .url .bat .cmd`) can be pinned.

Voice: "open photoshop", "open vs code" finds anything in your Start menu (pinned apps first). Well-known names
(notepad, calculator, terminal...) keep their exact Windows mapping, so a similarly named program can never hijack them.
Default pins use strict matching on purpose: a wrong guess (for example pinning a trading "Terminal" as Windows
Terminal) is worse than no pin.

## Shelf (clipboard history + parked files)

Hover the notch and use the tab icon, say "show my shelf", or **drag a file or text onto the notch** (it opens
by itself and the drop parks it).

- Shows your recent copies (text and files), newest first. **Click** an item to copy it back, **Paste** types it
  into the window you were just in (only if you are still in it), **x** removes it, **Clear shelf** empties it.
- Drag an item out to drop it into another app (text, or the real file).
- **Privacy:** memory only, never written to disk, gone when Jarvis closes. It ignores anything an app marked
  "do not record" (password managers do this), and anything that looks like a password or API key. Max 30 items,
  2000 characters each. Switch it off, or clear it, in Settings > Privacy.

## Controls panel (quick settings in the notch)

Hover the notch, then click the sliders icon (or say "open the controls"). It shows the real state of your PC and
refreshes every few seconds while open:

- **Real switches:** Wi-Fi and Bluetooth (through Windows' radio API), **Airplane mode** (all radios), and
  **power mode** (Efficient / Balanced / Performance).
- **Sliders:** volume (live as you drag) and brightness (applied when you let go). Click the speaker icon to mute.
- **Battery** percentage and whether you are plugged in, plus a **Screenshot** button.
- **Shortcuts, honestly labelled:** Battery saver, Night light and Accessibility open their Windows Settings page
  (marked with a small arrow), because Windows has no supported on/off switch for apps.
- Also by voice: "turn bluetooth off", "airplane mode on", "set power mode to performance". Turning Wi-Fi off (or
  Airplane on) by voice **asks first**, because it disconnects you. Tapping a tile is a deliberate action, so it
  does not ask. If Windows refuses a change, the tile snaps back and says so.

## Settings

Tray icon -> **Settings...** (or `run.py --settings`; tests: `tests/live_settings_clicks.py` clicks it with a simulated mouse). Seven pages: General (name, start with Windows, sleep time,
Do not disturb, greeting), Voice (when to speak, personality, speed + preview), Listening (wake word, command and
dictate keys, microphone, speech model), AI brain (status, model, download/remove), Claude Code (connect, approval
timeout, privacy, spoken updates), Privacy (lyrics, export, erase, reset) and About. Most changes apply
immediately; keys, microphone, speech model and the Claude bridge show a "restart" notice. Destructive buttons
(erase, reset) ask twice. Do Not Disturb holds reminders instead of losing them, and fires them when it ends.

## The AI brain (local, optional)

Tray menu **Download AI brain (1.1 GB)** (or pick it in the setup tour) installs `llama.cpp` and **Qwen3 1.7B**
into `models/`. Everything runs on your PC. Without it, everything still works through the rules parser; with it,
Jarvis also understands unusual phrasing, answers short questions, and can **write for you**
("write a short note asking Maya to move the deadline" types a draft into the focused app).

How it behaves:
- The rules parser always goes first (instant). The model only handles what the rules miss.
- The model can only pick from a fixed list of tools; its output is validated, numbers are clamped, and unknown
  tools are rejected.
- **Safety nets that do not depend on the model:** destructive wording ("delete", "wipe", "get rid of"...) never
  becomes an action; questions about your own data (list, battery, Claude, time) are answered by a real tool,
  never invented; a tool must be justified by your words (so "lower the glare" can't toggle mute).
- On this PC (i5-class CPU, 7.8 GB RAM, no usable GPU): about 10 s once at launch to warm up, then roughly 1 to
  3 s per request. The model is unloaded after 10 idle minutes to free memory.
- Measured with the real model: 21/22 on a development set and 14 to 15 of 16 on phrasings it had never seen.
  A 1.7B model is small, so expect occasional misses; it fails safe (asks you to repeat) rather than guessing.
- The model server writes `%APPDATA%\Jarvis\llama.log`. If it dies mid-request the app restarts it and retries once.

## What is built, and what is not (honest status)

**Built and tested:** the notch (shape, eyes, sleep/wake, hover tooltips, all states), hold-to-talk + wake word,
local speech-to-text, dictation clean-up (fillers, self-corrections, bullets, spoken punctuation), typing into the
focused app (fails closed if the window changes), British Piper voice with sentence streaming and barge-in,
rules-based commands, to-do list, reminders, focus timer, Claude Code bridge + approvals + hooks installer,
now-playing + synced lyrics, tray menu, 17-step onboarding.

**Not built yet:**
- A full **Models page** for cloud providers / API keys (the local brain below is built).
- Adding your own models by file or Ollama name (the Settings window lists the built-in Qwen3 models only).
- World clocks, weather and the teleprompter (their tab-icon tooltips exist, the features don't).
- Dragging an item **out of** the Shelf into another app uses Qt's native drag, which I could not exercise
  automatically (dropping *in* is tested with synthesized events). Click to copy and the Paste button are tested.
- A real on/off switch for **night light, battery saver and accessibility**: Windows gives apps no supported way to
  do that, so those tiles open the matching Windows Settings page instead.
- **Browser extension** for claude.ai/code. Code-signing the installer, and automatic updates.
- Memory use: the running app takes about 600 MB with the speech model and wake word loaded (Qt itself is a few
  hundred), which is above the original 150 MB target.
- Not yet tested by a human with a real microphone and speakers: wake-word accuracy in a noisy room, dictation
  into every app, voice quality and loudness. Automated tests cover the logic, not your ears.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest tests -q     # 230 tests
```

Live checks (need a real screen/speakers): `tests/live_winio_check.py`, `tests/live_voice_roundtrip.py`,
`tests/live_e2e.py`.

## Privacy

Audio stays in memory and is dropped as soon as it is transcribed. Speech recognition, the wake word, the voice and
all commands run locally. The only network use is optional: synced lyrics ask `lrclib.net` for the song title,
artist and length (turn off with `"lyrics": false`), and the first-run model download.

## Layout

```
app/ui/            notch + onboarding (QML) and their controllers
app/core/          assistant brain, persona
app/tools/         command parser, dictation clean-up
app/audio, stt, wake, tts/   microphone, Whisper, "Hey Jarvis", Piper
app/winio/         typing, volume, screenshots, hotkeys, media, autostart
app/claude_bridge/ hook helper, session tracker, loopback server, settings installer
app/store/         SQLite + settings
tests/             pytest suite and live checks
```

---
Made by Nur Al Mahtab.
