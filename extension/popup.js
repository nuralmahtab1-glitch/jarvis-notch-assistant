const s = document.getElementById("s");
chrome.storage.local.get("status").then(({ status }) => {
  if (!status) { s.textContent = "Not connected yet."; s.className = "bad"; return; }
  s.textContent = status.text; s.className = status.ok ? "ok" : "bad";
});
document.getElementById("opt").onclick = () => chrome.runtime.openOptionsPage();
