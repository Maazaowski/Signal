# Profiles and sources

Two things you are likely to want to change: **who Signal is looking for**, and
**where it looks**. Neither needs a code edit for the first, and the second is
one small file.

For setup and daily use, read [SETUP.md](../SETUP.md). For why the code is
shaped this way, read [00-history.md](00-history.md).

---

## The profile

A profile is the whole targeting configuration: search terms, scoring weights,
where you can work, and the text of your intros. Exactly one is active at a
time. Nothing candidate-specific lives in Python — `core/scorer.py`,
`core/hunter.py` and `core/emailer.py` all read the active profile at the point
of use.

Edit it in **Settings**, which is generated from the profile schema, or edit a
YAML preset and import it. The `profiles/` directory holds four starting points;
all of them ship with the `outreach` block blanked out, because that block is
about you.

### Top-level sections

| Section | What it controls |
|---|---|
| `search` | Terms to search for, positive and negative title keywords, the tech list, and the JSearch queries |
| `scoring` | Experience target, the minimum score to store a role, and the four weights |
| `location` | Home terms, global terms, regions, and the exclusion lists behind "open to you" |
| `outreach` | Your name, bio, achievements and the two message templates |

### The `outreach` block

| Field | What it does |
|---|---|
| `candidate_name` | Signs the long DM and greets you in the digest |
| `bio_short` | One-liner used inside the DM. `{stack}` is substituted with the tech you and the role have in common |
| `achievements` | Bullet list injected into the long DM as `{achievements}` |
| `dm_short_template` | LinkedIn connection note. Hard-capped at 300 characters in `core/hunter.py` — that is LinkedIn's limit, not a style choice |
| `dm_long_template` | The full message |
| `candidate_core_tech` | Drives the `{stack}` token and a scoring bonus |
| `recipient_email` | Optional per-profile override of the digest recipient |

**On `recipient_email`:** a non-empty value here **wins over** the address in
Settings (`core/emailer.py`). That is deliberate — it lets one profile mail a
different inbox — but it means a value left in a shared preset silently
misdirects someone else's digest. The shipped presets leave it blank.

### Template tokens

`core/hunter.py::_safe_format()` substitutes these. An unknown token renders
empty rather than raising, so a typo costs you a blank, not a crash:

`{greeting}` `{company}` `{title}` `{stack}` `{bio_short}` `{achievements}` `{candidate_name}`

### Presets

Copy any file in `profiles/`, edit it, and import it from **Settings →
Profiles**, which lists every YAML file in that directory as a starting point.
Export the other way with `GET /api/profiles/{id}/export`, which returns YAML.

Changing scoring weights only affects roles collected afterwards. To apply them
to what you already have, use **Settings → Reapply scoring**.

---

## Adding a job source

Every source implements one method. `sources/base.py` is the entire contract:

```python
class BaseSource(ABC):
    name: str = "unknown"

    @abstractmethod
    async def fetch(self) -> list[Job]:
        """Fetch jobs from this source. Returns list of Job objects."""
```

There are eight adapters to copy from. `sources/remotive.py` is the simplest —
one public JSON endpoint, no key.

**1. Write the adapter.** Return `Job` models (`core/models.py`); the id is
derived for you, so dedup works across sources without you doing anything.

```python
import httpx

from core.models import Job
from sources.base import BaseSource


class ExampleSource(BaseSource):
    name = "example"

    async def fetch(self) -> list[Job]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get("https://example.com/api/jobs")
            resp.raise_for_status()

        return [
            Job(
                title=item["title"],
                company=item["company"],
                location=item.get("location", ""),
                description=item.get("description", ""),
                url=item["url"],
                source=self.name,
                posted_date=item.get("published_at", ""),
            )
            for item in resp.json()["jobs"]
        ]
```

**2. Register it** in `core/collector.py::_build_job_board_sources()`, which
builds the list fresh on every run:

```python
sources = [
    RemotiveSource(),
    RemoteOKSource(),
    ArbeitnowSource(),
    ExampleSource(),
]
```

Scoring, location fit, deduplication, storage and retention all apply
automatically. A source that raises is logged and skipped rather than failing
the run.

**If the source costs money**, follow `sources/jsearch.py`: read the key with
`settings.get("...")` **at the point of use** — never into a module constant or
an instance attribute — and log each call through `log_api_call` so the quota
gauge stays honest. Add the key as a row in `SCHEMA` in
`core/settings_store.py`; the Settings UI builds itself from that schema.

---

## Company boards

The other collection track crawls company ATS boards directly. Adding a company
needs no code — use **Companies → Add**, or **Add curated list**, then **Find
job boards** so their ATS is detected. A company whose board is never detected
stays paused and is never crawled.

Greenhouse, Lever and Ashby have dedicated adapters. Anything else falls back to
`sources/html_scraper.py`, which is best-effort.
