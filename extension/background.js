/* Flous Apply Assistant — coordinates: read form (all frames) -> AI answers -> fill + attach files. */
importScripts("core.js");

let CACHE = null;  // decrypted dashboard data, kept only while the browser is open
async function data() {
  if (CACHE) return CACHE;
  const { password } = await chrome.storage.local.get("password");
  if (!password) throw new Error("Open Settings and enter your dashboard password first.");
  CACHE = await FLOUS.loadDashboard(password);
  return CACHE;
}

async function fillTab(tabId) {
  const D = await data();
  if (!D.gemini_key) throw new Error("No AI key found in your dashboard data.");
  await chrome.scripting.executeScript({ target: { tabId, allFrames: true }, files: ["content.js"] });
  const scans = await chrome.scripting.executeScript({ target: { tabId, allFrames: true }, func: () => window.__flous && window.__flous.scan() });
  const frames = scans.filter(s => s.result && s.result.fields && s.result.fields.length).sort((a, b) => b.result.fields.length - a.result.fields.length);
  if (!frames.length) throw new Error("No form found on this page. Click the company's Apply button first, then try again.");
  const top = scans.find(s => s.frameId === 0) || frames[0];
  const page = { ...frames[0].result, title: (top.result && top.result.title) || frames[0].result.title,
                 text: ((top.result && top.result.text) || "") + " " + frames[0].result.text };
  let listing = FLOUS.matchListing(D, page);
  // no tailored kit yet for this posting? write one now (ATS CV + cover letter + answers)
  if (!(listing && listing.ai && listing.ai.ats_cv)) {
    try {
      const kit = await FLOUS.generateKit(D, listing, page);
      if (kit) listing = Object.assign({}, listing || { title: page.title, company: page.host, kind: "", description: page.text }, { ai: kit });
    } catch (e) { /* fall back to the base CV */ }
  }
  const fields = frames.flatMap(f => f.result.fields);
  const out = await FLOUS.ask(D.gemini_key, FLOUS.buildPrompt(D, listing, page, fields));
  const A = D.applicant || {};
  const base = `${A.first_name || "CV"}_${A.last_name || ""}`.replace(/\s+/g, "_");
  const letterAnswer = (out.answers || []).map(a => String(a.value || "")).find(v => v.length > 600) || "";
  const letter = (listing && listing.ai && listing.ai.cover_letter) || letterAnswer;
  const files = { cv: { name: `${base}_CV.pdf`, b64: FLOUS.cvPdf(D, listing) } };
  if (letter) files.cover_letter = { name: `${base}_Cover_Letter.pdf`, b64: FLOUS.letterPdf(D, letter) };
  let total = { filled: 0, attached: 0, left: 0 };
  for (const f of frames) {
    const [r] = await chrome.scripting.executeScript({ target: { tabId, frameIds: [f.frameId] },
      func: (a, fl, n, t) => window.__flous.fill(a, fl, n, t), args: [out.answers || [], files, f === frames[0] ? (out.notes || []) : [], listing ? listing.title : ""] });
    if (r && r.result) { total.filled += r.result.filled; total.attached += r.result.attached; total.left += r.result.left; }
  }
  return { ...total, job: listing ? `${listing.title}${listing.company ? " — " + listing.company : ""}` : "(not in your dashboard — used the page text)",
           student: FLOUS.studentRule(D, listing, page).startsWith("She IS") };
}

/* ---------- swipe right on the dashboard: open the job, click its Apply button, fill the form ---------- */
const AUTO = {};  // tabId -> {steps, title}
const wait = ms => new Promise(r => setTimeout(r, ms));
async function formSize(tabId) {
  await chrome.scripting.executeScript({ target: { tabId, allFrames: true }, files: ["content.js"] });
  const r = await chrome.scripting.executeScript({ target: { tabId, allFrames: true }, func: () => window.__flous ? window.__flous.formSize() : 0 });
  return Math.max(0, ...r.map(x => x.result || 0));
}
async function autoStep(tabId) {
  const job = AUTO[tabId]; if (!job || job.busy) return;
  job.busy = true;
  try {
    await wait(1500);
    if (await formSize(tabId) >= 3) { delete AUTO[tabId]; await fillTab(tabId); return; }
    if (job.steps >= 3) { delete AUTO[tabId]; return; }   // give up quietly: she can click ⚡ herself
    job.steps++;
    const [r] = await chrome.scripting.executeScript({ target: { tabId }, func: () => window.__flous.clickApply() });
    const res = (r && r.result) || {};
    if (res.href) { await chrome.tabs.update(tabId, { url: res.href }); }          // onUpdated continues
    else if (res.clicked) { await wait(3500); job.busy = false; return autoStep(tabId); }  // same-page form (SPA)
    else { delete AUTO[tabId]; }
  } catch (e) { delete AUTO[tabId]; }
  finally { if (AUTO[tabId]) AUTO[tabId].busy = false; }
}
chrome.tabs.onUpdated.addListener((tabId, info) => { if (info.status === "complete" && AUTO[tabId]) autoStep(tabId); });
chrome.tabs.onCreated.addListener(tab => {   // the site opened the form in a new tab: follow it
  if (tab.openerTabId && AUTO[tab.openerTabId]) { AUTO[tab.id] = { ...AUTO[tab.openerTabId], busy: false }; delete AUTO[tab.openerTabId]; }
});

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (msg.type === "autoApply") {
    chrome.tabs.create({ url: msg.url, active: true }).then(tab => { AUTO[tab.id] = { steps: 0, title: msg.title, busy: false }; reply({ ok: true }); })
      .catch(e => reply({ ok: false, error: String(e) }));
    return true;
  }
  if (msg.type === "fill") { fillTab(msg.tabId).then(r => reply({ ok: true, ...r })).catch(e => reply({ ok: false, error: String(e.message || e) })); return true; }
  if (msg.type === "reload") { CACHE = null; data().then(D => reply({ ok: true, n: (D.listings || []).length })).catch(e => reply({ ok: false, error: String(e.message || e) })); return true; }
});
chrome.commands.onCommand.addListener(async cmd => {
  if (cmd !== "fill-page") return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab) fillTab(tab.id).catch(() => {});
});
