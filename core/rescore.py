"""Re-score every stored job against the active profile.

Extracted from the inline endpoint body in main.py so the run engine can execute
it as a tracked background job (it can take a while on a large jobs table, and
the delete_below_min variant is destructive enough to deserve a history entry).
"""

from __future__ import annotations

from core import runlog
from core.database import get_connection
from core.profile import get_active_profile
from core.scorer import score_job


def rescore_all_jobs(delete_below_min: bool = False) -> dict:
    profile = get_active_profile()
    profile_id = profile.get("_id")
    min_store = int((profile.get("scoring") or {}).get("min_score_to_store", 25))

    runlog.log(f"Re-scoring against profile: {profile.get('_name')}")
    if delete_below_min:
        runlog.warn(f"Jobs scoring below {min_store} will be DELETED")

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, title, description, location, tech_stack FROM jobs"
        ).fetchall()
    finally:
        conn.close()

    total = len(rows)
    runlog.log(f"Scanning {total} jobs")

    updated = 0
    deleted = 0
    conn = get_connection()
    try:
        for i, r in enumerate(rows, 1):
            result = score_job(
                r["title"], r["description"] or "", r["location"] or "", profile=profile
            )

            if delete_below_min and result["score"] < min_store:
                conn.execute("DELETE FROM jobs WHERE id = ?", (r["id"],))
                deleted += 1
            else:
                existing_tech = {
                    t.strip() for t in (r["tech_stack"] or "").split(",") if t.strip()
                }
                existing_tech.update(result["tech_stack"])
                conn.execute(
                    "UPDATE jobs SET relevance_score = ?, experience_level = ?, "
                    "india_friendly = ?, location_note = ?, tech_stack = ?, "
                    "scored_profile_id = ? WHERE id = ?",
                    (result["score"], result["experience_level"],
                     result["india_friendly"], result["location_note"],
                     ", ".join(sorted(existing_tech)), profile_id, r["id"]),
                )
                updated += 1

            if i % 50 == 0 or i == total:
                runlog.progress(i, total, f"Re-scoring jobs ({i}/{total})")
        conn.commit()
    finally:
        conn.close()

    runlog.log(f"Re-scored {updated} jobs, deleted {deleted}")
    return {"scanned": total, "updated": updated, "deleted": deleted}
