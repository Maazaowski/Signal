"""Shared pieces the routers depend on.

Kept here rather than in main.py so a router never has to import the
application object — that would be a circular dependency and would couple every
route module to app assembly.
"""


import hashlib
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates

from core import runs as run_engine
from core import settings_store as settings

APP_VERSION = "4.0.0"

templates = Jinja2Templates(directory="templates")

_STATIC = Path(__file__).parent.parent / "static"


def asset_stamp() -> str:
    """Cache-busting token derived from the static files themselves.

    A hand-maintained version constant meant every stylesheet edit shipped
    behind a stale cached copy until someone remembered to bump it.
    """
    h = hashlib.sha1()
    for path in sorted(_STATIC.rglob("*")):
        if path.is_file():
            h.update(path.name.encode())
            h.update(str(path.stat().st_mtime_ns).encode())
    return h.hexdigest()[:8]


def page_context(request: Request, page: str, **extra) -> dict:
    """Context every page template needs. The product name comes from settings,
    so renaming it in the UI updates the sidebar and the tab title everywhere."""
    ctx = {
        "page": page,
        "v": asset_stamp(),
        "product_name": settings.get("product_name"),
    }
    ctx.update(extra)
    return ctx


def enqueue_run(kind: str, **kwargs) -> dict:
    """Start a background run and return its id immediately.

    409 when something is already running: only one run executes at a time, so
    a second start would either be silently dropped or double-spend the API
    quota. Saying so is better than either.
    """
    try:
        run_id = run_engine.enqueue(kind, trigger="manual", **kwargs)
    except run_engine.RunBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"ok": True, "run_id": run_id, "status": "queued", "kind": kind}
