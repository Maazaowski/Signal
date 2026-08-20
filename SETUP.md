# Signal — setup

Signal watches job boards and company career pages, scores what it finds against
your profile, and emails you a short daily list with an intro already written for
each role.

Almost everything is configured inside the app. This file covers the parts that
happen outside it: installing, starting it, and the two accounts you need.

Written for this machine: Windows, PowerShell, Python 3.12.

---

## 1 · Install

```powershell
python -m venv .venv
```

```powershell
.venv\Scripts\Activate.ps1
```

```powershell
pip install -r requirements.txt
```

> If PowerShell blocks the activate script, run
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.

---

## 2 · Start it

```powershell
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

That one command starts everything — the web app, the scheduler, and the
background worker that runs jobs. There is nothing else to launch. You should see:

```
Run worker started
Schedule updated - next run Fri 21 Aug 09:00 PKT
```

Open **http://127.0.0.1:8000**.

Everything from here happens in the browser. If something is not set up, the app
says so at the top of the page and points at where to fix it — it never shows a
healthy state while it is degraded.

---

## 3 · Two accounts to connect

Both are added in **Settings**, stored encrypted, and testable from the page
before you rely on them. Neither needs a file edit or a restart.

### JSearch, for LinkedIn and Indeed results — free

1. Sign up at **https://rapidapi.com**
2. Open **https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch**
3. Subscribe to **Basic** — $0/month, 200 requests
4. Copy the `X-RapidAPI-Key`
5. In Signal: **Settings → Integrations**, paste it, press **Test**

⚠️ Stay on Basic. Its 200-request limit is a hard stop, so you cannot be charged.
The paid tiers bill per request beyond the quota with no ceiling.

Without this Signal still works — it reads the free boards and every company
career page it can find, at no cost.

### Gmail, for the daily digest — free

Use a **dedicated throwaway Gmail** as the sender, not your main account. An app
password bypasses two-factor auth and grants IMAP as well as SMTP, so whatever
account you use here, assume anything that can read the app's data can also read
that mailbox.

1. On the throwaway account, turn on 2-Step Verification at
   **https://myaccount.google.com/security**
2. Create an app password at **https://myaccount.google.com/apppasswords**
3. In Signal: **Settings → Email delivery** — sender address, the 16-character
   app password, and where the digest should arrive
4. Press **Test** to confirm Gmail accepts it

---

## 4 · First run

Work through this in the browser:

1. **Companies → Add curated list** — loads a set of companies whose job boards
   can be read directly, at no cost to your search allowance.

2. **Companies → Find job boards** — ⚠️ **do not skip this.** Companies arrive
   paused because Signal does not yet know where they publish jobs. This checks
   each one for a Greenhouse, Lever or Ashby board and switches on the ones that
   have a readable board. Without it the company side collects nothing at all.

3. **Today → Find roles** — watch it run. You can navigate away or close the tab;
   the run continues on the server and any page picks it back up.

4. **Intros → Write intros**, then **Preview digest**, then **Send digest**.

5. **Settings → Your pitch** — the one thing only you can write. A one-line bio
   and two or three achievements, with numbers in them. Everything else has a
   sensible default.

After that it runs itself every morning.

---

## 5 · Everyday use

Open the daily email, or open **Today**. For each role: click a contact search,
copy the intro, send it, then mark it in **Intros**.

**Activity** shows what is running, what finished, what failed and why, with the
full log — you should never need to look at a terminal.

If a role is worth keeping regardless of what scores above it, open it in
**Roles** and use **Send in digest**. It moves to the top of the next email and
is exempt from the stale-role cleanup.

### Who to approach

Signal drafts the intro; picking the right person is still yours. Roughly:

| Company size | Usually the best target |
|---|---|
| Under 50 | Founder or CTO directly |
| 50–200 | Engineering Manager or Tech Lead |
| 200–1000 | Tech Lead, or a senior engineer on that team |
| Over 1000 | Technical recruiter — they are the ones actively looking |

Reference something specific, ask one clear question, and keep the connection
note under 300 characters, which is LinkedIn's limit. Weekday mornings in the
recipient's timezone do better than Friday evenings.

Follow up once after about three days. If a second week passes with no reply,
set it aside and spend the time on the next one.

---

## Settings worth knowing about

| Section | What it controls |
|---|---|
| **Schedule** | Run time and timezone. Changing either reschedules immediately. |
| **Email delivery** | Sender, app password, recipient, with a Test button. |
| **Integrations** | Search key and your monthly allowance. |
| **Data & crawling** | How long roles are kept, how hard company sites are hit. |
| **Appearance** | Theme, and the product name — rename it and the whole app follows. |
| **Where you can work** | The location rules, in the order they are applied. |
| **How it scores** | Weighting and seniority target, plus **Reapply scoring** for roles already collected. |

Changes take effect immediately. Nothing here needs a restart.

---

## Things worth knowing

**The morning run only happens if the machine is awake with Signal running.**
There is no catch-up for a missed day — open it and press **Find roles**.

**Never bind to `0.0.0.0`.** Signal has no login. On `127.0.0.1` that is fine;
exposed to a network it would let anyone trigger your email or delete your data.

**Your search allowance.** Each saved search costs one request per run. Four
searches running daily uses about 120 of the 200 free monthly requests. **Today**
shows what is left; **Settings → Saved searches** shows what your current set costs.

**Secrets are encrypted in the database.** The key sits in `.secret_key` beside
it, so this protects the database if it is copied, backed up, or picked up by a
cloud sync client — a real risk with this folder under `C:\Git`. It does not
protect against someone who already has access to this folder; that would need a
passphrase on every start, which is the wrong trade for something that must run
unattended at 9am.

**If you push this to GitHub**, `.env`, `*.db`, `.secret_key` and
`credentials.json` are all excluded. Point `origin` at your own repository first.

---

## If something breaks

Everything diagnostic is in **Activity**: service status, run history with the
reason for any failure, and a live application log.

If the app will not start at all, the terminal shows why. The most common cause
is the port still being held by an older copy.

To run the test suite:

```powershell
.venv\Scripts\python.exe -m pytest
```

It uses a throwaway database and stubbed network calls, so it never touches your
real data and never spends your search allowance.
