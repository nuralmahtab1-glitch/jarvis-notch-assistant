# PLAN.md — Jarvis (notch voice assistant for Windows)

**Made by Nur Al Mahtab.**
Status: DRAFT for approval. No code has been written.

---

## 0. Decisions I need from you (short list at the bottom, section 14)

Everything else below is a default I picked. Change anything you like.

## 1. What I found on this PC (verified today)

| Item | Result | Consequence |
|---|---|---|
| OS | Windows 11 (10.0.26200) | Target confirmed. |
| RAM | 7.8 GB | Tight. Models must be small, loaded lazily, unloaded when idle. |
| GPU | Intel UHD + NVIDIA MX250 (2 GB) | MX250 is weak. Default to CPU. Vulkan offload only for small models, and only if a benchmark says it helps. |
| Python | 3.12.10 | Ready. |
| git, ffmpeg | Present | Ready. |
| **Node, npm, pnpm** | **Not installed** | Needed for Electron or any React UI. |
| **Rust, cargo, MSVC Build Tools** | **Not installed** | Needed for Tauri. Multi-GB install. |
| Ollama, Piper | Not installed | I will not depend on Ollama (see 3.4). |
| WebView2 runtime | Present | Fine for Tauri if chosen later. |
| `~/.claude/settings.json` | Exists | The hook installer must merge, not overwrite. Backup first. |

## 2. Stack decision (departs from your suggestion; here is why)

You suggested Tauri + React. I recommend **Python 3.12 + PySide6 (Qt 6) with QML for the UI** instead.

**Why:**
1. **No toolchain to install.** Tauri needs Rust plus Visual Studio Build Tools (several GB). Electron needs Node. Python is already here.
2. **Every AI component is Python-native**: faster-whisper, openWakeWord, Piper, Kokoro-ONNX, llama.cpp bindings. No sidecar glue between languages.
3. **Qt is excellent at exactly this window type**: frameless, translucent, always-on-top, per-pixel shapes (the inverted notch corners), and GPU-accelerated 60 fps animation in QML.
4. **Lowest idle RAM** of the three options on a 7.8 GB machine. Electron's shell alone often exceeds your 150 MB budget.
5. A packaged Qt/Python Windows app is a proven approach (the reference app you gave me is built this way).

**Costs, stated honestly:**
- Installer is large (~150 MB before models) and cold start is slower than Tauri.
- Windows APIs go through `ctypes`/`pywin32`/`pycaw`, not the Rust `windows` crate. Fine, but more careful code.
- If you strongly prefer Tauri, I will do it. It adds one setup milestone (install Rust + Build Tools) and a sidecar Python process for AI.

| | PySide6/QML (recommended) | Tauri 2 | Electron |
|---|---|---|---|
| Install burden here | none | Rust + MSVC (~6 GB) | Node (~100 MB) |
| Idle RAM | ~80–120 MB | ~60–100 MB | 150–250 MB |
| AI libs | native | sidecar needed | sidecar needed |
| Notch shape/animation | excellent | good | good |

## 3. Architecture

One main process (UI + orchestration) plus isolated workers, so a crash in one model never kills the notch.

```
jarvis/
  app/
    main.py                  # entry, single-instance lock, tray, startup
    config.py                # APP_NAME, WAKE_PHRASE, AUTHOR (one place to rename)
    ui/                      # QML + thin Python view-models
      qml/Notch.qml, Panel.qml, Eyes.qml, states/*.qml, onboarding/*.qml
      theme/tokens.qml       # design tokens (section 5)
    core/
      state_machine.py       # single source of truth for notch state
      event_bus.py           # typed pub/sub between modules
    audio/                   # mic capture, VAD, level meter, ducking, playback queue
    stt/                     # faster-whisper worker (+ cloud provider interface)
    wake/                    # openWakeWord worker
    tts/                     # Piper / Kokoro / SAPI behind speak(text, opts)
    llm/                     # provider interface, llama.cpp server manager, cloud providers
    tools/                   # typed tool registry (reminders, todo, focus, media, toggles...)
    winio/                   # SendInput typing, global keys, volume, brightness, SMTC, tray, foreground window
    store/                   # SQLite + Credential Manager wrapper
    claude_bridge/           # local HTTP+WS server, session tracker, approvals, transcript fallback
  extension/                 # MV3 browser extension for claude.ai/code
  installer/                 # NSIS script, version-info resource (author credit)
  tests/
  PLAN.md  README.md  LICENSE
```

### 3.1 State machine
One enum drives the whole notch: `SLEEPING, IDLE, PEEK, EXPANDED, LISTENING, HEARING, WORKING, CONFIRM, DONE, SPEAKING, RECORDING, TOAST(volume|water|reminder|charging), MUSIC, FOCUS, CLAUDE_WORKING, CLAUDE_NEEDS_YOU, CLAUDE_DONE, CLAUDE_ERROR`. States have priorities (Needs-you > Confirm > Listening > Speaking > Working > Toast > Music > Idle) and a stack so a toast can interrupt Music and then return to it.

### 3.2 Process layout
- **UI/main process**: Qt event loop, state machine, tools, store, bridge server (asyncio in a thread).
- **Audio worker**: capture + VAD + wake word (always on, tiny).
- **STT worker**: loaded on demand, unloaded after idle.
- **LLM server**: `llama-server` (llama.cpp release) started and stopped by the app. Same pattern the reference app uses. No Ollama requirement, but an Ollama provider is supported.
- **TTS worker**: Piper (default), Kokoro optional, SAPI fallback for first reply.

### 3.3 Models (default picks for 7.8 GB RAM, MX250)
| Slot | Default | Optional |
|---|---|---|
| Ears (STT) | faster-whisper `base.en` int8, CPU (~150 MB) | `tiny.en` (faster), `small.en` (slow here), Parakeet via onnx-asr |
| Wake | openWakeWord with the pretrained **`hey_jarvis`** model | custom phrase later |
| Brain (LLM) | Qwen3 ~1.7B Q4_K_M (~1.1 GB) | ~4B Q4 (slow here), 9B hidden as "too large" on this PC |
| Voice (TTS) | Piper `en_GB-alan-medium` | `northern_english_male`, Kokoro `bm_george`/`bm_lewis`, SAPI |

Note: a ready-made "hey jarvis" wake model exists, so no wake-word training is needed. The app is also designed so the phrase can be renamed.

### 3.4 Tool calling and the rules fallback
LLM gets a JSON-schema tool list and returns one call. If the model is missing, too slow, or returns invalid JSON, a **rules-based intent parser** handles the core commands (reminders, to-do, focus, volume, screenshot, open app, sleep, Claude status). This is why "Not now" on model download still leaves a working assistant. Tools that affect things outside the PC (send, delete) always go through Confirm.

## 4. Claude Code live status (verified against current docs, 2026-11-25)

I read the official hooks reference (code.claude.com/docs/en/hooks). Key facts that shape the design:

- **34 hook events exist today**, far more than the spec's minimum. I will subscribe to: `SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, PostToolUseFailure, PermissionRequest, Notification, Stop, StopFailure, SubagentStart, SubagentStop, PreCompact, SessionEnd`.
- **`Stop` provides `last_assistant_message` directly.** The Done summary line needs no transcript parsing. Transcript reading becomes fallback-only.
- **There is a dedicated `PermissionRequest` event** (fires when Claude is about to ask). Decision shape:
  `{"hookSpecificOutput":{"hookEventName":"PermissionRequest","decision":{"behavior":"allow"|"deny"}}}`.
  Exiting 0 with no decision falls through to Claude Code's normal prompt. That is exactly the "never auto-approve, hand back on timeout" behavior the spec wants.
- **`Notification` has `notification_type`** (e.g. `permission_prompt`, `idle_prompt`), which maps to the amber "Needs you" state.
- **Handler type `http` exists.** Claude Code can POST hook JSON straight to `http://127.0.0.1:<port>/...`. That removes the helper-process latency risk almost entirely. Command helper stays as a fallback.
- **Registration:** `~/.claude/settings.json` → `hooks → <Event> → [{matcher, hooks:[{type, ...}]}]`. Matcher supports `*`, exact lists, and regex. Timeouts default to 600 s (command/http), `SessionEnd` has a 1.5 s budget.
- **Windows:** tool paths arrive with backslashes. Command hooks can use `"shell": "powershell"`.
- Common stdin fields: `session_id, transcript_path, cwd, permission_mode, hook_event_name`. Tool events add `tool_name, tool_input, tool_use_id`.

**Still unverified (I will read these directly in milestone 8 before writing the installer):**
1. Whether the `http` handler supports custom auth headers or env-var interpolation (needed for the shared token). If not, the token goes in the URL path and the server binds to 127.0.0.1 only, or I use the command helper for decision events.
2. The exact response contract for `http` handlers.
3. The format of `permission_suggestions`.

**Design consequences**
- Install: show a diff, back up `settings.json`, merge, tag each entry with a `"_jarvis": true`-style marker (or recognisable URL) so Disconnect removes only ours.
- Fire-and-forget events (`PostToolUse`, `SessionEnd`, etc.): async or http with a tiny timeout, never blocking.
- **Approval flow:** `PermissionRequest` hook → bridge → notch shows Approve/Deny + voice asks. Timeout 30 s then return no decision. **If the terminal/VS Code window is already in the foreground, return no decision immediately** so I never delay a prompt you are already looking at. If Jarvis isn't running, the hook fails silently and Claude Code behaves normally.
- Risky classifier (rm/del, force-push, writes outside project, package installs, network): red, tap-only, voice "yes" disabled.
- Sessions list keyed by `session_id`, with `cwd` folder name, state, elapsed, last action. Click focuses the window by matching process/title.
- Web (claude.ai/code): MV3 extension, selectors in one JSON file, "Web status unavailable" when detection fails, self-test button. It sends state and a short action label only, never conversation content.

## 5. Visual design ("make it look nice")

Quiet, tiny, polished. My own design, no copied assets.

**Tokens (single file, used everywhere)**
- Notch/pill: pure `#000000`. Panel: `#0B0B0E` with 1 px inner highlight `rgba(255,255,255,0.07)` and a soft outer shadow `0 18px 50px rgba(0,0,0,0.55)`.
- Text: primary `#F5F5F7`, secondary `#9A9AA3`, tertiary `#5E5E66`.
- Accent (Jarvis): **arc cyan `#5CE1FF`**, used sparingly: listening ring, focus of selection, links.
- State colors: Working `#5CE1FF`, Needs-you `#FFB340`, Done `#34D399`, Error `#FF5C5C`, Recording `#FF3B30`, Sleep moon `#FFD84D`.
- Type: **Inter** (bundled, variable). Title 15/600, subtitle 12/400, numerals tabular for timers.
- Radii: pill 18, panel 28, chips 14, buttons full-round. Spacing scale 4/8/12/16/24.
- Motion: expand spring (stiffness ~260, damping ~22, ≈250 ms), state cross-fades 160 ms, eyes blink every 3–7 s random, breathing 4 s sine ±1.5 %. All animations pause when full-screen app is active.

**Notch details**
- Inverted top-corner curves drawn as a QML shape so the pill melts into the bezel.
- Eyes: white vertical ovals; expressions as parametric shapes (blink, glance, alert "!", happy arcs, sleepy lines), not sprites, so they stay crisp at any DPI.
- Sleep: curved closed eyes, crescent moon with star dot, two drifting "z", ~4 fps, slightly dimmed.
- Listening: eyes + thin cyan ring that pulses with mic level. Speaking: waveform from the real output level.
- Music: panel gradient tinted from album-art dominant color, synced lyrics with current line highlighted.
- Onboarding: light rounded card, big bold title, dark pill **Continue**, live notch demo above (real components).

**Author credit — "Made by Nur Al Mahtab" appears in:**
1. Final onboarding screen footer ("Made by Nur Al Mahtab").
2. Tray menu → About Jarvis, and Settings → About (version, author, licenses).
3. Windows exe/installer version-info (Company/Author fields), installer welcome page, README and LICENSE headers.
4. A small subtle line on the first-ever wake greeting screen only. Never on the notch during normal use, so it stays out of the way.

## 6. Voice and persona
- Persona "Butler" (British, calm, dry wit, rare jokes, addresses you by the name you give, default your name). Presets: Butler, Friendly, Neutral, Minimal. **Original persona; no actor voice cloning, no film character branding.** Name "Jarvis" is a personal-project working name (see risk R9).
- Speak when the interaction started by voice; short replies; first sentence streamed; barge-in; wake detector paused/ducked during TTS; music ducking; SAPI fallback until Piper is warm.

## 7. Dictation
- Hold **Right Ctrl** (low-level keyboard hook via `WH_KEYBOARD_LL`, since `RegisterHotKey` cannot bind a bare modifier). Tour text also suggested a second key for Dictate vs Command; I will make Right Ctrl = Command and Right Alt = Dictate configurable.
- Clean-up pipeline: rules first (fillers, self-correction markers like "actually/no I mean/scratch that", bullets, punctuation), optional LLM polish with strict protection of numbers/URLs/emails, fall back to rules result on any failure.
- Insert via `SendInput` unicode typing; clipboard-paste fallback; fail closed if the target window changed. Known limit: **cannot type into elevated (admin) windows** (UIPI).
- Audio kept in memory only and discarded right after transcription. Cloud STT off by default.

## 8. Models page / providers
`ModelProvider` interface with three slots (Brain, Ears, Voice). Local: recommended list with hardware verdicts (Runs well / Slow / Too large), download with pause/resume, import `.gguf`/Whisper/Piper files, Ollama pull by name. Cloud (own key, off by default, "cloud" badge on notch when active): Anthropic, OpenAI, Gemini, OpenRouter, custom OpenAI-compatible. Keys in Windows Credential Manager. Test connection, routing (fast model for simple, big/cloud for hard), automatic local fallback, usage view, JSON provider files.

## 9. Milestones (your order, plus a setup step)

| # | Milestone | Done when |
|---|---|---|
| 0 | Project setup | venv, deps pinned, Inter font, `config.py`, hello-window runs |
| 1 | Notch shell | Pill at top-center, eyes blink/glance, sleep/wake (moon + Zz), spring expand/collapse, hover title swaps, click-through outside pill, tray icon |
| 2 | All UI states on mock data | Every state in section 2 of your spec renders, incl. 4 Claude states |
| 3 | Push-to-talk + local STT | Live transcript in the notch |
| 4 | Dictation | Fillers struck through, self-corrections, bullets, typed into Notepad/browser |
| 4b | Voice output | Piper Butler voice, sentence streaming, barge-in, ducking, Speaking state, A/B test of voices on this PC |
| 5 | Tools + LLM | Reminders, to-do, focus, volume, brightness, screenshot, open app, toggles; rules fallback |
| 6 | Wake word + sleep/DND | "Hey Jarvis" wakes it; Goodnight sleeps it |
| 7 | Music/lyrics, Shelf, Widgets, Controls, Menu, teleprompter, Apps, Timer | All panel pages |
| 8 | Claude Code bridge | Hooks installer w/ diff+backup+Disconnect, states, approvals, sessions list, voice, transcript fallback |
| 8b | Browser extension | claude.ai/code status working or cleanly "unavailable" |
| 9 | Onboarding + Settings + Models | All 17 steps with live demos, credit footer |
| 10 | Polish | Perf, multi-monitor, DPI 100–200 %, full-screen hiding, NSIS installer, README |

Each milestone: run it, verify against the section 12 checklist items that belong to it, commit.

## 10. Testing approach
- Unit tests for intent parser, dictation cleanup, state-machine priorities, hook-settings merge (backup/merge/disconnect round-trip), approval-timeout behavior.
- Fixture-driven bridge tests with recorded hook JSON for each event.
- Manual live checklist per milestone (you test on the real machine; I cannot hear audio or see your screen live, so I will ask you to confirm voice quality and animation feel).
- Perf budget checks: idle CPU < 1 %, RAM < ~150 MB excluding models (measured with psutil in a test script).

## 11. Privacy and security
Local-first, no telemetry, no accounts. Bridge binds to `127.0.0.1`, random port, shared token, rejects anything else. Cloud off until you add a key. Keys only in Credential Manager. Privacy setting hides commands/paths in Claude status. Never auto-approve anything.

## 12. Risks and mitigations

| ID | Risk | Mitigation |
|---|---|---|
| R1 | Click-through only outside the pill, with a transparent window | Use window mask/hit-test region updated per state; test early in milestone 1 |
| R2 | Staying above full-screen apps vs hiding in them | Detect full-screen and hide/dim by setting; default hide |
| R3 | 7.8 GB RAM with STT + LLM + TTS loaded | Lazy load, unload on idle, small defaults, measure |
| R4 | MX250 Vulkan may be slower than CPU | Benchmark at first run and choose; default CPU |
| R5 | Wake word self-triggering from TTS | Pause detector during speech, echo handling, tests with speakers on |
| R6 | Hook latency or blocking Claude Code | http handlers + short timeouts + async where decisions are not needed; foreground-terminal bypass for approvals |
| R7 | Typing into elevated windows fails (UIPI) | Detect and tell the user; clipboard fallback |
| R8 | claude.ai/code DOM changes | Selectors in one JSON, honest "unavailable" state, self-test |
| R9 | **"Jarvis" is a Marvel/Disney trademarked character name** | Fine for personal use. If you ever publish or sell, rename (one constant in `config.py`). Persona is an original British-butler style |
| R10 | Antivirus flags for keyboard hook and `SendInput` | Expected for dictation tools; document it; sign the installer later if distributing |
| R11 | SessionEnd hook has only a 1.5 s budget | Use fire-and-forget |
| R12 | Echo of mic indicator privacy expectations | Wake word is always-listening; show tray state, easy mute, state clearly in onboarding |

## 13. Things I deliberately did not copy
Your reference app's name, mascot look, logo, and exact copy. Titles/subtitles in your spec are kept as behavior descriptions with Jarvis wording.

## 14. Open questions for you (answer, or say "use defaults")
1. **Stack:** OK with PySide6/QML instead of Tauri? (Default: yes.)
2. **Name:** "Jarvis" for the app and wake phrase "Hey Jarvis"? (Default: yes; one-constant rename.)
3. **Address:** What should it call you? (Default: "Nur".)
4. **Project folder:** `C:\Users\nural\Desktop\ai assistant\jarvis\` (this folder, next to your reference folders). OK?
5. **Credit text:** exactly "Made by Nur Al Mahtab" everywhere listed in section 5. OK?
6. **Model downloads:** OK to download ~1.5 GB (whisper + Qwen + Piper voice) when we reach milestones 3–5?

---
*Made by Nur Al Mahtab.*
