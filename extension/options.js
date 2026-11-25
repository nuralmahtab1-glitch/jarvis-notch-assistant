// options.js - pairing, connection test and the page self-check. (Jarvis made by Nur Al Mahtab.)
const $ = (id) => document.getElementById(id);
const msg = (text, ok) => { const m = $("msg"); m.textContent = text; m.className = ok === undefined ? "" : ok ? "ok" : "bad"; };

chrome.storage.local.get("pairCode").then(({ pairCode }) => { $("code").value = pairCode || ""; });

$("save").onclick = async () => {
  const code = $("code").value.trim().toUpperCase();
  if (!/^[0-9A-F]{8}$/.test(code)) return msg("The code is 8 letters and numbers, like 3F9A01BC.", false);
  await chrome.storage.local.set({ pairCode: code });
  msg("Saved. Press Test connection.", true);
};

$("test").onclick = async () => {
  msg("Testing...");
  const r = await chrome.runtime.sendMessage({ type: "test" });
  if (r && r.ok) msg(`Connected to Jarvis on port ${r.port}.`, true);
  else msg({ "not paired": "Save a pairing code first.", "no jarvis": "Jarvis is not running, or the web option is off in its Settings.",
             "wrong code": "Wrong code. Copy the current one from Jarvis Settings.", unreachable: "Could not reach Jarvis." }[(r && r.error) || ""] || "Could not connect.", false);
};

$("page").onclick = async () => {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab || !/^https:\/\/claude\.ai\/code/.test(tab.url || "")) return msg("Open claude.ai/code in the active tab, then press this.", false);
  try {
    const r = await chrome.tabs.sendMessage(tab.id, { type: "selftest" });
    msg(r.recognised ? `Recognised the page (state: ${r.state}).` : "This page was not recognised: the message box was not found. selectors.js may need updating.", r.recognised);
  } catch (e) { msg("The extension is not running on that tab yet. Reload the page and try again.", false); }
};
