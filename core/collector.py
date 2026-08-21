"""Orchestrates fetching from all sources, scoring, dedup, and storage.
Two tracks: job boards (existing) + company ATS crawling (new)."""

import asyncio
from datetime import datetime

from core import settings_store as settings
from core.database import (
    cleanup_old_jobs,
    get_companies,
    init_db,
    insert_job,
    update_company_crawl_status,
)
from core.models import Job
from core.profile import get_active_profile

# Retention and crawl concurrency are settings now (Settings -> Data / Crawling),
# read at point of use so a change applies to the very next run.
from core.runlog import log, progress  # noqa: F401  (shared seam: stdout + ring buffer + run_logs)
from core.scorer import score_job
from sources.arbeitnow import ArbeitnowSource
from sources.ashby import AshbySource
from sources.greenhouse import GreenhouseSource
from sources.html_scraper import HTMLCareerSource
from sources.jsearch import JSearchSource
from sources.lever import LeverSource
from sources.remoteok import RemoteOKSource
from sources.remotive import RemotiveSource


def _build_job_board_sources() -> list:
    """Build the list of sources fresh each run so JSearch uses current queries."""
    sources = [
        RemotiveSource(),
        RemoteOKSource(),
        ArbeitnowSource(),
    ]
    if settings.get("rapidapi_key"):
        # Queries come from the active profile (single source of truth).
        profile = get_active_profile()
        profile_queries = (profile.get("search") or {}).get("jsearch_default_queries") or []
        queries = [
            {
                "query": q["query"],
                "country": q.get("country") or settings.get("search_country"),
                "date_posted": q.get("date_posted", "3days"),
                **({"remote_jobs_only": "true"} if q.get("remote_jobs_only") else {}),
            }
            for q in profile_queries
            if q.get("query") and q.get("enabled", True)
        ]
        if queries:
            sources.append(JSearchSource(queries=queries))
    return sources


def _make_ats_source(company: dict):
    """Factory: return the right source class for a company's ATS."""
    platform = company.get("ats_platform", "unknown")
    if platform == "greenhouse":
        return GreenhouseSource(company)
    elif platform == "lever":
        return LeverSource(company)
    elif platform == "ashby":
        return AshbySource(company)
    elif platform == "html":
        return HTMLCareerSource(company)
    return None


async def _fetch_from_source(source) -> list[Job]:
    """Fetch jobs from a single source with error handling."""
    try:
        jobs = await source.fetch()
        log(f"  [OK] {source.name}: {len(jobs)} jobs fetched")
        return jobs
    except Exception as e:
        log(f"  [FAIL] {source.name}: {e}")
        return []


def _score_and_store(jobs: list[Job], stats: dict, profile: dict = None):
    """Score, filter, deduplicate, and store jobs. Shared by both tracks."""
    stats.setdefault("filtered_out", 0)
    profile = profile or get_active_profile()
    profile_id = profile.get("_id")
    min_store = int((profile.get("scoring") or {}).get("min_score_to_store", 25))

    for job in jobs:
        result = score_job(job.title, job.description, job.location, profile=profile)

        # Filter: drop irrelevant jobs before storing (saves DB space)
        if result["score"] < min_store:
            stats["filtered_out"] += 1
            continue

        job.relevance_score = result["score"]
        job.experience_level = result["experience_level"]
        job.location_fit = result["location_fit"]
        job.location_note = result["location_note"]

        existing_tech = {t.strip() for t in job.tech_stack.split(",") if t.strip()}
        existing_tech.update(result["tech_stack"])
        job.tech_stack = ", ".join(sorted(existing_tech))

        if not job.company_domain:
            job.company_domain = job.extract_domain()

        job_dict = job.model_dump()
        job_dict["id"] = job.fingerprint
        job_dict["discovered_at"] = datetime.utcnow().isoformat()
        job_dict["scored_profile_id"] = profile_id

        result_status = insert_job(job_dict)
        if result_status == "new":
            stats["new"] += 1
        else:
            stats["updated"] = stats.get("updated", 0) + 1


async def run_company_crawl(company_ids: list[str] = None) -> dict:
    """Track B: crawl jobs from companies in the DB."""
    init_db()
    log("Starting company crawl...")
    stats = {"fetched": 0, "new": 0, "updated": 0, "filtered_out": 0, "sources": {},
             "companies_crawled": 0, "companies_failed": 0}

    companies = get_companies(crawl_status="active")
    if company_ids:
        companies = [c for c in companies if c["id"] in company_ids]

    if not companies:
        log("  No active companies to crawl. Seed first with /api/companies/seed")
        return stats

    log(f"  Crawling {len(companies)} companies...")
    total_companies = len(companies)
    done_count = 0
    semaphore = asyncio.Semaphore(settings.get("crawl_concurrency"))

    async def crawl_one(company: dict) -> list[Job]:
        nonlocal done_count
        source = _make_ats_source(company)
        if not source:
            done_count += 1
            progress(done_count, total_companies, f"Skipped {company['name']}")
            return []
        async with semaphore:
            try:
                jobs = await source.fetch()
                update_company_crawl_status(
                    company["id"], "active", datetime.utcnow().isoformat()
                )
                log(f"  [OK] {company['name']} ({company['ats_platform']}): {len(jobs)} jobs")
                done_count += 1
                progress(done_count, total_companies, f"Crawled {company['name']}")
                stats["companies_crawled"] += 1
                stats["sources"][f"{company['ats_platform']}:{company['ats_slug']}"] = len(jobs)
                return jobs
            except Exception as e:
                update_company_crawl_status(
                    company["id"], "failed", datetime.utcnow().isoformat()
                )
                log(f"  [FAIL] {company['name']}: {e}", level="warn")
                done_count += 1
                progress(done_count, total_companies, f"Failed {company['name']}")
                stats["companies_failed"] += 1
                return []

    tasks = [crawl_one(c) for c in companies]
    results = await asyncio.gather(*tasks)

    all_jobs = [job for batch in results for job in batch]
    stats["fetched"] = len(all_jobs)

    log(f"  Total from companies: {len(all_jobs)}")
    profile = get_active_profile()
    _score_and_store(all_jobs, stats, profile=profile)

    log(f"  Companies crawled: {stats['companies_crawled']}")
    log(f"  Companies failed: {stats['companies_failed']}")
    log(f"  New: {stats['new']} | Updated: {stats.get('updated', 0)} | Filtered out: {stats.get('filtered_out', 0)}")
    return stats


async def run_job_boards() -> dict:
    """Track A: fetch from existing job boards."""
    stats = {"fetched": 0, "new": 0, "updated": 0, "filtered_out": 0, "sources": {}}

    sources = _build_job_board_sources()
    tasks = [_fetch_from_source(src) for src in sources]
    results = await asyncio.gather(*tasks)

    all_jobs: list[Job] = []
    for source, jobs in zip(sources, results, strict=False):
        stats["sources"][source.name] = len(jobs)
        all_jobs.extend(jobs)

    stats["fetched"] = len(all_jobs)
    profile = get_active_profile()
    _score_and_store(all_jobs, stats, profile=profile)
    return stats


async def run_collection(include_companies: bool = True) -> dict:
    """Run full collection: job boards + company crawl."""
    init_db()
    log("=" * 50)
    log("Starting full collection...")

    # Track A: job boards
    log("\n--- Job Boards ---")
    board_stats = await run_job_boards()

    # Track B: company crawl
    company_stats = {"fetched": 0, "new": 0, "updated": 0, "filtered_out": 0,
                     "companies_crawled": 0, "companies_failed": 0}
    if include_companies:
        log("\n--- Company Crawl ---")
        company_stats = await run_company_crawl()

    # Cleanup: forget roles not seen recently (Settings -> Data)
    stale_days = settings.get("stale_job_days")
    log(f"\n--- Cleanup (roles not seen for {stale_days} days) ---")
    deleted = cleanup_old_jobs(days=stale_days)
    log(f"  Deleted {deleted} stale jobs")

    # Merge stats
    total = {
        "fetched": board_stats["fetched"] + company_stats["fetched"],
        "new": board_stats["new"] + company_stats["new"],
        "updated": board_stats.get("updated", 0) + company_stats.get("updated", 0),
        "filtered_out": board_stats.get("filtered_out", 0) + company_stats.get("filtered_out", 0),
        "deleted_stale": deleted,
        "board_sources": board_stats["sources"],
        "companies_crawled": company_stats.get("companies_crawled", 0),
        "companies_failed": company_stats.get("companies_failed", 0),
    }

    log("\n--- Summary ---")
    log(f"  Total fetched: {total['fetched']}")
    log(f"  New: {total['new']} | Updated (already existed): {total['updated']}")
    log(f"  Filtered out (low score): {total['filtered_out']}")
    log(f"  Deleted (stale): {total['deleted_stale']}")
    log("Collection complete!")
    log("=" * 50)
    return total
