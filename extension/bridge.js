/* Runs on your dashboard only: lets the swipe page ask the extension to open an application and fill it. */
document.documentElement.dataset.flousExt = "1";
window.addEventListener("message", e => {
  if (e.source !== window || !e.data || e.data.flous !== "apply") return;
  chrome.runtime.sendMessage({ type: "autoApply", url: e.data.url, title: e.data.title || "" }, r => {
    window.postMessage({ flous: "applyResult", ok: !!(r && r.ok), error: r && r.error }, "*");
  });
});
