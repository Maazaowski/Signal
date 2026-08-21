"""Background run engine.

Before this, `POST /api/collect` awaited the whole collection inline: the HTTP
request blocked for one to two minutes, and closing the tab lost all visibility.
Work now goes through a queue with a single worker, so:

  * the endpoint returns a run_id immediately and the UI polls it
  * progress and logs survive a page refresh (they live in SQLite, not the tab)
  * only one job runs at a time, so double-clicking "Collect Jobs" cannot spend
    the RapidAPI quota twice
  * a crash leaves a `failed` row with the traceback rather than silence
"""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Callable
from typing import Any

from core import runlog
from core.database import (
    create_run,
    finish_run,
    get_active_run,
    get_run,
    reap_orphaned_runs,
    start_run,
)

# Human-readable labels, also used by the UI to render run kinds.
RUN_KINDS = {
    "collect": "Collect jobs",
    "crawl": "Crawl company boards",
    "pipeline": "Full daily pipeline",
    "email": "Send digest email",
    "outreach": "Generate outreach",
    "rescore": "Re-score all jobs",
    "discover": "Discover companies",
    "seed": "Seed companies",
    "detect_ats": "Detect company ATS",
}

_queue: asyncio.Queue | None = None
_worker_task: asyncio.Task | None = None
_current_run_id: int | None = None


class RunBusyError(Exception):
    """Raised when a run is requested while another is still active."""

    def __init__(self, active: dict):
        self.active = active
        super().__init__(
            f"A {RUN_KINDS.get(active.get('kind'), active.get('kind'))} run is "
            f"already in progress (run #{active.get('id')})."
        )


# ── Job registry ───────────────────────────────────────────────
# Handlers are registered rather than imported at module load, to avoid a
# circular import (collector -> runlog -> database, emailer -> collector).

_HANDLERS: dict[str, Callable] = {}


def register(kind: str, fn: Callable) -> None:
    _HANDLERS[kind] = fn


def _load_default_handlers() -> None:
    if _HANDLERS:
        return

    async def _collect(**kw):
        from core.collector import run_collection
        return await run_collection(include_companies=kw.get("include_companies", True))

    async def _crawl(**kw):
        from core.collector import run_company_crawl
        return await run_company_crawl(company_ids=kw.get("company_ids"))

    async def _pipeline(**kw):
        from core.emailer import run_daily_pipeline
        return await run_daily_pipeline(send=kw.get("send", True))

    # NOTE: the handlers below are synchronous, CPU/DB/SMTP-bound loops. Run
    # them with asyncio.to_thread, otherwise they block the event loop and the
    # server cannot answer progress polls while they execute - which would
    # defeat the point of running them in the background at all.
    # contextvars propagate into to_thread, so runlog's run context still works.

    async def _email(**kw):
        from core.emailer import send_daily_digest
        return await asyncio.to_thread(
            send_daily_digest, dry_run=kw.get("dry_run", False)
        )

    async def _outreach(**kw):
        from core.emailer import generate_outreach_for_top_jobs
        n = await asyncio.to_thread(
            generate_outreach_for_top_jobs,
            limit=kw.get("limit", 15),
            min_score=kw.get("min_score", 40),
            location_fit=kw.get("location_fit", "maybe"),
        )
        return {"generated": n}

    async def _rescore(**kw):
        from core.rescore import rescore_all_jobs
        return await asyncio.to_thread(
            rescore_all_jobs, delete_below_min=kw.get("delete_below_min", False)
        )

    async def _discover(**kw):
        from core.bulk_discover import run_bulk_discovery
        return await run_bulk_discovery(
            sources=kw.get("sources") or ["yc", "remoteintech", "wwr"],
            detect_ats=kw.get("detect_ats", True),
            min_team_size=kw.get("min_team_size", 10),
        )

    def _seed_sync(mega: bool = True):
        from core.company_seeder import get_all_seed_companies
        from core.database import upsert_company
        from core.mega_companies import get_all_mega_companies
        companies = get_all_mega_companies() if mega else get_all_seed_companies()
        added = 0
        total = len(companies)
        for i, c in enumerate(companies, 1):
            if upsert_company(c):
                added += 1
            if i % 25 == 0 or i == total:
                runlog.progress(i, total, f"Seeding companies ({i}/{total})")
        runlog.log(f"Seeded {added} of {total} companies")
        return {"total_in_list": total, "added": added}

    async def _seed(**kw):
        return await asyncio.to_thread(_seed_sync, kw.get("mega", True))

    async def _detect_ats(**kw):
        from core.ats_detect import detect_ats_for_stored
        return await detect_ats_for_stored(
            only_unknown=kw.get("only_unknown", True),
            limit=kw.get("limit", 0),
        )

    _HANDLERS.update({
        "collect": _collect, "crawl": _crawl, "pipeline": _pipeline,
        "email": _email, "outreach": _outreach, "rescore": _rescore,
        "discover": _discover, "seed": _seed, "detect_ats": _detect_ats,
    })


# ── Public API ─────────────────────────────────────────────────

def enqueue(kind: str, trigger: str = "manual", **kwargs: Any) -> int:
    """Queue a run and return its id immediately.

    Raises RunBusyError if something is already running — deliberate, so the UI
    can say "already running" instead of silently stacking duplicate work.
    """
    _load_default_handlers()
    if kind not in _HANDLERS:
        raise ValueError(f"Unknown run kind: {kind}")

    active = get_active_run()
    if active:
        raise RunBusyError(active)

    run_id = create_run(kind, trigger)
    if _queue is None:
        # No event loop worker (e.g. a script importing this module). Fail the
        # run immediately rather than leaving it queued forever.
        finish_run(run_id, "failed", error="Run worker is not running")
        raise RuntimeError("Run worker is not running")

    _queue.put_nowait((run_id, kind, kwargs))
    return run_id


async def _execute(run_id: int, kind: str, kwargs: dict) -> None:
    global _current_run_id
    _current_run_id = run_id
    token = runlog.set_run_context(run_id)
    start_run(run_id)
    label = RUN_KINDS.get(kind, kind)
    try:
        runlog.log(f"=== {label} started (run #{run_id}) ===")
        result = await _HANDLERS[kind](**kwargs)
        stats = result if isinstance(result, dict) else {"result": result}
        finish_run(run_id, "success", stats=stats)
        runlog.log(f"=== {label} finished (run #{run_id}) ===")
    except asyncio.CancelledError:
        finish_run(run_id, "cancelled", error="Cancelled")
        runlog.warn(f"=== {label} cancelled (run #{run_id}) ===")
        raise
    except Exception as e:
        tb = traceback.format_exc(limit=6)
        finish_run(run_id, "failed", error=f"{type(e).__name__}: {e}\n{tb}")
        runlog.error(f"=== {label} FAILED (run #{run_id}): {type(e).__name__}: {e} ===")
    finally:
        runlog.reset_run_context(token)
        _current_run_id = None


async def _worker() -> None:
    assert _queue is not None
    while True:
        run_id, kind, kwargs = await _queue.get()
        try:
            await _execute(run_id, kind, kwargs)
        except asyncio.CancelledError:
            raise
        except Exception:
            # _execute already records failures; this is belt and braces so the
            # worker loop itself can never die and silently stop all automation.
            runlog.error(f"Run worker error:\n{traceback.format_exc(limit=4)}")
        finally:
            _queue.task_done()


async def start_worker() -> None:
    """Called from the app lifespan. Idempotent."""
    global _queue, _worker_task
    _load_default_handlers()
    if _worker_task and not _worker_task.done():
        return
    reaped = reap_orphaned_runs()
    if reaped:
        runlog.warn(f"Marked {reaped} interrupted run(s) as failed from a previous session")
    _queue = asyncio.Queue()
    _worker_task = asyncio.create_task(_worker(), name="run-worker")


async def stop_worker() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
    _worker_task = None


def worker_alive() -> bool:
    return bool(_worker_task and not _worker_task.done())


def cancel_current() -> bool:
    """Cancel the in-flight run, if any. Returns whether anything was cancelled."""
    if _worker_task and _current_run_id is not None:
        _worker_task.cancel()
        return True
    return False


def current_run() -> dict | None:
    return get_run(_current_run_id) if _current_run_id else None
