# Database

One SQLite file, `jobs.db`, in the repo root. Override the location with
`JOBS_DB_PATH` — the test suite does exactly that, which is what keeps a test
run from touching real data.

The schema lives in one place: `core/database.py::init_db()`. It runs on every
start and is idempotent. Migrations are additive `ALTER TABLE ... ADD COLUMN`
guarded by a `try/except`, so an older database upgrades in place.

The connection opens with `PRAGMA journal_mode=WAL`, which matters for backups —
see below.

---

## Tables

| Table | Holds |
|---|---|
| `jobs` | Every collected role: title, company, location, description, URL, source, score, status, location fit, and the digest mark |
| `companies` | The company registry crawled directly: domain, careers URL, detected ATS platform and slug, crawl status |
| `outreach` | One row per generated intro: the job it belongs to, contact details, the short and long messages, and its stage |
| `email_log` | Digest send history — when, to whom, how many items, and any error |
| `api_usage` | One row per outbound paid API call. This is what the JSearch quota gauge counts |
| `search_queries` | Legacy query table, still seeded. The live queries come from the active profile |
| `profiles` | Targeting configurations as JSON blobs; exactly one is active |
| `runs` | One row per background run: kind, status, trigger, progress, stats, failure reason |
| `run_logs` | Per-run log lines, so a run's output survives the process that produced it |
| `app_settings` | Runtime configuration, the active profile id, and the one-time bootstrap marker |

`runs`, `run_logs` and `app_settings` came with the run engine and the settings
store. Anything describing this schema without them predates that work.

### Notable columns

- **`jobs.location_fit`** — `yes` / `maybe` / `no`: can you actually take this
  role, judged against your profile's `location` section. The UI says "open to
  you". Was called `india_friendly` before the tool stopped assuming a country;
  `init_db()` renames the column in place on first start after upgrading, and
  the rename is idempotent.
- **`jobs.mark_for_email`** — set from **Roles → Send in digest**. Marked roles
  sort above score order in the next digest and are exempt from stale cleanup.
- **`jobs.last_seen`** — refreshed every time a role is seen again. Retention
  works off this, not `discovered_at`.
- **`companies.crawl_status`** — seeded companies arrive `paused` with
  `ats_platform='unknown'`. They stay inert until `core/ats_detect.py` finds a
  crawlable board, which is what **Companies → Find job boards** runs.

---

## Encryption

Two settings are stored encrypted, both in `app_settings`: `sender_password` and
`rapidapi_key`. Encryption is Fernet, via `core/crypto.py`, and ciphertext is
tagged `enc:v1:` so plaintext rows from an older database migrate cleanly.

**What this protects is the database file.** `jobs.db` is the artefact most
likely to escape — copied for debugging, swept into a backup, or picked up by a
cloud sync client watching the folder. Encrypting those two values means a stray
copy is not a credential leak.

**What it does not protect** is anyone who can already read the project
directory, because the key sits in `.secret_key` right beside the database.
Defending against that would mean typing a passphrase on every start, which is
the wrong trade for a tool that must run unattended at 9am. It is worth doing
and worth describing accurately. It is not a vault.

The API never returns either value. `settings_store.public()` returns
`{configured: bool, hint: "••••abcd"}`, and a test asserts no endpoint leaks
plaintext.

---

## Backups

Two things make a naive `cp jobs.db backup.db` wrong.

**1. Back up `.secret_key` with it.** Without that file the encrypted settings
in the copy cannot be decrypted, and you will not find out until you restore.
`.secret_key` is gitignored, so it is never in the repo — it exists only on this
machine.

**2. Copy with the app stopped, or use SQLite's own backup.** WAL mode means
recent writes may still be in `jobs.db-wal` rather than `jobs.db`. Copying the
main file alone while the server runs can capture a torn state.

Either stop the server and copy both files:

```bash
cp jobs.db ~/backups/jobs-$(date +%Y%m%d).db
cp .secret_key ~/backups/secret_key-$(date +%Y%m%d)
```

Or take a consistent snapshot with the app running:

```bash
sqlite3 jobs.db ".backup 'backup.db'"
```

That still needs `.secret_key` copied alongside it.

---

## Retention

Nothing is a hardcoded constant; both are settings.

- **`stale_job_days`** (default 14) — roles not seen again for this long are
  deleted. Roles you marked applied, or added to the digest, are always kept.
- **`run_retention`** (default 200) — how many past runs to keep, with their
  logs.

---

## Inspecting it

```bash
sqlite3 jobs.db ".tables"
```

```bash
sqlite3 jobs.db "SELECT status, COUNT(*) FROM jobs GROUP BY status;"
```

The app's own **Activity** page covers run history and logs without dropping to
SQL, and **Settings** covers everything in `app_settings`.
