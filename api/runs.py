"""Background runs: starting work, following progress, reading logs."""


from fastapi import APIRouter, HTTPException, Query

from api.deps import enqueue_run
from core import runlog
from core import runs as run_engine
from core.database import get_active_run, get_run, get_run_logs, get_runs

router = APIRouter()

# ── Runs (background jobs) ─────────────────────────────────────

@router.get("/api/runs")
async def api_runs(limit: int = Query(30, ge=1, le=200),
                   kind: str | None = None, status: str | None = None):
    return {
        "runs": get_runs(limit=limit, kind=kind, status=status),
        "active": get_active_run(),
        "kinds": run_engine.RUN_KINDS,
    }


@router.get("/api/runs/active")
async def api_run_active():
    return {"active": get_active_run()}


@router.get("/api/runs/{run_id}")
async def api_run_detail(run_id: int):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/api/runs/{run_id}/logs")
async def api_run_logs(run_id: int, after_id: int = Query(0, ge=0),
                       limit: int = Query(500, ge=1, le=2000)):
    if not get_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")
    logs = get_run_logs(run_id, after_id=after_id, limit=limit)
    return {"logs": logs, "last_id": logs[-1]["id"] if logs else after_id}


@router.post("/api/runs")
async def api_start_run(body: dict):
    kind = (body or {}).get("kind")
    if not kind:
        raise HTTPException(status_code=400, detail="kind is required")
    opts = {k: v for k, v in (body or {}).items() if k != "kind"}
    return enqueue_run(kind, **opts)


@router.post("/api/runs/{run_id}/cancel")
async def api_cancel_run(run_id: int):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run["status"] not in ("queued", "running"):
        raise HTTPException(status_code=400, detail="Run is not active")
    cancelled = run_engine.cancel_current()
    # The worker task is recreated so future runs still execute.
    await run_engine.start_worker()
    return {"ok": cancelled}


@router.get("/api/logs")
async def api_logs(limit: int = Query(200, ge=1, le=500),
                   level: str | None = None):
    """Global log tail - what the console shows, but readable from the UI."""
    return {"logs": runlog.tail(limit=limit, level=level)}


