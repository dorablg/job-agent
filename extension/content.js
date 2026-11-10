/* Flous Apply Assistant — runs inside the application page (and its frames). Reads fields, fills answers, shows a summary.
   It never clicks Submit and never ticks consent / terms boxes. */
(function () {
  if (window.__flous) return;

  const SKIP_TYPES = ["hidden", "submit", "button", "reset", "image", "password", "search"];
  const visible = el => { const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    return (r.width > 0 || r.height > 0 || el.type === "file") && cs.visibility !== "hidden" && cs.display !== "none"; };
  const clean = s => String(s || "").replace(/\s+/g, " ").replace(/\*+/g, "").trim();

  function questionFor(el) {
    const parts = [];
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) parts.push(l.innerText); }
    const lb = el.getAttribute("aria-labelledby");
    if (lb) lb.split(/\s+/).forEach(id => { const n = document.getElementById(id); if (n) parts.push(n.innerText); });
    if (el.getAttribute("aria-label")) parts.push(el.getAttribute("aria-label"));
    const wrapLabel = el.closest("label"); if (wrapLabel && !parts.length) parts.push(wrapLabel.innerText);
    const fs = el.closest("fieldset"); if (fs) { const lg = fs.querySelector("legend"); if (lg) parts.push(lg.innerText); }
    if (!parts.length) {
      const box = el.closest('[class*="question"],[class*="field"],[class*="form-group"],[class*="FormField"],[data-qa],[role="group"],li,tr,p,div');
      if (box) { const t = box.querySelector("label,legend,h3,h4,.label,[class*=label],[class*=title]"); if (t) parts.push(t.innerText); }
    }
    if (el.placeholder) parts.push("(" + el.placeholder + ")");
    if (!parts.length && el.name) parts.push(el.name.replace(/[_\[\]]+/g, " "));
    return clean(parts.join(" — ")).slice(0, 400);
  }

  let counter = 0;
  function scan() {
    const fields = [], groups = {};
    document.querySelectorAll("input, textarea, select").forEach(el => {
      const type = (el.type || el.tagName).toLowerCase();
      if (SKIP_TYPES.includes(type) || el.disabled || (el.readOnly && type !== "file")) return;
      if (type !== "file" && !visible(el)) return;
      if ((type === "radio" || type === "checkbox") && el.name) {
        const key = type + ":" + el.name;
        const optLabel = clean((el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`) || el.closest("label") || {}).innerText || el.value);
        if (!groups[key]) {
          const id = "f" + (++counter); el.dataset.flous = id;
          const fs = el.closest("fieldset"), lg = fs && fs.querySelector("legend");
          const box = el.closest('[role="radiogroup"],[role="group"],[class*="question"],[class*="field"],[class*="form-group"]');
          const boxLabel = box && box.querySelector("label:not(:has(input)),legend,h3,h4,[class*=label]:not(:has(input))");
          const groupLabel = clean((lg && lg.innerText) || (boxLabel && boxLabel.innerText) || "") || questionFor(el);
          groups[key] = { id, type: type === "radio" ? "radio" : "checkboxes", name: el.name, label: groupLabel.slice(0, 400), options: [], required: el.required };
          fields.push(groups[key]);
        }
        groups[key].options.push(optLabel);
        return;
      }
      const id = el.dataset.flous || ("f" + (++counter)); el.dataset.flous = id;
      const f = { id, type: type === "select-one" || type === "select-multiple" ? "select" : type, label: questionFor(el),
                  required: el.required || el.getAttribute("aria-required") === "true", value: type === "file" ? "" : el.value };
      if (el.tagName === "SELECT") f.options = [...el.options].map(o => clean(o.text)).filter(t => t && !/^(select|choose|--|please)/i.test(t));
      if (type === "checkbox") f.options = ["checked"];
      fields.push(f);
    });
    return { url: location.href, host: location.host, title: document.title,
             text: clean((document.querySelector("main") || document.body).innerText).slice(0, 12000), fields };
  }

  const setValue = (el, v) => {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, v);
    el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new Event("blur", { bubbles: true }));
  };
  const mark = (el, ok) => { el.style.outline = ok ? "2px solid #22a06b" : "2px solid #e5a000"; el.style.outlineOffset = "2px"; };
  const CONSENT = /consent|agree|privacy|terms|certify|confirm that|acknowledge|gdpr|data processing|marketing|newsletter|policy/i;
  const same = (a, b) => clean(a).toLowerCase() === clean(b).toLowerCase();
  const near = (a, b) => { a = clean(a).toLowerCase(); b = clean(b).toLowerCase(); return a && b && (a.includes(b) || b.includes(a)); };

  function b64File(b64, name) {
    const bin = atob(b64), bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new File([bytes], name, { type: "application/pdf" });
  }

  function fill(answers, files, notes, jobTitle) {
    const byId = {}; (answers || []).forEach(a => { if (a && a.id) byId[a.id] = a.value; });
    let filled = 0, attached = 0; const left = [];
    document.querySelectorAll("[data-flous]").forEach(el => {
      const id = el.dataset.flous, type = (el.type || el.tagName).toLowerCase(), v = byId[id];
      if (type === "radio" || (type === "checkbox" && el.name && document.querySelectorAll(`input[type=checkbox][name="${CSS.escape(el.name)}"]`).length > 1)) {
        const group = document.querySelectorAll(`input[type="${type}"][name="${CSS.escape(el.name)}"]`);
        const want = [].concat(v || []).map(String);
        const label = questionFor(el);
        if (!want.length || (type === "checkbox" && CONSENT.test(label))) { if (el.required) left.push(label); return; }
        group.forEach(o => {
          const t = clean((o.id && document.querySelector(`label[for="${CSS.escape(o.id)}"]`) || o.closest("label") || {}).innerText || o.value);
          if (want.some(w => same(w, t)) || (!want.some(w => group.length && [...group].some(g => same(w, g.value))) && want.some(w => near(w, t) && t.length > 1))) {
            if (!o.checked) { o.click(); } mark(o, true); filled++;
          }
        });
        return;
      }
      if (type === "file") {
        const which = String(v || "").toLowerCase();
        const lab = questionFor(el).toLowerCase();
        const kind = which === "cover_letter" || /cover|motivation/.test(lab) ? "cover_letter" : (which === "cv" || /resume|résumé|cv|curriculum/.test(lab) ? "cv" : "");
        const f = kind && files && files[kind];
        if (f && (!el.files || !el.files.length)) {
          try { const dt = new DataTransfer(); dt.items.add(b64File(f.b64, f.name)); el.files = dt.files;
                el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true }));
                attached++; mark(el.closest("div") || el, true); }
          catch (e) { left.push("Upload " + (kind === "cv" ? "your CV" : "your cover letter") + " (" + lab.slice(0, 60) + ")"); }
        }
        return;
      }
      if (type === "checkbox") {
        const label = questionFor(el);
        if (CONSENT.test(label)) { mark(el, false); left.push("Tick yourself if you agree: " + label.slice(0, 80)); return; }
        if (v && /^(true|yes|checked|1)$/i.test(String(v)) && !el.checked) { el.click(); mark(el, true); filled++; }
        return;
      }
      if (v === undefined || v === null || v === "") { if (el.required && !el.value) { mark(el, false); left.push(questionFor(el).slice(0, 80)); } return; }
      if (el.tagName === "SELECT") {
        const opt = [...el.options].find(o => same(o.text, v)) || [...el.options].find(o => near(o.text, v) && o.value);
        if (opt) { setValue(el, opt.value); mark(el, true); filled++; } else { mark(el, false); left.push(questionFor(el).slice(0, 80)); }
        return;
      }
      if (el.value && el.value.trim()) return;  // never overwrite what's already there
      setValue(el, Array.isArray(v) ? v.join(", ") : String(v)); mark(el, true); filled++;
    });
    panel(filled, attached, left.concat(notes || []), jobTitle);
    return { filled, attached, left: left.length };
  }

  function panel(filled, attached, todo, jobTitle) {
    document.getElementById("flous-panel")?.remove();
    const p = document.createElement("div"); p.id = "flous-panel";
    p.style.cssText = "position:fixed;z-index:2147483647;right:16px;bottom:16px;width:340px;max-height:60vh;overflow:auto;background:#fff;color:#14181f;" +
      "border:2px solid #4f46e5;border-radius:14px;box-shadow:0 10px 40px rgba(0,0,0,.25);font:13.5px/1.45 system-ui,Segoe UI,Arial;padding:14px 16px";
    const esc = s => String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
    p.innerHTML = `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px"><b style="font-size:15px">⚡ Flous filled this page</b>
      <button id="flous-x" style="margin-left:auto;border:0;background:none;font-size:18px;cursor:pointer">✕</button></div>
      ${jobTitle ? `<div style="color:#555;margin-bottom:6px">For: ${esc(jobTitle)}</div>` : ""}
      <div>✅ <b>${filled}</b> answers filled · 📎 <b>${attached}</b> file${attached === 1 ? "" : "s"} attached</div>
      <div style="color:#555;margin:6px 0">Green = filled by Flous. Orange = needs you.</div>
      ${todo.length ? `<b>Check / do yourself:</b><ul style="margin:4px 0 0;padding-left:18px">${todo.slice(0, 10).map(t => `<li>${esc(t)}</li>`).join("")}</ul>` : ""}
      <div style="margin-top:10px;padding:8px;background:#eef0ff;border-radius:8px">👀 Read every answer, fix anything, then <b>you</b> click <b>Submit</b>.
      Multi-step form? Click the Flous button again on each page.</div>`;
    document.body.appendChild(p);
    p.querySelector("#flous-x").onclick = () => p.remove();
  }

  window.__flous = { scan, fill };
})();
