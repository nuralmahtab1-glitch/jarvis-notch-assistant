# Jarvis: how to use it

Made by Nur Al Mahtab. Jarvis is a voice assistant that lives in a small pill at the top of your screen (the "notch").

## Open it, close it, reopen it

- **Installed to:** `%LOCALAPPDATA%\Programs\Jarvis` (type that into File Explorer's address bar).
- **Reopen if you closed it:** Start menu -> type "Jarvis", or double-click `Jarvis.exe` in that folder.
- **Close it:** right-click the tray icon (bottom-right, may be under the ^ arrow) -> **Quit**.
- **Start with Windows:** tray menu -> *Start with Windows*.
- **Install again / update:** run `dist\JarvisSetup.exe` (it replaces the old version and keeps your data).
- **Uninstall:** Windows Settings -> Apps -> Jarvis -> Uninstall. Your data is kept unless you choose otherwise.
- **If something is wrong,** read the log: `%APPDATA%\Jarvis\jarvis.log`.

## Talking to it

| Do this | What happens |
|---|---|
| Say **"Hey Jarvis"**, then your request | Wake word (needs a microphone) |
| Hold **Right Ctrl** and speak | Push-to-talk command |
| Hold **Right Alt** and speak | Dictation: types what you say wherever your cursor is |
| Hover or click the notch | Opens the panels (tab icons along the bottom) |

## Things to say

- "What time is it?" / "What's the weather in London?" / "What time is it in Tokyo?"
- "Set a timer for 10 minutes." / "Remind me to call mum at 6." / "Add milk to my to-do list."
- "Open Spotify." / "Volume 40." / "Turn Wi-Fi off." / "Take a screenshot."
- "Don't let my laptop sleep." / "Let it sleep again."
- "Open YouTube and Chrome side by side." / "Open Notepad and Calculator." / "Snap this window to the left."
- "Open YouTube and after that search for avengers." / "Search YouTube for lofi beats." / "Find a laptop on Amazon."
- "Start the teleprompter." (copy your script first) / "Show the menu."
- "What's Claude doing?" (needs Claude Code connected, see below)
- Questions and writing ("write a short email saying I'll be late") need the AI brain, see below.

## First-time setup

1. **AI brain (optional, makes it answer questions and write):** Settings -> AI brain -> **Download**. It's about 1 GB, runs only on your PC, and everything else works without it.
2. **A smarter cloud brain (optional):** Settings -> AI brain -> Brain source -> ChatGPT / Gemini / Claude. Paste an API key (billed by that company, separate from a chat subscription) and press Test. Your questions are then sent to them.
3. **Your own model:** Settings -> AI brain -> *Add your own model*: paste the path of a `.gguf` file and press Import.
4. **Weather city, clocks, favourite sites:** Settings -> General.

## Moving and hiding Jarvis

- **It hides by itself:** after a few seconds of nothing, Jarvis slides up out of sight. Push the mouse to the **very top edge** of the screen (middle) to bring it back. It also returns on its own for "Hey Jarvis", reminders and approvals. Turn this off or change the delay in Settings -> General -> *Hide when idle*.
- **Move it:** point at Jarvis so it opens, then **drag any empty part** of it left or right. It remembers the spot. Buttons and sliders still click normally.
- **Put it back in the middle:** Settings -> General -> *Put back in the middle*, or the tray menu.

## Panels (tab icons)

Timer/focus, Widgets (clocks, weather, to-do), Shelf (drop files and text to keep them handy), Controls (volume, brightness, Wi-Fi, Bluetooth, Keep awake, Quiet mode, Screenshot), Apps (pinned programs), Menu (favourite sites, teleprompter, music, Settings).

## Claude Code

- **Terminal / VS Code:** tray menu -> **Connect Claude Code**. Jarvis then shows what Claude is doing and lets you Approve or Deny actions from the notch. It never approves anything by itself. **Disconnect** removes only its own hooks.
- **Claude Code on the web (claude.ai/code):**
  1. Chrome or Edge -> Extensions -> turn on *Developer mode* -> *Load unpacked* -> choose the `extension` folder
     (`%LOCALAPPDATA%\Programs\Jarvis\_internal\extension`).
  2. Jarvis Settings -> Claude Code -> switch on **Claude Code on the web** and copy the **pairing code**.
  3. Extension options -> paste the code -> **Save** -> **Test connection**.
  4. Open claude.ai/code and press **Check this page** in the options. Approving still happens in the browser.
  - Only a state and a short label are sent, only to this PC. If claude.ai changes its layout, edit `extension\selectors.js`.

## Keep the laptop awake

Say "don't let my laptop sleep", use the **Keep awake** tile in Controls, or tray menu -> *Keep awake*. It can also stay awake while Claude is working (Settings -> General).
To stop a stuck keep-awake: run `Jarvis.exe --awake-stop` (or `python run.py --awake-stop` in the project folder).

## Privacy

Everything runs on your PC. The only internet use: weather and lyrics lookups (city name or song title only), the one-time brain download, and nothing else. The teleprompter is hidden from screen sharing and recordings while it's showing.

## Known limits

- The installer is unsigned: Windows SmartScreen may warn ("More info" -> "Run anyway").
- Mic, wake word and voice depend on your hardware; not every setup has been tested.
- Memory use is roughly 200-600 MB.
- Not built: Ollama pulls, cloud model providers, a teleprompter that follows your voice.
