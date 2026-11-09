/**
 * Flous Job Agent — Gmail bridge (runs inside YOUR Google account, read-only).
 *
 * It only READS emails that look like replies to job / internship / scholarship applications
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
  if (p.key !== KEY) return json_({ error: "forbidden" });
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

function json_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}

/** Optional: click Run on this once to check it works (see View > Logs). */
function test() {
  const r = JSON.parse(doGet({ parameter: { key: KEY, days: 14 } }).getContent());
  Logger.log((r.emails || []).length + " job-related emails found in the last 14 days");
}
