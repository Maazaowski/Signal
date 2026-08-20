"""System health, settings and the scheduler."""


from fastapi import APIRouter, HTTPException, Request

from api.deps import APP_VERSION
from config.settings import DB_PATH
from core import runs as run_engine
from core import settings_store as settings
from core.database import get_active_run, get_api_usage, get_runs, get_stats
from core.profile import (
    get_active_profile,
)

router = APIRouter()

# ── System health ──────────────────────────────────────────────

@router.get("/api/system")
async def api_system(request: Request):
    """Everything needed to judge whether the system is actually working.
    `warnings` renders as a banner, so the app can never look healthy while
    degraded. Values come from the settings store, so this reflects a change
    the moment it is saved."""
    import os
    from datetime import datetime

    scheduler = request.app.state.scheduler
    job = scheduler.get_job("daily_pipeline") if scheduler.running else None
    next_run = None
    if job and job.next_run_time:
        next_run = {
            "iso": job.next_run_time.isoformat(),
            "display": job.next_run_time.strftime("%a %d %b, %H:%M %Z"),
        }

    usage = get_api_usage("jsearch")
    limit = settings.get("jsearch_limit")
    try:
        db_size = os.path.getsize(DB_PATH)
    except OSError:
        db_size = 0

    try:
        profile = get_active_profile()
        active_profile = {"id": profile.get("_id"), "name": profile.get("_name")}
    except Exception:
        active_profile = None

    runs_recent = get_runs(limit=1)
    stats = get_stats()

    warnings = list(getattr(request.app.state, "boot_warnings", []))
    warnings += request.app.state.config_warnings()
    if not scheduler.running:
        warnings.append("The scheduler is not running, so nothing will happen automatically.")
    if not run_engine.worker_alive():
        warnings.append("The background worker is not running, so nothing can be started.")
    if limit and usage["month"] >= limit:
        warnings.append(
            f"JSearch allowance used up ({usage['month']} of {limit} this month). "
            "Collection falls back to the free sources until it resets."
        )

    return {
        "version": APP_VERSION,
        "product_name": settings.get("product_name"),
        "started_at": getattr(request.app.state, "started_at", None),
        "healthy": len(warnings) == 0,
        "warnings": warnings,
        "scheduler": {
            "running": scheduler.running and bool(job),
            "enabled": settings.get("schedule_enabled"),
            "hour": settings.get("schedule_hour"),
            "timezone": settings.get("timezone"),
            "next_run": next_run,
        },
        "worker": {"alive": run_engine.worker_alive()},
        "active_run": get_active_run(),
        "last_run": runs_recent[0] if runs_recent else None,
        "database": {"path": DB_PATH, "size_bytes": db_size, "jobs": stats.get("total", 0)},
        "jsearch": {
            "configured": bool(settings.get("rapidapi_key")),
            "used_this_month": usage["month"],
            "used_today": usage["today"],
            "limit": limit,
            "remaining": max(0, limit - usage["month"]) if limit else 0,
        },
        "email": {
            "sender_configured": bool(settings.get("sender_email") and settings.get("sender_password")),
            "sender": settings.get("sender_email"),
            "recipient": settings.get("recipient_email"),
        },
        "active_profile": active_profile,
        "server_time": datetime.utcnow().isoformat(),
    }


# ── Settings ───────────────────────────────────────────────────

@router.get("/api/settings")
async def api_get_settings():
    """Grouped settings for the UI to render. Secret values are never included -
    only whether one is configured plus a masked hint."""
    return settings.public()


@router.put("/api/settings")
async def api_put_settings(body: dict):
    """Partial update. Saving fires each setting's on_change hook, so a schedule
    change reschedules the live cron job immediately - no restart."""
    if not isinstance(body, dict) or not body:
        raise HTTPException(status_code=400, detail="Nothing to update")
    unknown = [k for k in body if k not in settings.SCHEMA]
    if unknown:
        raise HTTPException(status_code=400,
                            detail=f"Unknown setting(s): {', '.join(unknown)}")
    settings.set_many(body)
    return {"ok": True, "settings": settings.public()}


@router.post("/api/settings/test/email")
async def api_test_email():
    """Verify the mail credentials by opening a real SMTP session, so a bad app
    password is caught here rather than at 9am."""
    import smtplib
    import ssl

    sender = settings.get("sender_email")
    password = settings.get("sender_password")
    if not sender or not password:
        return {"ok": False, "detail": "Add a sender address and app password first."}
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx, timeout=15) as s:
            s.login(sender, password)
        return {"ok": True, "detail": f"Signed in to Gmail as {sender}."}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "detail": "Gmail rejected those credentials. "
                                       "Check you used a 16-character app password, "
                                       "not the account password."}
    except Exception as e:
        return {"ok": False, "detail": f"Could not reach Gmail: {e}"}


@router.post("/api/settings/test/jsearch")
async def api_test_jsearch():
    """Spend exactly one request to confirm the key works, and report the
    quota headers so the allowance can be set correctly."""
    import httpx

    key = settings.get("rapidapi_key")
    if not key:
        return {"ok": False, "detail": "Add a JSearch API key first."}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                "https://jsearch.p.rapidapi.com/search",
                headers={"x-rapidapi-host": "jsearch.p.rapidapi.com",
                         "x-rapidapi-key": key},
                params={"query": "python developer", "page": 1, "num_pages": 1},
            )
        if r.status_code == 200:
            allowed = r.headers.get("x-ratelimit-requests-limit")
            left = r.headers.get("x-ratelimit-requests-remaining")
            note = f" {left} of {allowed} requests left this month." if allowed else ""
            return {"ok": True, "detail": f"Key works.{note}",
                    "limit": int(allowed) if allowed and allowed.isdigit() else None}
        if r.status_code in (401, 403):
            return {"ok": False, "detail": "RapidAPI rejected the key. "
                                           "Check it is copied from the JSearch page."}
        if r.status_code == 429:
            return {"ok": False, "detail": "Monthly allowance already used up."}
        return {"ok": False, "detail": f"Unexpected response ({r.status_code})."}
    except Exception as e:
        return {"ok": False, "detail": f"Could not reach RapidAPI: {e}"}


@router.post("/api/system/scheduler/pause")
async def api_scheduler_pause(request: Request):
    if request.app.state.scheduler.running:
        request.app.state.scheduler.pause()
    return {"ok": True, "paused": True}


@router.post("/api/system/scheduler/resume")
async def api_scheduler_resume(request: Request):
    if request.app.state.scheduler.running:
        request.app.state.scheduler.resume()
    return {"ok": True, "paused": False}


