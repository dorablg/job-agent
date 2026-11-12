/* Settings: the password is sent once to the background, which derives a non-extractable key and forgets the password. */
const pw = document.getElementById("pw"), msg = document.getElementById("msg");
chrome.runtime.sendMessage({ type: "reload" }, r => {
  if (r && r.ok) { msg.textContent = `✅ Connected: ${r.n} opportunities loaded.`; pw.placeholder = "Connected (enter again only to change it)"; }
});
document.getElementById("save").onclick = () => {
  const value = pw.value.trim();
  if (!value) { msg.textContent = "Enter your dashboard password."; return; }
  msg.textContent = "Testing…";
  chrome.runtime.sendMessage({ type: "setPassword", password: value }, r => {
    pw.value = "";
    const why = (r && r.error) || (chrome.runtime.lastError && chrome.runtime.lastError.message) || "Could not connect";
    msg.textContent = r && r.ok ? `✅ Connected: ${r.n} opportunities and your profile loaded. You're ready.` : "⚠️ " + why;
  });
};
