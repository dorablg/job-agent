/* Runs on your dashboard only: lets the page ask the extension to open applications, fill them, and run agent batches.
   Accepts messages from this exact page (same window, same origin) and only http(s) links. */
document.documentElement.dataset.flousExt = "2";   // 2 = supports agent batches
const web = u => typeof u === "string" && /^https?:\/\//i.test(u);
window.addEventListener("message", e => {
  if (e.source !== window || e.origin !== location.origin) return;
  const d = e.data;
  if (!d) return;
  if (d.flous === "apply" && web(d.url)) {
    chrome.runtime.sendMessage({ type: "autoApply", url: d.url, title: String(d.title || "").slice(0, 300) }, r => {
      window.postMessage({ flous: "applyResult", ok: !!(r && r.ok), error: r && r.error }, location.origin);
    });
  }
  if (d.flous === "applyBatch" && Array.isArray(d.items)) {
    const items = d.items.filter(x => x && web(x.url)).slice(0, 30);
    chrome.runtime.sendMessage({ type: "applyBatch", items, autoSubmit: !!d.autoSubmit, consent: !!d.consent }, r => {
      window.postMessage({ flous: "batchStarted", ok: !!(r && r.ok), n: r && r.n, error: r && r.error }, location.origin);
    });
  }
  if (d.flous === "stopBatch") chrome.runtime.sendMessage({ type: "stopBatch" });
});
// progress from the agents -> the page
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (sender.id === chrome.runtime.id && msg && msg.flous === "batchResult") window.postMessage(msg, location.origin);
});
