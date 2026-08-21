# Working on Signal

Read this before changing anything. Most of it is knowledge that cost real
debugging to acquire and is not obvious from the code.

## What this is

A single-user job-hunting tool. It collects roles from public job boards and
company job boards overnight, scores them against a configurable profile,
drafts a LinkedIn intro for the best ones, and emails a shortlist each morning.

Python + FastAPI + SQLite + APScheduler. Server-rendered pages, vanilla JS, no
build step. One process runs everything.

**Origin:** forked from another developer's repo and substantially rewritten.
The owner is a Karachi-based senior backend engineer targeting Python roles that
are open to Pakistan or genuinely worldwide-remote. That context is encoded in
`profiles/backend_python_pk_senior.yaml`, which is also the first-run default.

The repo is public. That preset's **`outreach` block ships with placeholders** —
the owner's real name, bio, achievements and recipient address live in the
database, which is gitignored, seeded once by `ensure_first_run_seed()`. **Do not
refill the file from the live profile.** A non-empty `recipient_email` there
outranks the value in Settings, so a real address left in the preset silently
misdirects a stranger's digest. The targeting sections are the point of the file
and should stay as they are.

## Run it

```bash
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

That one command starts the API, the scheduler and the background worker.
There is nothing else to launch.

The checks. None of these tools are in `requirements.txt` — install them with
`pip install -r requirements-dev.txt`, then `playwright install chromium`.

```bash
.venv\Scripts\python.exe -m pytest tests/     # 73 browser-driven tests, ~90s
.venv\Scripts\python.exe -m ruff check .      # must stay clean
.venv\Scripts\python.exe -m pip_audit         # must stay clean
```

`.github/workflows/ci.yml` runs all three on every push and pull request against
Python 3.11 and 3.12, and weekly so `pip-audit` catches new advisories against
the pinned dependency set.

## Invariants — do not break these

**Tests must never spend API quota or touch real data.** `tests/conftest.py`
forces `RAPIDAPI_KEY=""`, points `JOBS_DB_PATH` at a temp file, and stubs every
outbound source including ATS detection. JSearch's free tier is 200 requests a
month; a careless test run is a meaningful chunk of it.

**Never bind `0.0.0.0`.** There is no authentication. `config/settings.py`
defaults to `127.0.0.1` deliberately.

**Secrets never leave the server.** `settings_store.public()` returns
`{configured: bool, hint: "••••abcd"}`, never plaintext. A test asserts no
endpoint leaks them.

**One run at a time.** A second start returns 409. This is what stops a
double-click from spending the API allowance twice.

**`.secret_key` is gitignored and must be backed up.** Without it the encrypted
settings in the database cannot be decrypted.

## Bugs that were fixed here — do not reintroduce them

These are the traps. Each one shipped broken and was found the hard way.

| Trap | What went wrong | The rule now |
|---|---|---|
| **Scheduler gating** | `if SENDER_EMAIL:` wrapped `scheduler.start()`, so a missing sender silently disabled the *daily collection*, not just the email. The app looked fine and did nothing. | The scheduler starts unconditionally. Email is gated **inside** `run_daily_pipeline`. There is a regression test. |
| **Inert companies** | Seeded companies arrive with `ats_platform="unknown"` and `crawl_status="paused"`. Nothing ever detected their board, so the crawler logged "no active companies" forever and half the product did nothing. | `core/ats_detect.py` closes the loop. The Companies page states the gap and names the fix. |
| **Frozen config** | `from config.settings import RAPIDAPI_KEY` captured a value at import; `JSearchSource` copied it again into `self.api_key`. Nothing written at runtime could reach it. | Always `settings.get("key")` **at the point of use**. Never assign a setting to a module constant or instance attribute. |
| **Timezone unchangeable** | `AsyncIOScheduler` fixes its timezone at construction. | The scheduler runs in UTC; the timezone goes on the `CronTrigger`. `apply_schedule()` rebuilds the job on change. |
| **`stripHtml` executed payloads** | Assigning to `.innerHTML`, even on a detached node, starts image loads and fires `<img onerror>`. | Use `DOMParser` — its document is inert. Verified by test. |
| **`escapeHtml` missed quotes** | A `textContent → innerHTML` round-trip escapes `& < >` but not `"`, so feed values broke out of `href=""`. | The regex version in `static/js/core.js`. Also `safeUrl()` for any URL reaching an href. |
| **Blocking the event loop** | `seed` and `rescore` are synchronous loops. Run directly they froze the server, so progress could not be polled. | Sync handlers go through `asyncio.to_thread` in `core/runs.py`. |
| **Click before wired** | Buttons were clickable from first paint but handlers attach on `DOMContentLoaded`. Clicks vanished. | Action buttons carry `disabled data-wire` in markup; `wired()` enables them at the end of each page's init. |
| **Blank background tab** | `poll()` skipped while `document.hidden`, so a page opened in a background tab never loaded data. | The **first** tick always runs; only repeats pause. |
| **Route shadowing** | `/api/jobs/marked` lived in its own router mounted *after* the one owning `/api/jobs/{job_id}`. FastAPI matches in registration order, so "marked" was read as a job id: the endpoint answered `200 {"error": "Job not found"}` and the marked list was unreachable. Nothing failed loudly. | A literal path goes **above** the `{param}` route that would swallow it, **in the same file** — see the marked-roles endpoints in `api/roles.py`. Do not rely on the mount order in `main.py`. A test walks `app.routes` and fails on any shadowed literal. |

## Scoring — the subtle parts

`core/scorer.py::check_location_fit` decides whether a role is open to the user.
It stores into `jobs.location_fit`; the UI calls it **"open to you"**.

**Nothing here knows a country.** Every term comes from the active profile's
`location` section, set in Settings → Where you can work. The fallbacks in
`scorer.py` for home terms, regions and excluded regions are all deliberately
**empty**: unconfigured, only genuinely worldwide postings score `yes` and
everything tied to a place scores `maybe`. Do not put a country in them. A wrong
home country marks roles the user cannot take as open, which is the one error
that wastes real effort.

Order matters, and each rule exists because of a real false positive:

1. Hard blockers (`blocking_terms`, e.g. `"us only"`) win over everything.
2. Home terms → **yes**.
3. **A concrete foreign city in the *location field* → no**, before any
   description check. Without this, "we are a global company" boilerplate in a
   London-only posting scored it as open.
4. Global terms → yes. **`"global"` and `"fully remote"` are deliberately absent** —
   both appear in ordinary marketing copy.
5. Region terms → yes.
6. A bare city with no remote wording is onsite → no.

Whether a country restriction is a *blocker* depends on where the user is:
`"us only"` rules the role out for most people and rules it in for someone in
Texas. That is why `blocking_terms` ships empty in the generic presets.

**`"pst"` must never be a compatible timezone.** In job posts it means Pacific
Standard Time, not Pakistan Standard Time.

## Where things live

```
main.py          app assembly only — lifespan, scheduler, middleware. No routes.
api/             one router per concern; deps.py holds shared helpers
core/            domain logic
  settings_store.py   runtime config, single source of truth
  runs.py             background run engine (queue + single worker)
  runlog.py           shared log seam: stdout + ring buffer + run_logs table
  scorer.py           relevance and location fit
  ats_detect.py       finds which companies have a crawlable board
  crypto.py           Fernet encryption for stored secrets
sources/         one adapter per job board behind sources/base.py
templates/       base.html is the shell; _icons.html is the SVG sprite
static/css/      tokens → base → components. Never a raw colour at a call site.
static/js/       core.js is shared; one module per page
profiles/        YAML presets; the first-run profile is seeded from one
```

**Adding a setting:** add one row to `SCHEMA` in `core/settings_store.py`. The
Settings UI builds itself from that schema — there is no second place to edit.
Add an `on_change` hook if it needs to take effect live.

**Adding a background job:** add a handler in `core/runs.py::_load_default_handlers`
and a label in `RUN_KINDS`. Wrap it in `asyncio.to_thread` if it is synchronous.

## Conventions

- Config is read at point of use, never captured. This is load-bearing.
- Copy is plain and factual. No exclamation marks, no emoji in the UI.
- Icons are SVG `<use>` from the sprite. **No Unicode glyphs** — a test enforces this.
- Every list needs four states: loading, empty, error, degraded. Empty states
  name the action that fixes them.
- Terminology: roles (not jobs), intros (not outreach), activity (not automation),
  "open to you" (not location fit) in user-facing copy.

## The documentation

All of it is current. There is no stale set any more — the seven pre-rewrite
files under `docs/` were deleted rather than patched, because each was between
10% and 70% accurate and several taught bugs listed in the table above.

```
README.md                        what it is, how it fits together
SETUP.md                         install, first run, day-to-day use
CLAUDE.md                        this file — conventions, invariants, traps
docs/00-history.md               why the code looks like this
docs/01-profiles-and-sources.md  profile YAML, adding a job source
docs/02-database.md              schema, encryption, backups
```

**Do not write an API reference.** FastAPI serves one at `/docs` from the code,
covering all 66 paths, and it cannot drift. A checked-in Postman collection was
deleted for the same reason; import `/openapi.json` instead.

## Things not worth doing

Considered and deliberately skipped, with reasons:

- **SSRF validation on `careers_url`** and the path-traversal guard in preset
  import. Both are self-attacks on a localhost single-user tool.
- **Re-adding a default home country.** The scorer's location fallbacks are
  empty on purpose. Filling them in "so it works out of the box" reintroduces
  exactly the coupling that made this a one-country tool.
- **Auth.** Out of scope for a tool bound to loopback; if it is ever exposed,
  that decision changes and auth becomes mandatory, not optional. A public
  *repository* is not a public *deployment* — `127.0.0.1` still holds.
- **A checked-in API reference or Postman collection.** `/docs` and
  `/openapi.json` are generated from the code. Both previous copies rotted.
- **`pytest-timeout`.** A dead `timeout = 120` sat in `pytest.ini` for exactly
  as long as nobody read the warning. `--strict-config` now makes an unknown key
  an error; `timeout-minutes` in CI is the real backstop.
- **A Windows leg in CI.** There is no platform-specific code. It would double
  the run to guard a risk that has not appeared.
