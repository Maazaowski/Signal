"""Intros: generated messages and the digest email."""


from fastapi import APIRouter, Query
from pydantic import BaseModel

from core.collector import run_collection
from core.database import (
    delete_outreach_bulk,
    get_last_outreach_batch_at,
    get_outreach,
    get_outreach_stats,
    update_outreach_notes,
    update_outreach_status,
)
from core.emailer import generate_outreach_for_top_jobs

router = APIRouter()

# ── Outreach API ───────────────────────────────────────────────

@router.get("/api/outreach")
async def api_get_outreach(
    status: str | None = None,
    search: str | None = None,
    batch: str | None = Query(None, pattern="^(new|old|all)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    batch_filter = batch if batch in ("new", "old") else None
    items = get_outreach(status=status, search=search, batch=batch_filter,
                         limit=limit, offset=offset)
    return {
        "outreach": items,
        "count": len(items),
        "last_batch_at": get_last_outreach_batch_at(),
    }


@router.get("/api/outreach/stats")
async def api_outreach_stats():
    return get_outreach_stats()


class OutreachBulkDelete(BaseModel):
    ids: list[str]


@router.post("/api/outreach/bulk-delete")
async def api_outreach_bulk_delete(body: OutreachBulkDelete):
    deleted = delete_outreach_bulk(body.ids)
    return {"deleted": deleted}


@router.post("/api/outreach/refresh")
async def api_outreach_refresh(limit: int = Query(15, ge=1, le=50),
                               min_score: int = Query(40, ge=0, le=100)):
    """Refresh = run a fresh collection, then generate outreach scoped to the
    jobs that were actually returned by that collection. Previous batches stay
    in place and show up in the 'Old' tab."""
    from datetime import datetime
    cutoff = datetime.utcnow().isoformat()
    collect_stats = await run_collection()
    generated = generate_outreach_for_top_jobs(
        limit=limit, min_score=min_score, seen_after=cutoff,
    )
    return {"collected": collect_stats, "generated": generated}


@router.post("/api/outreach/generate")
async def api_generate_outreach(
    min_score: int = Query(40, ge=0, le=100),
    limit: int = Query(15, ge=1, le=50),
    location_fit: str | None = "maybe",
):
    """For top N high-scoring jobs without existing outreach,
    build LinkedIn search URLs + generate DMs. No API credits used."""
    generated = generate_outreach_for_top_jobs(
        limit=limit, min_score=min_score, location_fit=location_fit,
    )
    if generated == 0:
        return {"generated": 0, "message": "No new jobs eligible for outreach"}
    return {"generated": generated}


@router.patch("/api/outreach/{outreach_id}/status")
async def api_update_outreach(outreach_id: str, status: str = Query(...)):
    field_map = {"messaged": "messaged", "replied": "replied", "followed_up": "followed_up"}
    update_outreach_status(outreach_id, status, field=field_map.get(status))
    return {"ok": True}


@router.patch("/api/outreach/{outreach_id}/notes")
async def api_update_outreach_notes(outreach_id: str, notes: str = Query("")):
    update_outreach_notes(outreach_id, notes)
    return {"ok": True}


