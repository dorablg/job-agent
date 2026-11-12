/* Runs on your dashboard only: lets the swipe page ask the extension to open an application and fill it.
   Accepts messages from this exact page (same window, same origin) and only http(s) links. */
document.documentElement.dataset.flousExt = "1";
window.addEventListener("message", e => {
  if (e.source !== window || e.origin !== location.origin) return;
  const d = e.data;
  if (!d || d.flous !== "apply" || typeof d.url !== "string" || !/^https?:\/\//i.test(d.url)) return;
  chrome.runtime.sendMessage({ type: "autoApply", url: d.url, title: String(d.title || "").slice(0, 300) }, r => {
    window.postMessage({ flous: "applyResult", ok: !!(r && r.ok), error: r && r.error }, location.origin);
  });
});
