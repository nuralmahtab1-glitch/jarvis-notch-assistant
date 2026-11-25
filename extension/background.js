// background.js - the service worker. Forwards states from the page to Jarvis on this PC (127.0.0.1 only), using the
// pairing code you pasted in the options page. (Jarvis made by Nur Al Mahtab.)
const PORTS = [17894, 17895, 17896, 17897, 17898, 17899];
let cachedPort = null;

async function getCode() {
  const { pairCode } = await chrome.storage.local.get("pairCode");
  return (pairCode || "").trim().toUpperCase();
}

function setStatus(ok, text) {
  chrome.storage.local.set({ status: { ok, text, at: Date.now() } });
  chrome.action.setBadgeText({ text: ok ? "" : "!" });
  chrome.action.setBadgeBackgroundColor({ color: ok ? "#34C759" : "#FF3B30" });
}

async function isJarvis(port) {
  try {
    const r = await fetch(`http://127.0.0.1:${port}/web/hello`, { signal: AbortSignal.timeout(700) });
    return r.ok && (await r.json()).app === "Jarvis";
  } catch (e) { return false; }
}

async function findPort() {
  if (cachedPort && (await isJarvis(cachedPort))) return cachedPort;
  for (const p of PORTS) if (await isJarvis(p)) { cachedPort = p; return p; }
  cachedPort = null;
  return null;
}

async function post(path, body) {
  const code = await getCode();
  if (!code) { setStatus(false, "Not paired yet. Open the extension options and paste the code from Jarvis."); return { ok: false, error: "not paired" }; }
  const port = await findPort();
  if (!port) { setStatus(false, "Jarvis is not running, or Claude Code on the web is switched off in its Settings."); return { ok: false, error: "no jarvis" }; }
  try {
    const r = await fetch(`http://127.0.0.1:${port}${path}`, {
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json", "X-Jarvis-Pair": code },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(2500)
    });
    if (r.status === 401) { setStatus(false, "Wrong pairing code. Copy the current one from Jarvis Settings."); return { ok: false, error: "wrong code", port }; }
    if (r.status === 429) return { ok: true, port };                         // slow down: not an error worth showing
    setStatus(r.ok, r.ok ? `Connected to Jarvis on port ${port}.` : `Jarvis answered ${r.status}.`);
    return { ok: r.ok, port, status: r.status };
  } catch (e) {
    cachedPort = null;
    setStatus(false, "Could not reach Jarvis.");
    return { ok: false, error: "unreachable" };
  }
}

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg && msg.type === "state") {
    // only a state, a fixed label and the tab number leave the browser: never page text or the title
    post("/web/event", { state: msg.state, action: String(msg.action || "").slice(0, 60), tab: String(sender.tab ? sender.tab.id : 0) }).then(reply);
    return true;
  }
  if (msg && msg.type === "test") { post("/web/ping", null).then(reply); return true; }
  return false;
});

chrome.tabs.onRemoved.addListener((tabId) => { post("/web/event", { state: "idle", action: "", tab: String(tabId) }); });
