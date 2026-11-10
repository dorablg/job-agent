const pw = document.getElementById("pw"), msg = document.getElementById("msg");
chrome.storage.local.get("password").then(({ password }) => { if (password) pw.value = password; });
document.getElementById("save").onclick = async () => {
  await chrome.storage.local.set({ password: pw.value.trim() });
  msg.textContent = "Testing…";
  chrome.runtime.sendMessage({ type: "reload" }, r => {
    msg.textContent = r && r.ok ? `✅ Connected: ${r.n} opportunities and your profile loaded. You're ready.` : "⚠️ " + ((r && r.error) || "Could not connect");
  });
};
