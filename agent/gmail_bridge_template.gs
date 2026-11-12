/**
 * Flous Job Agent — Gmail bridge (runs inside YOUR Google account, read-only).
 *
 * 1) It keeps your applications database: a Google Sheet "Flous – My applications" in your Drive.
 * 2) It only READS emails that look like replies to job / internship / scholarship applications
 * from the last few days, and returns them to your job agent when it calls with the secret key.
 * It never sends, deletes, labels or changes any email.
 *
 * Setup: paste this whole file into a new Apps Script project (script.new), then
 * Deploy > New deployment > type "Web app" > Execute as: Me > Who has access: Anyone > Deploy,
 * allow access when Google asks, and copy the "Web app URL".
 */
const KEY = "__KEY__";   // secret shared with your agent — do not share this file

const QUERY = [
  "-in:sent -in:drafts -in:chats -category:promotions -category:social",
  "(application OR applying OR applied OR candidature OR candidate OR interview OR entretien OR assessment",
  "OR \"coding challenge\" OR \"take-home\" OR \"next steps\" OR unfortunately OR regret OR \"not moving forward\"",
  "OR offer OR shortlisted OR position OR role OR internship OR stage OR scholarship OR fellowship OR recruiter",
  "OR greenhouse OR lever OR workable OR ashby OR smartrecruiters OR teamtailor OR workday)"
].join(" ");

function doGet(e) {
  const p = (e && e.parameter) || {};
  if (!safeEq_(p.key, KEY)) return json_({ error: "forbidden" });
  if (p.action === "track") return json_(loadTrack_());
  const days = Math.max(1, Math.min(Number(p.days) || 3, 60));
  const since = new Date(Date.now() - days * 864e5);
  const me = Session.getActiveUser().getEmail().toLowerCase();
  const out = [];
  const threads = GmailApp.search(QUERY + " newer_than:" + days + "d", 0, 150);
  threads.forEach(function (t) {
    t.getMessages().forEach(function (m) {
      if (m.getDate() < since) return;
      const from = m.getFrom();
      if (me && from.toLowerCase().indexOf(me) >= 0) return;          // skip your own messages
      if (/jobalert|job-alert|jobs-noreply@linkedin|alert@indeed|newsletter|digest/i.test(from + " " + m.getSubject())) return;
      out.push({
        id: m.getId(),
        msgid: m.getHeader("Message-ID") || "",
        from: from,
        subject: m.getSubject(),
        date: m.getDate().toISOString(),
        body: (m.getPlainBody() || "").replace(/\s+/g, " ").slice(0, 2500)
      });
    });
  });
  return json_({ emails: out.slice(0, 120) });
}

/* ===================== Applications database (Google Sheet in your Drive) ===================== */
const SHEET_NAME = "Flous – My applications";
const COLS = ["ID", "Title", "Company", "Category", "Location", "Status", "Applied on", "Last update", "Link",
              "Not-interested reason", "Notes", "History", "Data (do not edit)"];

function sheet_() {
  const props = PropertiesService.getScriptProperties();
  let ss = null;
  const id = props.getProperty("SHEET_ID");
  if (id) { try { ss = SpreadsheetApp.openById(id); } catch (e) { ss = null; } }
  if (!ss) {
    ss = SpreadsheetApp.create(SHEET_NAME);
    props.setProperty("SHEET_ID", ss.getId());
    const sh = ss.getSheets()[0];
    sh.setName("Applications");
    sh.appendRow(COLS);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, COLS.length).setFontWeight("bold").setBackground("#eef0ff");
    sh.setColumnWidth(2, 320); sh.setColumnWidth(13, 60);
  }
  return ss;
}

// Text that starts with = + - @ would run as a spreadsheet formula (a scraped job title could be "=IMPORTXML(...)").
function cell_(v) {
  const t = String(v == null ? "" : v).slice(0, 5000);
  return /^[=+\-@\t\r]/.test(t) ? "'" + t : t;
}

function tab_(ss) { return ss.getSheetByName("Applications") || ss.getSheets()[0]; }

function loadTrack_() {
  const ss = sheet_(), v = tab_(ss).getDataRange().getValues(), out = {};
  for (let i = 1; i < v.length; i++) {
    if (!v[i][0]) continue;
    try { out[v[i][0]] = JSON.parse(v[i][12] || "{}"); } catch (e) { out[v[i][0]] = {}; }
  }
  return { track: out, sheet: ss.getUrl() };
}

function saveTrack_(items) {
  const lock = LockService.getScriptLock();
  lock.waitLock(25000);
  try {
    const ss = sheet_(), sh = tab_(ss), v = sh.getDataRange().getValues(), rowOf = {};
    for (let i = 1; i < v.length; i++) rowOf[v[i][0]] = i + 1;
    (items || []).slice(0, 200).forEach(function (it) {
      if (!it || typeof it.id !== "string" || it.id.length > 300) return;
      const t = it.track || {}, s = t.snap || {};
      const hist = (t.history || []).map(function (h) { return h.s + " " + String(h.at || "").slice(0, 10) + (h.by && h.by !== "you" ? " (" + h.by + ")" : ""); }).join(" → ");
      const url = /^https?:\/\//i.test(String(s.url || "")) ? s.url : "";
      const row = [it.id, s.title, s.company, s.category, s.location, t.status,
        String(t.applied_at || "").slice(0, 10), new Date().toISOString().slice(0, 16).replace("T", " "), url,
        t.na, t.note, hist].map(cell_).concat([cell_(JSON.stringify(t).slice(0, 49000))]);
      if (rowOf[it.id]) sh.getRange(rowOf[it.id], 1, 1, row.length).setValues([row]);
      else { sh.appendRow(row); rowOf[it.id] = sh.getLastRow(); }
    });
    return { ok: true, saved: (items || []).length, sheet: ss.getUrl() };
  } finally { lock.releaseLock(); }
}

function doPost(e) {
  let b = {};
  if (e && e.postData && e.postData.contents && e.postData.contents.length > 2000000) return json_({ error: "too large" });
  try { b = JSON.parse((e && e.postData && e.postData.contents) || "{}"); } catch (x) { return json_({ error: "bad json" }); }
  if (!safeEq_(b.key, KEY)) return json_({ error: "forbidden" });
  if (b.action === "load") return json_(loadTrack_());
  if (b.action === "save") return json_(saveTrack_(b.items));
  return json_({ error: "unknown action" });
}

// constant-time comparison of the shared secret
function safeEq_(a, b) {
  a = String(a || ""); b = String(b || "");
  let d = a.length ^ b.length;
  for (let i = 0; i < b.length; i++) d |= (a.charCodeAt(i % (a.length || 1)) || 0) ^ b.charCodeAt(i);
  return d === 0 && b.length > 0;
}

function json_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}

/** Optional: click Run on this once to check it works (see View > Logs). */
function test() {
  const r = JSON.parse(doGet({ parameter: { key: KEY, days: 14 } }).getContent());
  Logger.log((r.emails || []).length + " job-related emails found in the last 14 days");
  Logger.log("Applications sheet: " + sheet_().getUrl());
}
