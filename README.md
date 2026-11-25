# Jarvis

**Made by Nur Al Mahtab.**

A local-first voice assistant that lives in a "notch" at the top-centre of your Windows screen.
Hold a key and talk, or say "Hey Jarvis". It dictates into any app, keeps your list, sets reminders and
focus sessions, controls volume, plays music, talks back in a calm British voice, and shows live status
for **Claude Code** so you can approve actions from the notch. Everything runs on your PC. No account, no
telemetry, no cloud.

> "Jarvis" is a working name (one constant in `app/config.py`). It is also a trademarked character name, so
> rename it before you ever publish or sell this.

## Run it

```powershell
cd jarvis
.venv\Scripts\python.exe run.py              # normal start (first run shows the setup tour)
.venv\Scripts\python.exe run.py --demo       # cycle through every notch state
.venv\Scripts\python.exe run.py --onboarding # show the setup tour again
.venv\Scripts\python.exe run.py --say "what time is it"   # pretend you said something (no mic)
```

First launch downloads nothing by itself: the speech model (`faster-whisper base.en`, ~150 MB) is fetched the
first time it is needed, and the British voice (Piper `en_GB-alan-medium`) lives in `models/piper/`.

Tray icon menu: About, Connect/Disconnect Claude Code, Do not disturb, Speak replies, Start with Windows,
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
- **Models page** (add local/cloud models, API keys), **Settings window** (settings live in
  `%APPDATA%\Jarvis\settings.json`).
- **Controls / Shelf / Apps** panels, world clocks, weather, teleprompter. Their tab icons show tooltips only.
- Wi-Fi / Bluetooth / night-light toggles (the assistant says it can't yet).
- **Browser extension** for claude.ai/code, and a Windows **installer**.
- Not yet tested by a human with a real microphone and speakers: wake-word accuracy in a noisy room, dictation
  into every app, voice quality and loudness. Automated tests cover the logic, not your ears.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest tests -q     # 107 tests
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
