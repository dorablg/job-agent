# Security model

This repository and the dashboard website are **public**. Everything personal is protected by encryption, not by hiding files.

| What | How it is protected |
|---|---|
| CV, profile, listings, cover letters, email replies | AES-256-GCM, key from `DASHBOARD_PASSWORD` via PBKDF2-SHA256 (600,000 rounds). A fresh random IV per encryption. |
| API keys (Gemini, Apps Script) | Only inside the encrypted dashboard data, or GitHub Actions secrets (masked in logs). Never committed. |
| "Keep me signed in" | The browser and the extension store a **non-extractable** derived key in IndexedDB, never the password. Lock (🔒) deletes it. |
| Dashboard page | Strict Content-Security-Policy: only the page's own script (pinned by SHA-256) may run; data can only be sent to Gemini and your own Apps Script. No inline handlers, no third-party scripts, `no-referrer`. |
| Links from scraped sites / AI / email | Only `http(s)` links become clickable (blocks `javascript:` and similar). All text is HTML-escaped. |
| Browser extension | Only your dashboard page may ask it to open + fill a job page (checked by sender URL and origin), only for `http(s)` URLs. Fill / settings commands are accepted only from the extension's own pages. It never clicks Submit. |
| Google Sheet database (Apps Script) | Shared secret compared in constant time; input size limits; cell values that start with `= + - @` are stored as text (no formula injection). Read-only on Gmail. |
| CV archive | Extracted with path checks (no `..`, absolute paths or sub-folders). |
| Supply chain | GitHub Actions pinned to commit SHAs, dependency ranges capped, Dependabot weekly, `pip-audit` + `ruff` security rules + tests in CI; the agent runs its test suite before touching any data. |

**Your responsibilities:** use a long, unique `DASHBOARD_PASSWORD` (the encrypted page can be downloaded and attacked offline, so length matters most). In Google AI Studio you can restrict the Gemini key to the Generative Language API. If you ever think the password leaked: change the `DASHBOARD_PASSWORD` secret and run the workflow (everything is re-encrypted), then sign in again.

Report a problem: open a private security advisory on the repository.
