"""Infrastructure configuration only.

Everything a person would reasonably want to change — the schedule, the
timezone, API keys, mail credentials, retention, crawl behaviour — now lives in
the database and is edited in Settings. See core/settings_store.py.

What remains here is deployment-level: where the database file is, and what
address the server binds to. Both must be known before the database can be
opened, so they cannot themselves live in the database.

The search/scoring defaults that used to fill this file were a worse copy of
what profiles/*.yaml already contains; the first-run profile is now seeded from
a preset instead. See core.profile._default_profile.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# ── Storage ────────────────────────────────────────────────────
# JOBS_DB_PATH lets the test suite point at a throwaway file so it never touches
# the real jobs.db. Unset in normal use.
DB_PATH = os.getenv("JOBS_DB_PATH") or os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "jobs.db"
)

# ── Server ─────────────────────────────────────────────────────
# Localhost only. This app has no authentication; do not bind 0.0.0.0.
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# ── Legacy ─────────────────────────────────────────────────────
# The timezone used to be hardcoded here, which is precisely why it could not be
# changed without editing code. It is a real setting now; this constant survives
# only so settings_store.bootstrap_from_env() can carry an existing install's
# value across on the first run after the switch.
LEGACY_TIMEZONE = "Asia/Karachi"
