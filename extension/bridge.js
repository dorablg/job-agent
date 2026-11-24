/* Runs on your dashboard only: lets the page ask the extension to open applications, fill them, and run agent batches.
   Accepts messages from this exact page (same window, same origin) and only http(s) links. */
document.documentElement.dataset.flousExt = "2";   // 2 = supports agent batches
document.documentElement.dataset.flousVersion = chrome.runtime.getManifest().version;
const web = u => typeof u === "string" && /^https?:\/\//i.test(u);

// Always report WHY something failed: an extension updated on disk but not reloaded, or a page opened before the
// extension was reloaded, are the usual causes.
function ask(msg, done) {
  try {
    chrome.runtime.sendMessage(msg, r => {
      const err = chrome.runtime.lastError && chrome.runtime.lastError.message;
      if (err) return done({ ok: false, error: /receiving end|port closed/i.test(err)
        ? "The extension isn't responding. Open your extensions page, click ↻ on Flous, then reload this page." : err });
      done(r || { ok: false, error: "No answer from the extension. Click ↻ on Flous in your extensions page, then reload this page." });
    });
  } catch (e) {
    done({ ok: false, error: /context invalidated/i.test(String(e))
      ? "The extension was updated: reload this page (F5)." : String(e) });
  }
}

window.addEventListener("message", e => {
  if (e.source !== window || e.origin !== location.origin) return;
  const d = e.data;
  if (!d) return;
  if (d.flous === "apply" && web(d.url)) {
    ask({ type: "autoApply", url: d.url, title: String(d.title || "").slice(0, 300) },
      r => window.postMessage({ flous: "applyResult", ok: !!r.ok, error: r.error }, location.origin));
  }
  if (d.flous === "applyBatch" && Array.isArray(d.items)) {
    const items = d.items.filter(x => x && web(x.url)).slice(0, 30);
    ask({ type: "applyBatch", items, autoSubmit: !!d.autoSubmit, consent: !!d.consent },
      r => window.postMessage({ flous: "batchStarted", ok: !!r.ok, n: r.n, error: r.error }, location.origin));
  }
  if (d.flous === "ping") ask({ type: "ping" }, r => window.postMessage({ flous: "pong", ...r }, location.origin));
  if (d.flous === "stopBatch") ask({ type: "stopBatch" }, () => {});
});
// progress from the agents -> the page
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (sender.id === chrome.runtime.id && msg && msg.flous === "batchResult") window.postMessage(msg, location.origin);
});
