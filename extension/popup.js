const msg = document.getElementById("msg"), go = document.getElementById("go");
document.getElementById("settings").onclick = e => { e.preventDefault(); chrome.runtime.openOptionsPage(); };
go.onclick = async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  go.disabled = true; go.textContent = "⏳ Reading the form and writing answers… (≈20 s)"; msg.textContent = "";
  chrome.runtime.sendMessage({ type: "fill", tabId: tab.id }, r => {
    go.disabled = false; go.textContent = "✨ Fill this application";
    if (!r) { msg.textContent = "Something went wrong. Reload the page and try again."; return; }
    if (!r.ok) { msg.textContent = "⚠️ " + r.error; return; }
    msg.textContent = `✅ ${r.filled} answers filled, ${r.attached} file(s) attached.\n` +
      `Job: ${r.job}\nCV written as: ${r.student ? "student (engineering degree shown)" : "graduate (studies not mentioned)"}\n` +
      (r.left ? `⚠️ ${r.left} item(s) need you — see the panel on the page.\n` : "") + "Now check everything and click Submit yourself.";
  });
};
