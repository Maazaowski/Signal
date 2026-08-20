"""Detect which ATS the stored companies use, and activate the ones that resolve.

Why this exists: `mega_companies.get_all_mega_companies()` seeds every company
with `ats_platform="unknown"` and `crawl_status="paused"`, commented "paused
until ATS detected". Nothing ever performed that detection for seeded companies —
`batch_detect_ats` in core/bulk_discover.py was only called for newly *discovered*
companies. The result was 210 companies sitting inert in the database and a
company crawl that logged "No active companies to crawl" and collected nothing.

This module closes that loop: probe the unknown companies, store whatever ATS is
found, and flip those to `active` so the crawler will actually visit them.
"""

from __future__ import annotations

from core import runlog
from core.bulk_discover import batch_detect_ats
from core.database import get_companies, get_connection


def _set_ats(company_id: str, platform: str, slug: str, status: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE companies SET ats_platform=?, ats_slug=?, crawl_status=? WHERE id=?",
            (platform, slug, status, company_id),
        )
        conn.commit()
    finally:
        conn.close()


async def detect_ats_for_stored(only_unknown: bool = True,
                                limit: int = 0,
                                concurrency: int = 10) -> dict:
    """Probe stored companies for a Greenhouse/Lever/Ashby board.

    Companies with a detected ATS become `active` (crawlable). Companies with no
    detectable board stay `paused` — they are not deleted, so a later run or a
    manual careers_url can still rescue them.
    """
    companies = get_companies(limit=5000)
    if only_unknown:
        companies = [c for c in companies if (c.get("ats_platform") or "unknown") == "unknown"]
    if limit:
        companies = companies[:limit]

    total = len(companies)
    if not total:
        runlog.log("No companies need ATS detection - all already resolved.")
        return {"checked": 0, "detected": 0, "activated": 0, "still_unknown": 0}

    runlog.log(f"Probing {total} companies for a Greenhouse/Lever/Ashby board")
    runlog.progress(0, total, f"Detecting ATS (0/{total})")

    # Process in chunks so progress advances while the work happens.
    # batch_detect_ats only returns once its whole batch is done, so handing it
    # all 210 companies at once would leave the progress bar at 0 until the end.
    detected = 0
    checked = 0
    by_platform: dict[str, int] = {}
    CHUNK = 20

    for start in range(0, total, CHUNK):
        batch = [dict(c) for c in companies[start:start + CHUNK]]
        results = await batch_detect_ats(batch, concurrency=concurrency)

        for c in results:
            platform = c.get("ats_platform") or "unknown"
            if platform != "unknown":
                _set_ats(c["id"], platform, c.get("ats_slug", ""), "active")
                detected += 1
                by_platform[platform] = by_platform.get(platform, 0) + 1
        checked += len(results)
        runlog.progress(checked, total, f"Detecting ATS ({checked}/{total}, {detected} found)")

    still_unknown = total - detected
    runlog.log(
        f"ATS detection complete: {detected} of {total} companies are now crawlable "
        f"({by_platform or 'none'}); {still_unknown} have no public board."
    )
    if detected == 0:
        runlog.warn(
            "No ATS boards were detected. These companies cannot be crawled - "
            "the free job boards remain your only source."
        )

    return {
        "checked": total,
        "detected": detected,
        "activated": detected,
        "still_unknown": still_unknown,
        "by_platform": by_platform,
    }
