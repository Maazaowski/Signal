"""JSearch queries stored on the active profile."""


from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.profile import (
    add_active_profile_query,
    delete_active_profile_query,
    get_active_profile_queries,
    update_active_profile_query,
)

router = APIRouter()

# ── Search Queries (stored on the active profile) ──────────────

@router.get("/api/search-queries")
async def api_get_queries():
    return {"queries": get_active_profile_queries()}


class QueryInput(BaseModel):
    query: str
    # Left empty rather than defaulting here: a model default is evaluated at
    # import, which is exactly how config used to go stale in this codebase.
    # The country is resolved from settings at the point of use below.
    country: str = ""
    date_posted: str = "3days"
    remote_jobs_only: bool = False


@router.post("/api/search-queries")
async def api_add_query(body: QueryInput):
    from core import settings_store as settings
    country = body.country or settings.get("search_country")
    try:
        qid = add_active_profile_query(
            body.query, country, body.date_posted, body.remote_jobs_only,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"id": qid, "ok": True}


class QueryPatch(BaseModel):
    query: str | None = None
    country: str | None = None
    date_posted: str | None = None
    remote_jobs_only: bool | None = None
    enabled: bool | None = None


@router.patch("/api/search-queries/{qid}")
async def api_update_query(qid: int, body: QueryPatch):
    try:
        update_active_profile_query(qid, **body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


@router.delete("/api/search-queries/{qid}")
async def api_delete_query(qid: int):
    try:
        delete_active_profile_query(qid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


