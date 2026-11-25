// content.js - runs on claude.ai/code. Reads the PAGE STATE (is it working / waiting for you / finished) and tells
// Jarvis. It never reads or sends message text, code, file names or the page title. (Jarvis made by Nur Al Mahtab.)
(function () {
  if (window.__jarvisLoaded) return;
  window.__jarvisLoaded = true;
  const S = JARVIS_SELECTORS;
  const rx = (list) => list.map((p) => new RegExp(p, "i"));
  const allowRx = rx(S.needsYou.allow), denyRx = rx(S.needsYou.deny), stopTextRx = rx(S.working.buttonText);

  function visible(el) {
    if (!el || !el.isConnected) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== "hidden" && cs.display !== "none" && cs.opacity !== "0";
  }
  const anyVisible = (sels) => sels.some((s) => { try { return [...document.querySelectorAll(s)].some(visible); } catch (e) { return false; } });
  const buttonLabels = () => [...document.querySelectorAll("button, [role='button']")].filter(visible)
    .map((b) => (b.innerText || b.getAttribute("aria-label") || "").trim());

  // returns one of: "unavailable" | "needs_you" | "working" | "idle"
  function detect() {
    if (!anyVisible(S.anchors)) return "unavailable";                       // does not look like Claude Code
    const labels = buttonLabels();
    if (labels.some((t) => allowRx.some((r) => r.test(t))) && labels.some((t) => denyRx.some((r) => r.test(t)))) return "needs_you";
    if (anyVisible(S.working.selectors) || labels.some((t) => stopTextRx.some((r) => r.test(t)))) return "working";
    return "idle";
  }

  let shown = "idle", pending = "idle", idleRun = 0, lastSent = "", lastSentAt = 0, wasBusy = false;

  function send(state) {
    const now = Date.now();
    if (state === lastSent && now - lastSentAt < 15000) return;             // changes now, otherwise a heartbeat every 15 s
    lastSent = state; lastSentAt = now;
    try {
      chrome.runtime.sendMessage({ type: "state", state, action: S.labels[state] || "" }, () => void chrome.runtime.lastError);
    } catch (e) { /* the extension was reloaded: nothing to do */ }
  }

  function tick() {
    const raw = detect();
    if (raw === "idle") {
      idleRun++;
      if (wasBusy && idleRun >= S.settleChecks) { wasBusy = false; send("done"); shown = "done"; }   // working -> finished
      else if (!wasBusy && idleRun >= S.settleChecks) { shown = "idle"; send("idle"); }
    } else {
      idleRun = 0; shown = raw;
      if (raw === "working" || raw === "needs_you") wasBusy = true;
      send(raw);
    }
    if (S.debug) document.documentElement.setAttribute("data-jarvis-state", shown);
  }

  let timer = null;
  const schedule = () => { if (!timer) timer = setTimeout(() => { timer = null; tick(); }, 300); };
  new MutationObserver(schedule).observe(document.documentElement, { subtree: true, childList: true, attributes: true });
  setInterval(tick, S.intervalMs);
  tick();
  window.addEventListener("pagehide", () => { try { chrome.runtime.sendMessage({ type: "state", state: "idle", action: "" }); } catch (e) {} });

  // Options page "Check this page": which anchors matched, with no page content in the answer.
  chrome.runtime.onMessage.addListener((msg, _s, reply) => {
    if (msg && msg.type === "selftest") {
      reply({ recognised: anyVisible(S.anchors), working: anyVisible(S.working.selectors), state: detect(), selectorsVersion: S.version });
    }
  });
})();
