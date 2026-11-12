# Job Agent — free, fully automated

Every 4 hours, for free, on GitHub's servers (your PC can be off):

1. Collects new **remote & hybrid jobs, internships and fellowships** from Remotive, RemoteOK,
   Arbeitnow, Jobicy, Himalayas, Opportunity Desk and Opportunities Corners. You can add more RSS feeds.
2. Filters them by what you want (type, remote/hybrid, location, seniority, age).
3. Scores each one against **your CV**: a match score and an **ATS keyword score**, plus the keywords you have and the ones you're missing.
4. For the best ones, uses free AI (Gemini or Groq) to write:
   - a **tailored CV** (headline, summary, skills order, rewritten bullets, keywords you can truthfully add)
   - a **cover letter** for that posting (.docx)
   - **tips to strengthen that application** and the skills you're missing
5. Sends everything to **Telegram** with an **Apply** button. It never sends you the same posting twice.

## Setup (about 15 minutes, all free)

### 1. Telegram bot
1. In Telegram, message **@BotFather** → `/newbot` → pick a name → copy the **token**.
2. Open your new bot and press **Start** (send "hi").
3. On your PC: copy `.env.example` to `.env`, paste the token, then run:
   ```
   pip install -r requirements.txt
   python -m agent.main --chat-id
   ```
   Paste the number it prints as `TELEGRAM_CHAT_ID` in `.env`. Test it: `python -m agent.main --test-telegram`

### 2. Free AI key (for the cover letters and tailored CVs)
- Gemini: https://aistudio.google.com/apikey → "Create API key" (free tier, no card), and/or
- Groq: https://console.groq.com/keys (free tier, used as a backup)

Put it in `.env` as `GEMINI_API_KEY` / `GROQ_API_KEY`. Without a key, the agent still sends matches and ATS keywords, but it doesn't write anything.

### 3. Your CV + LinkedIn
- Put your CV in `cv/` as `cv.pdf` (or .docx/.txt/.md). **Delete the sample `cv/cv.md`.**
- LinkedIn: open your profile → **Resources → Save to PDF**, then add what's on it to your CV
  (or use that PDF as your CV) so the agent knows your whole profile.
- Edit `config.yaml`: your profile, interests, locations, and the titles to exclude.
- Try it: `python -m agent.main --dry-run` (prints the matches and sends nothing).

### 4. Make it run by itself (GitHub Actions, free)
1. Create a **private** GitHub repo and upload this folder. `.env` is git-ignored and never uploaded.
2. Repo → **Settings → Secrets and variables → Actions → New repository secret**. Add
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GEMINI_API_KEY` (and `GROQ_API_KEY` if you have one).
3. **Actions** tab → enable workflows → "job-agent" → **Run workflow** to test it.
   After that it runs every 4 hours. Change the `cron` line in `.github/workflows/job-agent.yml` to run more or less often.
   Each run takes about 2–4 minutes, which fits easily in the 2,000 free minutes a month that private repos get.

## 📋 Dashboard website
Every run also updates a private website: `https://<your-github-username>.github.io/job-agent/`
- All matches, sorted into 🤖 AI internships · 🎧 remote support/ops jobs · 🌍 paid fellowships
- Match score, ATS score, the keywords you have and the ones you're missing, and tips for each listing
- Cover letter (you can edit it) + tailored CV, which you can copy or download as Word files. ✨ writes them with AI for any listing
- Track each one: New → Saved → Applied → Interview → Offer / Rejected, plus notes
- 🚀 Apply copies the cover letter and opens the posting; then **⚡ Fill application** (a bookmark you set up in the
  "Autofill & profile" tab) fills in your name, email, phone, LinkedIn, GitHub and location on the form
- Password-protected: the page, your CV (`cv.enc`) and all listings are AES-encrypted, so the repo can be public
  (which makes GitHub Pages and Actions free) while only you can read them. The password is `DASHBOARD_PASSWORD` in `.env`.
- Changed your CV or `cv/applicant.yaml`? Run `python -m agent.secure lock`, then commit `cv.enc`.

## 📬 Gmail reply tracking
The agent reads (read-only) your inbox every run, finds replies to applications (confirmation, test, interview,
rejection, offer, request for documents), uses the free AI to sort them and link them to the right job, then
updates that job's status on the dashboard, lists them in the 📬 Inbox tab, and alerts you on Telegram.
Setup: Google Account → Security → 2-Step Verification (turn on) → App passwords → create one named "job agent",
then set `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` (in `.env` and as GitHub secrets).

## About LinkedIn and auto-apply
- The agent does **not** log into LinkedIn or scrape it. LinkedIn bans accounts that do that, and it has no free jobs API.
  Use your exported LinkedIn PDF as described above, and set LinkedIn's own **Job Alerts** to email you.
- It does **not** submit applications blindly. Each Telegram alert comes with the tailored CV, the cover letter and an
  **Apply** button. Applying takes about a minute and you check everything before it goes out. Auto-submitting gets
  flagged as spam by ATS systems and can send wrong answers to screening questions.

## Tuning
- Too many alerts → raise `min_score`, or add words to `exclude_title_words`.
- Too few → lower `min_score`, add `interests`, or add RSS feeds (most WordPress opportunity sites have `/feed/`).
- To see the full history again, reset `state/seen.json` to `{}`.

## Development

```bash
pip install -r requirements-dev.txt
ruff check .          # lint, incl. security rules
python -m pytest      # Python + JavaScript tests (needs Node for the JS part)
```

CI runs the same on every push; the scheduled agent also runs the tests before it touches any data. See [SECURITY.md](SECURITY.md) for the security model.
