"""Profiles: the targeting and scoring configuration."""


from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from api.deps import enqueue_run
from core.profile import (
    activate_profile,
    create_profile,
    delete_profile,
    duplicate_profile,
    export_profile,
    get_active_profile,
    get_profile,
    import_preset,
    list_presets,
    list_profiles,
    update_profile,
)

router = APIRouter()

@router.get("/api/profiles")
async def api_list_profiles():
    return {"profiles": list_profiles(), "presets": list_presets()}


@router.get("/api/profiles/active")
async def api_active_profile():
    cfg = get_active_profile()
    return {
        "id": cfg.get("_id"),
        "name": cfg.get("_name"),
        "config": {k: v for k, v in cfg.items() if not k.startswith("_")},
    }


@router.get("/api/profiles/{pid}")
async def api_get_profile(pid: int):
    row = get_profile(pid)
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    return row


class ProfileInput(BaseModel):
    name: str
    description: str = ""
    config: dict


class ProfileUpdate(BaseModel):
    """Partial update. core.profile.update_profile already skips None fields,
    so the UI can save just the config without resending name/description."""
    name: str | None = None
    description: str | None = None
    config: dict | None = None


@router.post("/api/profiles")
async def api_create_profile(body: ProfileInput):
    try:
        pid = create_profile(body.name, body.config, body.description)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"id": pid, "ok": True}


@router.put("/api/profiles/{pid}")
async def api_update_profile(pid: int, body: ProfileUpdate):
    if not get_profile(pid):
        raise HTTPException(status_code=404, detail="Profile not found")
    if body.config is None and body.name is None and body.description is None:
        raise HTTPException(status_code=400, detail="Nothing to update")
    update_profile(pid, config=body.config, name=body.name,
                   description=body.description)
    return {"ok": True}


@router.post("/api/profiles/{pid}/activate")
async def api_activate_profile(pid: int):
    try:
        activate_profile(pid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    # Queries now live on the profile itself — no separate seeding needed.
    queries_count = len((get_profile(pid) or {}).get("config", {}).get("search", {}).get("jsearch_default_queries") or [])
    return {"ok": True, "active": pid, "queries": queries_count}


@router.post("/api/profiles/{pid}/duplicate")
async def api_duplicate_profile(pid: int, name: str | None = Query(None)):
    try:
        new_id = duplicate_profile(pid, new_name=name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"ok": True, "id": new_id}


@router.delete("/api/profiles/{pid}")
async def api_delete_profile(pid: int):
    try:
        delete_profile(pid)
    except ValueError as e:
        # Thrown when trying to delete the active profile
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


class PresetImport(BaseModel):
    preset_slug: str
    activate: bool = False
    overwrite: bool = False


@router.post("/api/profiles/import")
async def api_import_preset(body: PresetImport):
    try:
        pid = import_preset(body.preset_slug, activate=body.activate,
                            overwrite=body.overwrite)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    queries_count = len((get_profile(pid) or {}).get("config", {}).get("search", {}).get("jsearch_default_queries") or [])
    return {"ok": True, "id": pid, "queries": queries_count}


@router.get("/api/profiles/{pid}/export")
async def api_export_profile(pid: int):
    try:
        yaml_text = export_profile(pid)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return PlainTextResponse(yaml_text, media_type="application/x-yaml")


@router.post("/api/profiles/rescore-all")
async def api_rescore_all(delete_below_min: bool = Query(False)):
    """Re-score every job against the active profile. Runs in the background -
    poll the returned run_id. Implementation lives in core/rescore.py."""
    return enqueue_run("rescore", delete_below_min=delete_below_min)


