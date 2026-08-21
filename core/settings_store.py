"""Runtime configuration — one source of truth, changeable without a restart.

Why this exists: `config/settings.py` resolved `os.getenv()` into module
constants at import time, and consumers took *value* imports of them
(`from config.settings import RAPIDAPI_KEY`). `JSearchSource` copied it again
into `self.api_key`. Nothing written at runtime could ever reach those bindings,
so every configuration change required editing a file and restarting the process.

Settings now live in the `app_settings` table and are read through `get()` at the
point of use. Changing one persists it, invalidates the cache, and fires an
optional `on_change` hook — which is how changing the schedule reschedules the
running cron job rather than waiting for a restart.

Adding a setting means adding one row to SCHEMA below. The UI builds itself from
that schema, so there is no second place to update.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.crypto import decrypt, encrypt, mask
from core.database import get_connection

_LOCK = threading.Lock()
_cache: dict[str, Any] = {}
_loaded = False

# Hooks are registered by main.py at startup rather than imported here, so this
# module stays free of app/scheduler dependencies.
_HOOKS: dict[str, Callable[[Any], None]] = {}


def register_hook(key: str, fn: Callable[[Any], None]) -> None:
    _HOOKS[key] = fn


@dataclass
class Setting:
    key: str
    type: str                       # str | int | bool | choice
    default: Any
    group: str
    label: str
    help: str = ""
    secret: bool = False
    choices: list | None = None
    minimum: int | None = None
    maximum: int | None = None
    env: str | None = None       # legacy .env name, for the one-time import
    restart_note: str = ""          # set only if genuinely not live-changeable


def _s(**kw) -> Setting:
    return Setting(**kw)


# Common IANA zones, offered as a picker rather than a free-text field so a typo
# cannot silently stop the scheduler.
TIMEZONES = [
    "UTC",
    "Africa/Cairo", "Africa/Johannesburg", "Africa/Lagos", "Africa/Nairobi",
    "America/Argentina/Buenos_Aires", "America/Bogota", "America/Chicago",
    "America/Denver", "America/Los_Angeles", "America/Mexico_City",
    "America/New_York", "America/Sao_Paulo", "America/Toronto",
    "Asia/Dhaka", "Asia/Dubai", "Asia/Hong_Kong", "Asia/Jakarta",
    "Asia/Karachi", "Asia/Kolkata", "Asia/Manila", "Asia/Riyadh",
    "Asia/Seoul", "Asia/Shanghai", "Asia/Singapore", "Asia/Tokyo",
    "Australia/Melbourne", "Australia/Sydney",
    "Europe/Amsterdam", "Europe/Berlin", "Europe/Dublin", "Europe/Istanbul",
    "Europe/Lisbon", "Europe/London", "Europe/Madrid", "Europe/Paris",
    "Europe/Warsaw", "Pacific/Auckland",
]

# ISO 3166-1 alpha-2, which is what JSearch expects. Offered as a picker so a
# typo cannot silently return nothing. Alphabetical by name; the Settings page
# renders its saved-search dropdown from this same map, so there is one list.
COUNTRY_NAMES: dict[str, str] = {
    "AR": "Argentina", "AU": "Australia", "AT": "Austria", "BD": "Bangladesh",
    "BE": "Belgium", "BR": "Brazil", "CA": "Canada", "CL": "Chile",
    "CN": "China", "CO": "Colombia", "CZ": "Czechia", "DK": "Denmark",
    "EG": "Egypt", "FI": "Finland", "FR": "France", "DE": "Germany",
    "GR": "Greece", "HK": "Hong Kong", "HU": "Hungary", "IN": "India",
    "ID": "Indonesia", "IE": "Ireland", "IL": "Israel", "IT": "Italy",
    "JP": "Japan", "KE": "Kenya", "MY": "Malaysia", "MX": "Mexico",
    "MA": "Morocco", "NL": "Netherlands", "NZ": "New Zealand",
    "NG": "Nigeria", "NO": "Norway", "PK": "Pakistan", "PE": "Peru",
    "PH": "Philippines", "PL": "Poland", "PT": "Portugal", "RO": "Romania",
    "SA": "Saudi Arabia", "SG": "Singapore", "ZA": "South Africa",
    "KR": "South Korea", "ES": "Spain", "SE": "Sweden", "CH": "Switzerland",
    "TW": "Taiwan", "TH": "Thailand", "TR": "Turkey", "UA": "Ukraine",
    "AE": "United Arab Emirates", "GB": "United Kingdom",
    "US": "United States", "VN": "Vietnam",
}
COUNTRIES = sorted(COUNTRY_NAMES, key=lambda c: COUNTRY_NAMES[c])

SCHEMA: dict[str, Setting] = {s.key: s for s in [
    # ── Brand ────────────────────────────────────────────────
    _s(key="product_name", type="str", default="Signal", group="brand",
       label="Product name",
       help="Shown in the sidebar, the browser tab and the digest email."),

    # ── Schedule ─────────────────────────────────────────────
    _s(key="schedule_hour", type="int", default=9, group="schedule",
       minimum=0, maximum=23, env="DAILY_EMAIL_HOUR",
       label="Daily run time",
       help="Hour of the day, in the timezone below, when the pipeline runs."),
    _s(key="timezone", type="choice", default="UTC", group="schedule",
       choices=TIMEZONES, label="Timezone",
       help="Used for the schedule and for displaying times."),
    _s(key="digest_size", type="int", default=15, group="schedule",
       minimum=1, maximum=50, env="DAILY_JOBS_COUNT",
       label="Roles per digest",
       help="How many roles the daily email includes."),
    _s(key="schedule_enabled", type="bool", default=True, group="schedule",
       label="Run automatically",
       help="Turn off to stop the daily run without stopping the app."),

    # ── Email ────────────────────────────────────────────────
    _s(key="sender_email", type="str", default="", group="email",
       env="SENDER_EMAIL", label="Sender address",
       help="The Gmail account the digest is sent from. Use a dedicated account."),
    _s(key="sender_password", type="str", default="", group="email", secret=True,
       env="SENDER_APP_PASSWORD", label="App password",
       help="A Google app password, not the account password. Stored encrypted."),
    _s(key="recipient_email", type="str", default="", group="email",
       env="RECIPIENT_EMAIL", label="Deliver to",
       help="Where the digest arrives. The active profile can override this."),

    # ── Integrations ─────────────────────────────────────────
    _s(key="rapidapi_key", type="str", default="", group="integrations", secret=True,
       env="RAPIDAPI_KEY", label="JSearch API key",
       help="From RapidAPI. Adds LinkedIn, Indeed and Glassdoor results. Stored encrypted."),
    _s(key="jsearch_limit", type="int", default=200, group="integrations",
       minimum=0, maximum=1000000, label="Monthly request allowance",
       help="Your plan's limit. Drives the quota gauge — the free tier is 200."),
    _s(key="search_country", type="choice", default="US", group="integrations",
       choices=COUNTRIES, label="Default search country",
       help="ISO country code used for saved searches that do not name one. "
            "JSearch requires a country, so worldwide-remote searches are a "
            "country plus 'Remote only'."),
    _s(key="google_sheet_id", type="str", default="", group="integrations",
       env="GOOGLE_SHEET_ID", label="Google Sheet ID",
       help="Optional. Enables exporting results to a spreadsheet."),

    # ── Data ─────────────────────────────────────────────────
    _s(key="stale_job_days", type="int", default=14, group="data",
       minimum=1, maximum=365, label="Forget roles after",
       help="Days without seeing a role again before it is removed. "
            "Roles you marked applied, or added to the digest, are always kept."),
    _s(key="run_retention", type="int", default=200, group="data",
       minimum=10, maximum=5000, label="Activity history",
       help="How many past runs to keep, with their logs."),
    _s(key="min_score_hint", type="int", default=40, group="data",
       minimum=0, maximum=100, label="Default score filter",
       help="The minimum score pre-selected when you open Roles."),

    # ── Crawl ────────────────────────────────────────────────
    _s(key="crawl_concurrency", type="int", default=5, group="crawl",
       minimum=1, maximum=20, label="Simultaneous company requests",
       help="Higher is faster but hits company sites harder. Five is polite."),
    _s(key="crawl_timeout", type="int", default=30, group="crawl",
       minimum=5, maximum=120, label="Request timeout",
       help="Seconds to wait for a company's job board before giving up."),
]}

GROUPS = {
    "brand":        {"label": "Appearance", "help": "How the product presents itself."},
    "schedule":     {"label": "Schedule", "help": "When the daily run happens."},
    "email":        {"label": "Email delivery", "help": "Where the digest comes from and goes to."},
    "integrations": {"label": "Integrations", "help": "External services and their limits."},
    "data":         {"label": "Data & retention", "help": "What is kept, and for how long."},
    "crawl":        {"label": "Crawling", "help": "How company job boards are fetched."},
}


# ── Storage ───────────────────────────────────────────────────

_PREFIX = "setting:"        # namespaced so profile/app keys never collide


def _row_key(key: str) -> str:
    return _PREFIX + key


def _coerce(spec: Setting, raw: Any) -> Any:
    if raw is None or raw == "":
        return spec.default if spec.type != "str" else (raw if raw == "" else spec.default)
    if spec.type == "int":
        try:
            v = int(raw)
        except (TypeError, ValueError):
            return spec.default
        if spec.minimum is not None:
            v = max(spec.minimum, v)
        if spec.maximum is not None:
            v = min(spec.maximum, v)
        return v
    if spec.type == "bool":
        if isinstance(raw, bool):
            return raw
        return str(raw).lower() in ("1", "true", "yes", "on")
    if spec.type == "choice":
        return raw if (not spec.choices or raw in spec.choices) else spec.default
    return str(raw)


def _load() -> None:
    """Read every stored value into the cache. Called lazily and after writes."""
    global _loaded
    stored: dict[str, str] = {}
    try:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT key, value FROM app_settings WHERE key LIKE ?", (_PREFIX + "%",)
            ).fetchall()
            stored = {r["key"][len(_PREFIX):]: r["value"] for r in rows}
        finally:
            conn.close()
    except Exception:
        stored = {}          # database not ready yet; fall back to defaults

    fresh: dict[str, Any] = {}
    for key, spec in SCHEMA.items():
        if key in stored:
            raw = decrypt(stored[key]) if spec.secret else stored[key]
            fresh[key] = _coerce(spec, raw)
        else:
            fresh[key] = spec.default
    _cache.clear()
    _cache.update(fresh)
    _loaded = True


def invalidate() -> None:
    global _loaded
    with _LOCK:
        _loaded = False


def get(key: str, default: Any = None) -> Any:
    """Read a setting. Cheap enough to call at the point of use, which is the
    whole point — no module-level constant to go stale."""
    global _loaded
    with _LOCK:
        if not _loaded:
            _load()
        if key in _cache:
            return _cache[key]
    spec = SCHEMA.get(key)
    return spec.default if spec else default


def set_many(values: dict[str, Any]) -> dict[str, Any]:
    """Persist several settings at once. Returns {key: applied_value}.

    Unknown keys are ignored rather than raising, so a stale browser tab cannot
    break a save. Hooks fire only for values that actually changed.
    """
    applied: dict[str, Any] = {}
    changed: list[tuple[str, Any]] = []
    ts = datetime.utcnow().isoformat()

    conn = get_connection()
    try:
        for key, raw in (values or {}).items():
            spec = SCHEMA.get(key)
            if not spec:
                continue

            # An unchanged masked secret means "leave it alone" — the UI never
            # receives the real value, so it cannot send it back.
            if spec.secret and isinstance(raw, str) and raw.startswith("•"):
                continue

            value = _coerce(spec, raw)
            previous = get(key)

            to_store = encrypt(str(value)) if spec.secret else str(value)
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
                (_row_key(key), to_store, ts),
            )
            applied[key] = value
            if value != previous:
                changed.append((key, value))
        conn.commit()
    finally:
        conn.close()

    invalidate()

    for key, value in changed:
        hook = _HOOKS.get(key)
        if hook:
            try:
                hook(value)
            except Exception as e:
                from core import runlog
                runlog.error(f"Setting '{key}' saved, but applying it failed: {e}")

    return applied


def set_one(key: str, value: Any) -> Any:
    return set_many({key: value}).get(key)


# ── Presentation ──────────────────────────────────────────────

def public() -> dict:
    """Everything the UI needs to render Settings.

    Secret values are never included — only whether one is configured and a
    masked hint, so a screenshot or a browser cache cannot leak a credential.
    """
    out_groups = []
    for gid, meta in GROUPS.items():
        fields = []
        for spec in SCHEMA.values():
            if spec.group != gid:
                continue
            value = get(spec.key)
            field_data = {
                "key": spec.key, "type": spec.type, "label": spec.label,
                "help": spec.help, "secret": spec.secret,
                "choices": spec.choices, "min": spec.minimum, "max": spec.maximum,
                "restart_note": spec.restart_note,
            }
            if spec.secret:
                field_data["configured"] = bool(value)
                field_data["value"] = mask(str(value)) if value else ""
            else:
                field_data["value"] = value
            fields.append(field_data)
        out_groups.append({"id": gid, **meta, "fields": fields})
    return {"groups": out_groups}


# ── One-time migration from .env ──────────────────────────────

def bootstrap_from_env() -> int:
    """Import values from the environment on first run only.

    This is what keeps an existing install working after the switch: whatever is
    already in .env becomes the initial stored value. Afterwards the database is
    authoritative, so editing .env has no further effect — deliberately, since
    there must be exactly one source of truth.
    """
    import os

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'settings_bootstrapped'"
        ).fetchone()
        if row:
            return 0
    finally:
        conn.close()

    imported: dict[str, Any] = {}
    for spec in SCHEMA.values():
        if not spec.env:
            continue
        env_value = os.getenv(spec.env, "")
        if env_value != "":
            imported[spec.key] = env_value

    # The timezone was hardcoded rather than an env var; carry it across so an
    # existing install does not silently jump to the default.
    try:
        from config.settings import LEGACY_TIMEZONE
        if LEGACY_TIMEZONE:
            imported.setdefault("timezone", LEGACY_TIMEZONE)
    except Exception:
        pass

    if imported:
        set_many(imported)

    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)",
            ("settings_bootstrapped", datetime.utcnow().isoformat(),
             datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()

    return len(imported)
