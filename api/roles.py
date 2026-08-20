"""Roles: the collected job listings, their stats and sources."""


from fastapi import APIRouter, Query

from api.deps import enqueue_run
from core.database import (
    get_job_by_id,
    get_jobs,
    get_marked_jobs,
    get_sources,
    get_stats,
    toggle_mark_for_email,
    update_job_status,
)

router = APIRouter()

# ── Jobs API ───────────────────────────────────────────────────

@router.get("/api/jobs")
async def api_get_jobs(
    source: str | None = None,
    status: str | None = None,
    min_score: int = Query(0, ge=0, le=100),
    search: str | None = None,
    location: str | None = None,
    tech: str | None = None,
    india_friendly: str | None = None,
    company_domain: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    jobs = get_jobs(
        source=source, status=status, min_score=min_score,
        search=search, location=location, tech=tech,
        india_friendly=india_friendly, company_domain=company_domain,
        limit=limit, offset=offset,
    )
    return {"jobs": jobs, "count": len(jobs)}


# ── Marking for the digest ─────────────────────────────────────
# These live here, immediately above /api/jobs/{job_id}, because FastAPI matches
# routes in registration order: a literal path must be registered before the
# parameterised one that would also match it. Split into their own router, this
# pair sat after `roles` in main.py's mount tuple and "marked" was read as a job
# id, so the endpoint answered with the job-detail error and was unreachable.

@router.post("/api/jobs/{job_id}/mark-for-email")
async def api_mark_for_email(job_id: str):
    """Toggle whether a role is promoted in the next digest. Returns the new
    state. Marked roles sort above score order in the digest and are exempt from
    the stale-role cleanup."""
    return {"mark_for_email": toggle_mark_for_email(job_id)}


@router.get("/api/jobs/marked")
async def api_get_marked():
    return {"jobs": get_marked_jobs()}


@router.get("/api/jobs/{job_id}")
async def api_get_job(job_id: str):
    job = get_job_by_id(job_id)
    if not job:
        return {"error": "Job not found"}
    return job


@router.patch("/api/jobs/{job_id}/status")
async def api_update_status(job_id: str, status: str = Query(...)):
    update_job_status(job_id, status)
    return {"ok": True}


@router.get("/api/stats")
async def api_stats():
    return get_stats()


@router.get("/api/sources")
async def api_sources():
    return {"sources": get_sources()}


@router.post("/api/collect")
async def api_collect():
    """Start a collection run. Returns a run_id immediately - poll
    /api/runs/{id} for progress.

    There used to be a `generate_outreach` flag here, but the collect handler
    never read it, so passing it did nothing. Use the `pipeline` run kind when
    you want collect -> intros -> digest in one go."""
    return enqueue_run("collect")


