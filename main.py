"""Signal — application assembly.

This module owns the application object and its lifecycle: opening the
database, importing settings, starting the background worker and the
scheduler, and mounting the routers. It deliberately contains no routes —
those live in api/, split by concern, so this file stays readable as the
system grows.
"""

from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api import (
    companies,
    email,
    exports,
    intros,
    pages,
    profiles,
    queries,
    roles,
    system,
)
from api import (
    runs as runs_api,
)
from api.deps import APP_VERSION, asset_stamp  # noqa: F401  (re-exported for tests)
from config.settings import HOST, PORT
from core import runlog
from core import runs as run_engine
from core import settings_store as settings
from core.database import init_db

# The scheduler's own timezone stays UTC. The timezone belongs on the
# CronTrigger instead, which is what makes it changeable at runtime -
# AsyncIOScheduler fixes its timezone at construction.
scheduler = AsyncIOScheduler(timezone="UTC")


async def _scheduled_pipeline():
    """Cron entrypoint. Goes through the run engine so scheduled work appears
    in the same history and log surface as anything started from the UI."""
    try:
        run_engine.enqueue("pipeline", trigger="schedule", send=True)
    except run_engine.RunBusyError as e:
        runlog.warn(f"Scheduled run skipped: {e}")


def _schedule_trigger() -> CronTrigger:
    return CronTrigger(hour=settings.get("schedule_hour"), minute=0,
                       timezone=settings.get("timezone"))


def apply_schedule(*_args) -> None:
    """Rebuild the cron job from current settings. Registered as the on_change
    hook for the schedule settings, so saving one reschedules the live job with
    no restart."""
    if not scheduler.running:
        return
    scheduler.remove_all_jobs()
    if not settings.get("schedule_enabled"):
        runlog.warn("Automatic runs are turned off in Settings")
        return
    scheduler.add_job(_scheduled_pipeline, _schedule_trigger(),
                      id="daily_pipeline", replace_existing=True,
                      misfire_grace_time=3600)
    job = scheduler.get_job("daily_pipeline")
    if job and job.next_run_time:
        runlog.log(f"Schedule updated - next run "
                   f"{job.next_run_time.strftime('%a %d %b %H:%M %Z')}")


def config_warnings() -> list[str]:
    """Computed fresh on every health check, never cached at startup -
    otherwise saving a key in Settings would leave a stale warning on screen."""
    out = []
    if not settings.get("rapidapi_key"):
        out.append(
            "No JSearch key, so LinkedIn, Indeed and Glassdoor results are "
            "unavailable. The free boards and company pages still run. "
            "Add a key in Settings."
        )
    if not (settings.get("sender_email") and settings.get("sender_password")):
        out.append(
            "Email delivery is not set up. Roles are still collected daily, but "
            "no digest is sent. Finish setup in Settings."
        )
    elif not settings.get("recipient_email"):
        out.append("No recipient address, so the digest has nowhere to go.")
    if not settings.get("schedule_enabled"):
        out.append("Automatic runs are turned off, so nothing happens on a schedule.")
    return out


@asynccontextmanager
async def lifespan(app: FastAPI):
    boot: list[str] = []

    try:
        init_db()
    except Exception as e:
        boot.append(f"The database could not be opened: {e}")
        runlog.error(f"Database initialisation failed: {e}")

    # Import any existing .env values once; afterwards the database is the
    # single source of truth for configuration.
    try:
        imported = settings.bootstrap_from_env()
        if imported:
            runlog.log(f"Imported {imported} setting(s) from .env into Settings")
        for key in ("schedule_hour", "timezone", "schedule_enabled"):
            settings.register_hook(key, apply_schedule)
    except Exception as e:
        boot.append(f"Settings could not be loaded: {e}")
        runlog.error(f"Settings failed to load: {e}")

    try:
        await run_engine.start_worker()
        runlog.log("Run worker started")
    except Exception as e:
        boot.append(f"Background worker failed to start: {e}")
        runlog.error(f"Background worker failed to start: {e}")

    # Started unconditionally. This used to be wrapped in `if SENDER_EMAIL:`,
    # so a missing sender silently disabled the daily collection as well as the
    # email. The email step is gated inside run_daily_pipeline instead.
    try:
        scheduler.start()
        apply_schedule()
    except Exception as e:
        boot.append(f"The scheduler failed to start: {e}")
        runlog.error(f"The scheduler failed to start: {e}")

    app.state.scheduler = scheduler
    app.state.config_warnings = config_warnings
    app.state.boot_warnings = boot
    app.state.started_at = datetime.utcnow().isoformat()
    for w in boot:
        runlog.warn(f"Startup: {w}")

    yield

    if scheduler.running:
        scheduler.shutdown(wait=False)
    await run_engine.stop_worker()


app = FastAPI(title="Signal", version=APP_VERSION, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.middleware("http")
async def block_cross_origin(request: Request, call_next):
    """Signal has no authentication and runs on 127.0.0.1.

    Many state-changing endpoints take query params with no body, which makes
    them "simple requests": any website open in the same browser could POST to
    them with no preflight - deleting roles or spending API quota. Browsers
    always send Sec-Fetch-Site; curl and Postman send nothing, so command-line
    use still works.
    """
    if request.method != "GET":
        site = request.headers.get("sec-fetch-site")
        if site not in (None, "same-origin", "none"):
            return JSONResponse({"detail": "cross-origin request blocked"},
                                status_code=403)
    return await call_next(request)


# FastAPI matches routes in registration order, so a literal path must be
# registered before a parameterised one that would also match it. Keep such
# pairs inside a single router rather than relying on this tuple's order — see
# the marked-roles endpoints in api/roles.py. A test walks app.routes and fails
# on any literal path shadowed by an earlier parameterised route.
for _router in (roles, runs_api, system, companies, exports, intros,
                queries, email, profiles, pages):
    app.include_router(_router.router)


if __name__ == "__main__":
    print(f"Starting Signal at http://{HOST}:{PORT}")
    uvicorn.run("main:app", host=HOST, port=PORT)
