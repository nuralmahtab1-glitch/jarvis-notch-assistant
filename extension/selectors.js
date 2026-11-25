// selectors.js - EVERYTHING that depends on claude.ai's page layout lives in this one file.
// If Claude Code on the web changes its markup and detection stops working, this is the only file to update.
// (Jarvis made by Nur Al Mahtab.)
//
// Detection is deliberately conservative: if the page does not look like Claude Code at all (no message box),
// the extension reports "unavailable" and Jarvis shows nothing, rather than guessing wrongly.
const JARVIS_SELECTORS = {
  version: 1,

  // Set true only when testing: writes the detected state into <html data-jarvis-state> so a test can read it.
  debug: false,

  // How often to re-check besides reacting to page changes (milliseconds).
  intervalMs: 800,

  // Idle checks in a row before a finished task is reported as "done" (avoids flicker between steps).
  settleChecks: 3,

  // The message box. If none of these exist, the page is not recognised -> "unavailable".
  anchors: ["textarea", "div[contenteditable='true']", "[role='textbox']"],

  // "Working": a visible control that stops generation, or a busy marker.
  working: {
    selectors: ["button[aria-label*='stop' i]", "button[data-testid*='stop' i]", "[aria-busy='true']"],
    buttonText: ["^stop$", "^stop (generating|response|task|claude)"]
  },

  // "Needs you": a visible permission prompt = an allow-type button AND a deny-type button on screen together.
  needsYou: {
    allow: ["^allow", "^approve", "^yes,? allow", "^accept"],
    deny: ["^deny", "^reject", "^no,? ?(deny|don)", "^decline"]
  },

  // The only words ever sent to Jarvis about what is happening. Never page text.
  labels: { working: "Working", needs_you: "Waiting for your OK in the browser" }
};
