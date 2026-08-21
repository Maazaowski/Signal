# How Signal got here

A record of the rewrite, kept because several decisions look arbitrary without
the reason behind them. Chronological. Written August 2026.

For working rules rather than history, read `CLAUDE.md`.

---

## Where it started

The repo was cloned from another developer's job-scraper. It worked, but it was
built for a different person and a different country, and it carried their
identity: their name and employer in the outreach templates, their Gmail as the
hardcoded fallback recipient, their resume committed as a PDF, and a
location-scoring layer wired specifically for India.

The new owner is a Karachi-based senior backend engineer. Everything below
follows from adapting the tool to that, and from what surfaced along the way.

---

## 1 — Security review

Reviewed before use rather than after. Findings, in the order they mattered:

- **Stored XSS.** Job descriptions arrive as raw HTML from public boards and
  were injected into the dashboard unsanitised, on the same origin as an API
  with no authentication. Fixed, then fixed again when the first fix turned out
  to route the payload through a helper that also executed it (see below).
- **No cross-origin protection.** Many state-changing endpoints took query
  params with no body, making them "simple requests" any website could fire —
  including one that mass-deletes the jobs table. A `Sec-Fetch-Site` middleware
  now refuses those while leaving curl and Postman working.
- **Quote-unsafe escaping.** Two of the three copies of `escapeHtml` used a
  `textContent → innerHTML` round-trip, which does not escape quotes, so feed
  values could break out of `href=""`.
- **Deliberately skipped:** SSRF validation and a path-traversal guard. Both are
  self-attacks on a loopback single-user tool.

The cost review at the same time found the JSearch free tier (200 requests a
month) was being consumed at ~186 with the shipped six queries — no headroom for
a single manual run. Trimmed to four.

## 2 — Localisation

Timezone, cities and search queries moved to Pakistan. The blocker was that
`check_india_friendly()` read some lists from the profile but hardcoded the
Indian cities and region lists, so a Pakistan profile could not work by
configuration alone. Made fully profile-driven, with fallbacks so the shipped
presets behave identically.

Two subtleties, both from real false positives, are documented in `CLAUDE.md`:
`"pst"` means Pacific in job posts, and a concrete foreign city in the location
field must outrank "we're a global company" in the description.

## 3 — The run engine

`POST /api/collect` awaited the whole collection inline: the request blocked for
one to two minutes and closing the tab lost all visibility. Every `log()` call
went to stdout and nowhere the UI could reach.

Replaced with a queue and a single worker. Runs get a database row, live
progress, persisted logs, and a recorded failure reason. Only one executes at a
time, which doubles as the fix for double-click quota burn.

Two bugs found while building it: synchronous handlers (`seed`, `rescore`)
blocked the event loop so progress could not be polled, and ATS detection
reported 0% until it finished.

**The scheduler bug** surfaced here and was the most consequential of the whole
project: `if SENDER_EMAIL:` wrapped `scheduler.start()`, so an unconfigured
sender silently disabled the daily *collection* as well as the email. The app
looked healthy and did nothing.

## 4 — The inert company list

The single largest functional find. `get_all_mega_companies()` seeds every
company with `ats_platform="unknown"` and `crawl_status="paused"`, commented
*"paused until ATS detected"* — but nothing ever performed that detection for
seeded companies. `batch_detect_ats` existed and was only ever applied to newly
*discovered* companies.

So the company-crawl track — half the product — had never collected anything.
Every crawl logged "No active companies to crawl."

`core/ats_detect.py` closes the loop. On the real database, 70 of 210 companies
turned out to have a crawlable board, and the first crawl pulled 1,217 listings.

## 5 — UI rewrite

The first rebuilt interface worked but read as generated: Unicode glyphs for
navigation, the default indigo accent, and every page assembled from the same
"KPI row → card → table" recipe regardless of purpose.

Rebuilt as **Signal** — the name describes what the scorer does, separating a
few real matches from thousands of listings. Warm ink-and-paper palette, system
serif for display type, a hand-drawn SVG icon sprite, and layouts that follow
each page's job: Today is a briefing, Roles a reading list, Activity a timeline.

Pages and vocabulary were renamed with it (jobs → roles, outreach → intros,
automation → activity). Old URLs redirect.

## 6 — Runtime configuration

Requirement: no setting should need a file edit or a restart.

The blocker was architectural. `config/settings.py` resolved `os.getenv()` into
module constants at import, and five modules took *value* imports of them;
`JSearchSource` copied the key again into `self.api_key`. Nothing written at
runtime could reach those bindings.

Replaced with `core/settings_store.py` — a typed schema over the existing
`app_settings` table, read at point of use, with `on_change` hooks. Changing the
schedule now reschedules the live cron job. The timezone became changeable at
all by moving it from the scheduler onto the `CronTrigger`.

Secrets moved in too, encrypted with Fernet. This protects the *database file*,
which is what ends up in backups and cloud-synced folders — not the directory,
since the key lives beside it. `config/settings.py` shrank from 151 lines to 39.

## 7 — Tests

69 browser-driven Playwright tests. They cover behaviour rather than units: a
run survives a hard refresh, a hostile description renders inert, a duplicate
run is refused, the scheduler starts without email configured, changing the
timezone reschedules the live job.

Early runs were flaky and the causes were real rather than cosmetic — the state
reset wiped the runs table while the worker was still executing, tables
re-rendered under a click, and a test clicked a button before its handler was
attached. That last one was a genuine UI defect, fixed by disabling action
buttons until wired.

## 8 — Cleanup

Split `main.py` (1,072 lines of routing plus business logic) into eleven routers
under `api/`; it is now app assembly only. Removed unreferenced functions and
unused dependencies, added `ruff` and `pip-audit` to CI.

`pip-audit` found 17 vulnerabilities that an earlier "upgraded, CVEs fixed"
claim had missed — the fix required pinning `starlette` explicitly, because
FastAPI only requires `>=0.46` and pip leaves a vulnerable transitive version in
place on upgrade.

## 9 — Dropping the country assumption

The tool had been built for one person in one place, then adapted for another,
and it showed. India was not a setting, it was an assumption baked into four
separate layers: a curated company list that was two-thirds Indian employers, a
scorer that fell back to Indian cities as "home" and treated the US, UK and
Europe as closed, profile keys literally called `india_positive` and
`india_negative`, and a `india_friendly` column carrying the verdict.

The goal became: anyone, anywhere, configures their own country.

The company list lost its 98 Indian-HQ entries and the "India engineering
centre" framing on 58 multinationals, leaving employers that are relevant
regardless of where you are. Seeded companies no longer claim `yes` for
location; that is a judgement only a configured profile can make.

The scorer's fallbacks are now **empty** rather than Indian. That is the part
worth understanding: the obvious fix is to swap one country for another, or to
keep a list "so it works out of the box". Both are wrong. A wrong home country
marks roles you cannot take as open to you, which costs real effort, so
unconfigured the scorer only recognises genuinely worldwide postings and calls
everything else `maybe`.

`india_friendly` finally became `location_fit`, reversing the decision recorded
below. What made it worth doing was not tidiness — it was that the name had gone
from untidy to misleading. `init_db()` renames the column in place, idempotently,
so existing databases keep their scores.

The default timezone moved from `Asia/Karachi` to `UTC`, the timezone picker
grew from 11 zones to cover every region, and the search country became a
setting instead of a hardcoded `"IN"` in eight places.

---

## Discarded ideas

- **React/Vite frontend.** A build step would break "one command starts
  everything."
- **Renaming `india_friendly`.** Skipped at the time: the internal name was
  wrong, but changing it needed a schema migration and touched every endpoint
  for no functional gain. **Later reversed** — see section 9, where the tool
  stopped assuming a country and the name became actively misleading rather
  than merely untidy.
- **Auto-start on Windows login.** Offered, not chosen.
- **A vault for secrets.** Rejected as dishonest framing — a passphrase on every
  start is wrong for a tool that must run unattended at 9am, so the threat model
  is stated plainly instead.
