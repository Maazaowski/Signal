"""Companies whose job boards are crawled directly."""


from fastapi import APIRouter, Query
from pydantic import BaseModel

from api.deps import enqueue_run
from core.database import (
    get_companies,
    get_company_by_id,
    get_company_stats,
    update_company_crawl_status,
    upsert_company,
)

router = APIRouter()

# ── Companies API ──────────────────────────────────────────────

@router.get("/api/companies")
async def api_get_companies(
    ats_platform: str | None = None,
    crawl_status: str | None = None,
    location_fit: str | None = None,
    search: str | None = None,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    companies = get_companies(
        ats_platform=ats_platform, crawl_status=crawl_status,
        location_fit=location_fit, search=search,
        limit=limit, offset=offset,
    )
    return {"companies": companies, "count": len(companies)}


class CompanyInput(BaseModel):
    name: str
    domain: str = ""
    careers_url: str = ""
    ats_platform: str = "unknown"
    ats_slug: str = ""
    founded_year: int = 0
    employee_count: str = ""
    tags: str = ""
    location_fit: str = "unknown"
    notes: str = ""


@router.post("/api/companies")
async def api_add_company(body: CompanyInput):
    from core.models import Company
    data = body.model_dump()
    data["id"] = Company.make_id(data["name"])
    data["last_crawled"] = ""
    data["crawl_status"] = "active"
    upsert_company(data)
    return {"ok": True, "id": data["id"]}


@router.patch("/api/companies/{company_id}")
async def api_update_company(company_id: str, body: CompanyInput):
    existing = get_company_by_id(company_id)
    if not existing:
        return {"error": "Not found"}
    data = body.model_dump()
    data["id"] = company_id
    data["last_crawled"] = existing.get("last_crawled", "")
    data["crawl_status"] = existing.get("crawl_status", "active")
    upsert_company(data)
    return {"ok": True}


@router.delete("/api/companies/{company_id}")
async def api_pause_company(company_id: str):
    from datetime import datetime
    update_company_crawl_status(company_id, "paused", datetime.utcnow().isoformat())
    return {"ok": True}


@router.post("/api/companies/{company_id}/activate")
async def api_activate_company(company_id: str):
    update_company_crawl_status(company_id, "active")
    return {"ok": True}


@router.get("/api/companies/stats")
async def api_company_stats():
    return get_company_stats()


@router.post("/api/companies/seed")
async def api_seed_companies():
    return enqueue_run("seed", mega=False)


@router.post("/api/companies/mega-seed")
async def api_mega_seed():
    """Load the full curated company list (large employers + remote-first)."""
    return enqueue_run("seed", mega=True)


@router.post("/api/companies/{company_id}/crawl")
async def api_crawl_company(company_id: str):
    return enqueue_run("crawl", company_ids=[company_id])


@router.post("/api/companies/crawl")
async def api_crawl_all_companies():
    return enqueue_run("crawl")


@router.post("/api/companies/detect-ats")
async def api_detect_ats(domain: str = Query(...)):
    """Probe a single domain. For the stored company list use
    /api/companies/detect-ats/all instead."""
    from core.company_seeder import detect_ats_platform
    return await detect_ats_platform(domain)


@router.post("/api/companies/detect-ats/all")
async def api_detect_ats_all(only_unknown: bool = Query(True),
                             limit: int = Query(0, ge=0)):
    """Detect the ATS for stored companies and activate the ones that resolve.

    Seeded companies land with ats_platform='unknown' and crawl_status='paused',
    which makes them invisible to the crawler until this has run."""
    return enqueue_run("detect_ats", only_unknown=only_unknown, limit=limit)


@router.post("/api/companies/discover")
async def api_discover_companies(
    sources: str = Query("yc,remoteintech,wwr"),
    detect_ats: bool = Query(True),
    min_team_size: int = Query(10, ge=1),
):
    """Bulk discover companies from YC, RemoteInTech, WeWorkRemotely."""
    source_list = [s.strip() for s in sources.split(",") if s.strip()]
    return enqueue_run("discover", sources=source_list,
                    detect_ats=detect_ats, min_team_size=min_team_size)


