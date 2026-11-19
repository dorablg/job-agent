# Flous — a free, automated career agent

Flous finds jobs, paid internships, contracts, alternance, study-and-work programmes, fellowships and tech events that
match **your CV**. It checks each one with AI, writes a tailored ATS CV, cover letter and answers, applies for you
where it's safe, reads the replies in your Gmail, and reminds you of every deadline. It runs **for free** on GitHub
(your computer can be off). Everything personal is **encrypted**.

```
 every ~3 h on GitHub Actions                                   you
 ┌───────────────────────────────────────────────────────┐   ┌─────────────────────────────────┐
 │ 13 sources ─► filters ─► CV match + ATS score         │   │ 🌐 encrypted website / phone app │
 │   ─► AI check (realistic chance, visa, fit)            │──►│ 💬 Telegram alerts + reminders   │
 │   ─► AI apply kit (ATS CV, letter, answers)            │   │ ⚡ browser extension = agents    │
 │ Gmail replies ─► statuses, tasks, morning reminders    │   │ 📗 Google Sheet of applications  │
 └───────────────────────────────────────────────────────┘   └─────────────────────────────────┘
```

## What it does

| | |
|---|---|
| 🔎 **Finds** | ~6,000–8,000 postings per run from 13 sources: company career boards (Greenhouse, Lever, Ashby), Workable, Adzuna (10 countries), jobs.ac.uk, Alignerr AI-training contracts, Remotive, RemoteOK, Jobicy, Himalayas, opportunity sites (full posts, real deadlines), Devpost hackathons, Google Developer Groups events, RSS feeds and a hand-researched list of programmes. |
| 🎯 **Filters** | Your target roles and places, max years of experience, languages you don't speak, remote jobs open to your country, no front-office / call-centre roles, no unpaid internships, no expired deadlines, one listing per role per company. |
| 🤖 **Checks with AI** | Each new posting gets a realistic chance (0–100), visa status and a one-line reason; irrelevant ones are dropped. |
| ✍️ **Writes** | A full ATS CV (study mentions follow your rules: hidden for jobs, shown for internships and programmes), a cover letter, screening answers and tips. |
| 💬 **Alerts** | Telegram cards with the match, chance, missing keywords, tips and the CV/letter files. |
| 🌐 **Website & phone app** | Swipe, Discover (grouped categories, filters, search), Applications (Overview analytics, searchable Database, Board, Emails) and Profile. Installable on your phone ("Add to Home screen"). |
| ⚡ **Agents** | Swipe right to queue jobs, then press **Let agents apply**. The browser extension opens each job, clicks Apply, writes tailored answers, fills the form, attaches your CV and letter, and **submits only on standard forms when everything is answered**. Everything else is left filled for you to check. |
| 📬 **Gmail** | Reads replies (read-only), sorts them (confirmation, test, interview, rejection, offer or acceptance, request), updates each application and extracts dated tasks. |
| ⏰ **Reminders** | One Telegram message each morning: what's due today, in the next 3 days and this week, including weekly tasks. Nothing on empty days. |
| 📗 **Database** | Your applications are mirrored to a Google Sheet in your Drive, shared across devices, with CSV export. |

## Setup (about 30 minutes, all free)

1. **Fork or copy this repository** and keep it **public**: GitHub Pages and Actions are free for public repos.
   Your data stays private because everything personal is encrypted.
2. **Telegram:** message **@BotFather** → `/newbot` → copy the token → open your bot and press Start.
   Locally: copy `.env.example` to `.env`, add the token, then run `python -m agent.main --chat-id` to get your chat id.
3. **Free AI key:** https://aistudio.google.com/apikey (Gemini). Groq is an optional backup.
4. **Your CV:** put it in `cv/` (PDF, DOCX, MD or TXT), plus `cv/applicant.yaml` (the details forms ask for) and
   optionally `cv/profile.txt`. Then encrypt it: `python -m agent.secure lock`, and commit `cv.enc`.
   The `cv/` folder itself is never committed.
5. **Your targets:** edit `config.yaml`: `focus_places`, `categories` (titles per fit level), filters,
   `max_per_company`, sources and the curated programmes.
6. **GitHub secrets** (Settings → Secrets and variables → Actions):
   `DASHBOARD_PASSWORD` (long and unique), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GEMINI_API_KEY`,
   and optionally `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` (free at developer.adzuna.com) and the Gmail ones below.
7. **GitHub Pages:** Settings → Pages → Source: **GitHub Actions**. Then Actions → *job-agent* → **Run workflow**.
   Your board is at `https://<user>.github.io/<repo>/`.

### Gmail + Google Sheet (optional, recommended)
1. Copy `agent/gmail_bridge_template.gs` and replace `__KEY__` with a long random secret.
2. Open https://script.google.com → New project → paste it → Save → **Run** once and allow access
   (read-only Gmail and one Google Sheet; "Advanced → Go to project" on the unverified-app screen, since it's your own script).
3. **Deploy → New deployment → Web app**, with *Execute as: Me* and *Who has access: Anyone*. Without the
   secret key it answers "forbidden".
4. Add secrets `GMAIL_WEBAPP_URL` (the web-app link) and `GMAIL_WEBAPP_KEY` (your secret).

### Browser extension (the agents)
See [extension/README.md](extension/README.md). Load it unpacked in Chrome or Opera, then enter your dashboard password once.

## How it runs
- `.github/workflows/job-agent.yml` knocks every 30 minutes. A small **gate** job lets a real run through only
  ~3 hours after the last one, because GitHub drops many scheduled runs when it's busy.
- Each run first runs **the test suite**: a broken change never touches your data or sends alerts.
- Sources are fetched **in parallel** with a deadline each (a slow site is skipped, never blocks the run).
- State (`state/`) is committed back: what you've already been sent, encrypted listings and replies,
  reminders and the run time.

| Command | |
|---|---|
| `python -m agent.main` | a full run (what GitHub runs) |
| `python -m agent.main --dry-run` | print matches, send nothing, change nothing |
| `python -m agent.main --test-telegram` | send a test message |
| `python -m agent.reminders` | preview the next week of morning reminders |
| `python -m agent.secure lock` / `unlock` | encrypt / decrypt your `cv/` folder |

## Rules the agents follow
- Only **your dashboard** can start them, and they only open normal web pages.
- They submit only on standard applicant-tracking forms (Greenhouse, Lever, Ashby, Workable, SmartRecruiters,
  Teamtailor, Recruitee), only when **every** required field is filled and the CV is attached, with **no CAPTCHA**,
  and at most **25 a day**.
- They tick "I have read the privacy notice" boxes only. Never marketing, talent-pool or "I certify" boxes.
- **Never on LinkedIn, Indeed or Glassdoor** (their rules ban bots).
- Answers come from your real CV. Nothing is invented, and visa questions are answered truthfully.

## Security
Public repo, private data: AES-256-GCM with PBKDF2 (600k rounds), a strict Content-Security-Policy on the website,
no password stored in the browser or the extension (a non-extractable key instead), only http(s) links, formula-safe
Google Sheet, pinned GitHub Actions, Dependabot and `pip-audit`. Details in [SECURITY.md](SECURITY.md).

## Development

```bash
pip install -r requirements-dev.txt
ruff check .          # lint, incl. security rules
python -m pytest      # ~100 Python + JavaScript tests (Node needed for the JS part)
```

| Path | |
|---|---|
| `agent/sources.py` | the 13 sources, parallel fetching with deadlines |
| `agent/match.py` | filters, categories, CV match + ATS keyword score |
| `agent/screen.py` | AI screening (chance, visa, fit) |
| `agent/tailor.py` | AI apply kits (ATS CV, cover letter, answers) and the study rules |
| `agent/gmail.py` · `agent/reminders.py` | email replies → statuses and tasks → morning digest |
| `agent/dashboard.py` · `dashboard_template.html` | the encrypted website (built every run) |
| `agent/main.py` | the run: fetch → score → screen → alert → website → Gmail → reminders |
| `extension/` | the browser extension (agents, autofill, PDF CV) |
| `tests/` | the test suite (also run by CI on every push) |
