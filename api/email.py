"""Digest delivery and provider status."""


from fastapi import APIRouter, Query

from api.deps import enqueue_run
from core import settings_store as settings
from core.database import get_api_usage, get_email_logs
from core.emailer import send_daily_digest
from core.profile import (
    get_active_profile,
)

router = APIRouter()

# ── Email Digest API ───────────────────────────────────────────

@router.post("/api/email/send-now")
async def api_send_email_now(dry_run: bool = Query(False)):
    """Manually trigger the daily digest email."""
    result = send_daily_digest(dry_run=dry_run)
    return result


@router.post("/api/email/run-pipeline")
async def api_run_pipeline(send: bool = Query(True)):
    """Run the full daily pipeline now: collect -> outreach -> email."""
    return enqueue_run("pipeline", send=send)


@router.get("/api/email/log")
async def api_email_log(limit: int = Query(30, ge=1, le=200)):
    """Digest send history. Previously only reachable nested inside
    /api/email/status, with no UI surface at all."""
    return {"sends": get_email_logs(limit=limit)}


@router.get("/api/email/status")
async def api_email_status():
    logs = get_email_logs(limit=10)
    out_cfg = get_active_profile().get("outreach") or {}
    profile_recipient = (out_cfg.get("recipient_email") or "").strip()
    settings_recipient = settings.get("recipient_email")
    effective_recipient = profile_recipient or settings_recipient
    sender = settings.get("sender_email")
    return {
        "sender_configured": bool(sender) and bool(settings.get("sender_password")),
        "sender": sender,
        "sender_source": "settings" if sender else "none",
        "recipient": effective_recipient,
        "recipient_source": "profile" if profile_recipient else ("settings" if settings_recipient else "none"),
        "candidate_name": out_cfg.get("candidate_name") or "",
        "scheduled_hour": settings.get("schedule_hour"),
        "timezone": settings.get("timezone"),
        "recent_sends": logs,
    }


@router.get("/api/jsearch/status")
async def api_jsearch_status():
    usage = get_api_usage("jsearch")
    # The allowance is configurable now — hardcoding 200 made this gauge lie
    # for anyone not on the free plan.
    monthly_limit = settings.get("jsearch_limit")
    return {
        "configured": bool(settings.get("rapidapi_key")),
        "month": usage["month"],
        "today": usage["today"],
        "total": usage["total"],
        "monthly_limit": monthly_limit,
        "remaining": max(0, monthly_limit - usage["month"]),
    }


