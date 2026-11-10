/* Flous Apply Assistant — shared logic (used by background.js; no browser-extension APIs in here so it can be tested in a page). */
var FLOUS = (function () {
  const DASHBOARD = "https://dorablg.github.io/job-agent/";
  const MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-flash-latest"];

  /* ---------- dashboard data (same encryption as the website) ---------- */
  const b64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
  async function loadDashboard(password) {
    const html = await (await fetch(DASHBOARD + "?t=" + Date.now(), { cache: "no-store" })).text();
    const m = html.match(/const BLOB = (\{[^\n]*?\});/);
    if (!m) throw new Error("Could not read the dashboard page");
    const blob = JSON.parse(m[1]);
    const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveKey"]);
    const aes = await crypto.subtle.deriveKey({ name: "PBKDF2", salt: b64(blob.salt), iterations: blob.iter, hash: "SHA-256" },
      key, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
    let plain;
    try { plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: b64(blob.iv) }, aes, b64(blob.ct)); }
    catch (e) { throw new Error("Wrong dashboard password"); }
    return JSON.parse(new TextDecoder().decode(plain));
  }

  /* ---------- which listing is this page about? ---------- */
  const norm = s => String(s || "").toLowerCase().replace(/[^a-z0-9à-ÿ]+/g, " ").trim();
  function matchListing(D, page) {
    const host = norm(page.host), text = norm(page.title + " " + page.text.slice(0, 6000)), url = page.url || "";
    let best = null, bestScore = 0;
    for (const r of D.listings || []) {
      let s = 0;
      if (r.url && url && (url.startsWith(r.url) || r.url.startsWith(url.split("?")[0]))) s += 10;
      const co = norm(r.company);
      if (co && co.length > 2 && (host.includes(co.replace(/ /g, "")) || text.includes(co))) s += 3;
      const t = norm(r.title).replace(/\b(hackathon|remote|hybrid|m f d|f m x)\b/g, "").trim();
      if (t && t.length > 5 && text.includes(t)) s += 4;
      else {
        const words = t.split(" ").filter(w => w.length > 3);
        if (words.length && words.filter(w => text.includes(w)).length / words.length >= 0.8) s += 2;
      }
      if (s > bestScore) { best = r; bestScore = s; }
    }
    return bestScore >= 5 ? best : null;
  }

  /* ---------- student rule (same as the agent) ---------- */
  function studentRule(D, listing, page) {
    const studentKinds = ["internship", "fellowship", "event"];
    const title = (listing && listing.title) || page.title || "";
    const looksStudent = /intern|internship|stage|tirocinio|working student|werkstudent|student|scholarship|fellowship|summer school|exchange|hackathon|volunteer|ambassador/i.test(title + " " + page.text.slice(0, 1500));
    const isStudent = listing ? (studentKinds.includes(listing.kind) || /working student|werkstudent|student|intern/i.test(title) ||
                                 ((D.student_rules || {})[listing.category] || "").startsWith("She IS")) : looksStudent;
    return isStudent ? (D.student_yes || "She IS a student: mention her engineering degree in progress at École Polytechnique de Sousse.")
                     : (D.student_no || "This is a JOB application: do not mention that she is currently a student.");
  }

  /* ---------- the AI writes the answers ---------- */
  function buildPrompt(D, listing, page, fields) {
    const A = D.applicant || {};
    const ai = (listing && listing.ai) || {};
    const job = listing ? `${listing.title} at ${listing.company || "(see page)"} — ${listing.location || ""}\n${(listing.description || "").slice(0, 4000)}`
                        : `${page.title}\n${page.text.slice(0, 6000)}`;
    const qa = (ai.screening_answers || []).map(x => `Q: ${x.question}\nA: ${x.answer}`).join("\n\n");
    const f = fields.map(x => ({ id: x.id, type: x.type, question: x.label.slice(0, 300), required: x.required,
      options: x.options && x.options.length ? x.options.slice(0, 40) : undefined, current: x.value || undefined }));
    return `You fill in an online application form for Dorra Bouallegue. She will review it and click Submit herself.

STUDENT RULE (very important): ${studentRule(D, listing, page)}

HER PROFILE: ${D.profile || ""}
HER CONTACT DETAILS: ${JSON.stringify(A)}
HER CV (the ONLY source of facts — never invent employers, degrees, dates, numbers, skills or tools):
"""${(D.cv || "").slice(0, 9000)}"""
${ai.cover_letter ? `\nCOVER LETTER ALREADY WRITTEN FOR THIS POSTING:\n"""${ai.cover_letter}"""` : ""}
${qa ? `\nANSWERS ALREADY WRITTEN FOR THIS POSTING:\n${qa}` : ""}

THE OPPORTUNITY:
"""${job}"""

THE FORM FIELDS (JSON):
${JSON.stringify(f)}

RULES:
- "Describe a time when..." / behavioural questions: describe the REAL type of situation she handles (from the CV) in general,
  honest terms ("At PayPal Europe I regularly investigate...") — never invent a specific incident, customer, number or outcome.
- Contact fields: use her contact details exactly. Full name = first + last name. Country: Tunisia. City: Sousse.
- Text questions (why us, motivation, experience, projects, strengths): specific, first person, 60-150 words, true facts from the CV,
  using the posting's words where they truthfully apply. Cover letter fields: the cover letter (or a new one, 250-350 words).
- Select / radio fields: the value MUST be exactly one of the given options. Checkbox groups: list the options to tick.
- Work authorization: she is a Tunisian citizen living in Tunisia. For on-site roles in the EU / UK / Gulf / elsewhere she is NOT
  currently authorized and WOULD need visa sponsorship (answer truthfully). For remote-from-Tunisia roles she needs no visa.
- Notice period / availability: use her details ("2 weeks" unless the details say otherwise). Start date: as soon as possible.
- Languages: Arabic native, French advanced, English C1. Years of experience: about 1 year professional + internships.
- Salary questions: if free text, write "Open to discuss, in line with the market for this level". If a NUMBER is required,
  leave it empty and add a note for her.
- Gender, ethnicity, race, disability, veteran, sexual orientation (equal-opportunity questions): choose the option meaning
  "prefer not to say / decline to self-identify" if it exists, otherwise leave empty.
- Consent, privacy policy, terms, "I confirm/certify", data-processing or marketing checkboxes: NEVER tick — leave for her.
- "How did you hear about us": "Online job board" (or the closest option).
- Unknown personal facts (date of birth, ID numbers, references' details, exact grades): leave empty and add a note.
- File upload fields: put "cv" for resume/CV, "cover_letter" for cover letter / motivation letter uploads, "" for anything else.

Return ONLY JSON: {"answers": [{"id": "<field id>", "value": "<text, or the exact option, or a list of options for checkbox groups>"}],
"notes": ["things she must check or fill herself, max 6 short items"]}`;
  }

  async function ask(geminiKey, prompt) {
    let err = "";
    for (const m of MODELS) {
      try {
        const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${m}:generateContent`, {
          method: "POST", headers: { "Content-Type": "application/json", "x-goog-api-key": geminiKey },
          body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }], generationConfig: { temperature: 0.4, responseMimeType: "application/json" } })
        });
        if (!res.ok) { err = `${m}: HTTP ${res.status}`; if ([400, 404, 429, 500, 503].includes(res.status)) continue; break; }
        const j = await res.json();
        const txt = j.candidates[0].content.parts.map(p => p.text || "").join("").replace(/^```(json)?|```$/gm, "").trim();
        const out = JSON.parse(txt);
        return Array.isArray(out) ? { answers: out, notes: [] } : out;
      } catch (e) { err = String(e); }
    }
    throw new Error("The free AI is busy (" + err + "). Try again in a minute.");
  }

  /* ---------- tiny PDF writer (text-only, ATS-friendly, no external library) ---------- */
  const WIN = { "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "...", "•": "\x95", " ": " " };
  function pdfText(s) {
    let out = "";
    for (let ch of String(s)) {
      if (/[--]/.test(ch)) ch = "•";  // odd bullets copied from PDFs
      const c = WIN[ch] !== undefined ? WIN[ch] : ch;
      const code = c.charCodeAt(0);
      if (c === "(" || c === ")" || c === "\\") out += "\\" + c;
      else if (code < 32) out += " ";
      else if (code < 128) out += c;
      else if (code < 256) out += "\\" + code.toString(8).padStart(3, "0");
      else out += "?";
    }
    return out;
  }
  function wrap(text, size, width) {
    const maxChars = Math.max(10, Math.floor(width / (size * 0.5)));
    const lines = [];
    for (const para of String(text).split("\n")) {
      let line = "";
      for (const w of para.split(/\s+/)) {
        if ((line + " " + w).trim().length > maxChars) { if (line) lines.push(line); line = w; }
        else line = (line + " " + w).trim();
      }
      lines.push(line);
    }
    return lines;
  }
  /* blocks: [{text, size, bold, gap, indent}] -> PDF bytes as base64 */
  function makePdf(blocks) {
    const W = 595, H = 842, M = 50, pages = [[]];
    let y = H - M;
    for (const b of blocks) {
      const size = b.size || 10.5, lead = size * 1.35, x = M + (b.indent || 0);
      y -= b.gap || 0;
      for (const ln of wrap(b.text, size, W - M - x)) {
        if (y < M + lead) { pages.push([]); y = H - M; }
        pages[pages.length - 1].push(`BT /${b.bold ? "F2" : "F1"} ${size} Tf ${x} ${y.toFixed(1)} Td (${pdfText(ln)}) Tj ET`);
        y -= lead;
      }
      if (b.rule) { pages[pages.length - 1].push(`0.3 w ${M} ${(y + lead * 0.55).toFixed(1)} m ${W - M} ${(y + lead * 0.55).toFixed(1)} l S`); }
    }
    const objs = [];
    const add = s => { objs.push(s); return objs.length; };
    const catalog = add(""), pagesObj = add("");
    const f1 = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>");
    const f2 = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>");
    const kids = [];
    for (const p of pages) {
      const content = p.join("\n");
      const cs = add(`<< /Length ${content.length} >>\nstream\n${content}\nendstream`);
      kids.push(add(`<< /Type /Page /Parent ${pagesObj} 0 R /MediaBox [0 0 ${W} ${H}] /Resources << /Font << /F1 ${f1} 0 R /F2 ${f2} 0 R >> >> /Contents ${cs} 0 R >>`));
    }
    objs[catalog - 1] = `<< /Type /Catalog /Pages ${pagesObj} 0 R >>`;
    objs[pagesObj - 1] = `<< /Type /Pages /Kids [${kids.map(k => k + " 0 R").join(" ")}] /Count ${kids.length} >>`;
    let pdf = "%PDF-1.4\n", offsets = [];
    objs.forEach((o, i) => { offsets.push(pdf.length); pdf += `${i + 1} 0 obj\n${o}\nendobj\n`; });
    const xref = pdf.length;
    pdf += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n` + offsets.map(o => String(o).padStart(10, "0") + " 00000 n \n").join("");
    pdf += `trailer\n<< /Size ${objs.length + 1} /Root ${catalog} 0 R >>\nstartxref\n${xref}\n%%EOF`;
    let bin = ""; for (let i = 0; i < pdf.length; i++) bin += String.fromCharCode(pdf.charCodeAt(i) & 255);
    return btoa(bin);
  }
  const L = v => Array.isArray(v) ? v.map(x => typeof x === "object" && x ? Object.values(x).join(" — ") : String(x)) : (v ? [String(v)] : []);
  function cvPdf(D, listing) {
    const c = listing && listing.ai && listing.ai.ats_cv;
    if (!c) {  // no tailored CV for this posting: her base CV text
      const A = D.applicant || {};
      return makePdf([{ text: `${A.first_name || ""} ${A.last_name || ""}`, size: 18, bold: true },
                      { text: D.cv || "", size: 10, gap: 8 }]);
    }
    const B = [{ text: c.name || "", size: 18, bold: true }];
    if (c.headline) B.push({ text: c.headline, size: 11.5 });
    B.push({ text: c.contact || "", size: 9.5, gap: 2 });
    const H = t => B.push({ text: t, size: 11.5, bold: true, gap: 10, rule: true });
    if (c.summary) { H("PROFESSIONAL SUMMARY"); B.push({ text: c.summary }); }
    if ((c.skills || []).length) { H("SKILLS"); L(c.skills).forEach(s => B.push({ text: "• " + s, indent: 6 })); }
    if ((c.experience || []).length) {
      H("PROFESSIONAL EXPERIENCE");
      for (const e of c.experience) {
        if (typeof e !== "object") { B.push({ text: String(e) }); continue; }
        B.push({ text: `${e.title || ""} — ${e.company || ""}`, bold: true, gap: 5 });
        B.push({ text: [e.location, e.dates].filter(Boolean).join(" | "), size: 9.5 });
        L(e.bullets).forEach(x => B.push({ text: "• " + x, indent: 6 }));
      }
    }
    if ((c.projects || []).length) { H("PROJECTS"); for (const p of c.projects) { if (typeof p === "object") { B.push({ text: p.name || "", bold: true, gap: 4 }); L(p.bullets).forEach(x => B.push({ text: "• " + x, indent: 6 })); } } }
    if ((c.education || []).length) { H("EDUCATION"); c.education.forEach(e => B.push({ text: typeof e === "object" ? `${e.degree || ""} — ${e.school || ""}${e.dates ? " (" + e.dates + ")" : ""}` : String(e) })); }
    if ((c.certifications || []).length) { H("CERTIFICATIONS"); L(c.certifications).forEach(x => B.push({ text: "• " + x, indent: 6 })); }
    if ((c.languages || []).length) { H("LANGUAGES"); B.push({ text: L(c.languages).join(", ") }); }
    return makePdf(B);
  }
  function letterPdf(D, text) {
    const A = D.applicant || {};
    return makePdf([{ text: `${A.first_name || ""} ${A.last_name || ""}`, size: 14, bold: true },
                    { text: [A.email, A.phone, A.location].filter(Boolean).join(" | "), size: 9.5 },
                    { text: new Date().toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" }), gap: 14 },
                    { text: text || "", gap: 10 }]);
  }

  /* ---------- write a tailored kit (ATS CV, cover letter, answers) for a posting that has none ---------- */
  async function generateKit(D, listing, page) {
    const r = listing || {};
    const desc = (r.description || page.text || "").slice(0, 9000);
    const kind = r.kind || (/intern|stage|tirocinio/i.test(page.title) ? "internship" : "job");
    const prompt = (D.prompt || "").replace("{student_rule}", studentRule(D, listing, page))
      .replace("{kind_note}", ((D.kind_notes || {})[kind]) || "").replace("{profile}", D.profile || "").replace("{cv}", (D.cv || "").slice(0, 12000))
      .replace("{kind}", kind).replace("{category}", r.category || "").replace("{title}", r.title || page.title)
      .replaceAll("{company}", r.company || page.host).replace("{location}", r.location || "n/a").replace("{mode}", r.mode || "")
      .replace("{desc}", desc).replace("{matched}", (r.matched || []).join(", ") || "none").replace("{missing}", (r.missing || []).join(", ") || "none");
    if (!prompt.trim()) return null;
    const kit = await ask(D.gemini_key, prompt);
    return kit && kit.ats_cv ? kit : null;
  }

  return { loadDashboard, matchListing, buildPrompt, ask, cvPdf, letterPdf, makePdf, studentRule, generateKit };
})();
