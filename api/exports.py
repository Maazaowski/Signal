"""Optional export of results to a spreadsheet."""


from fastapi import APIRouter, Query

from core import settings_store as settings
from core.sheets import export_to_sheet

router = APIRouter()

# ── Google Sheets Export ───────────────────────────────────────

@router.post("/api/export/sheets")
async def api_export_sheets(
    min_score: int = Query(0, ge=0, le=100),
    location_fit: str | None = None,
    source: str | None = None,
    search: str | None = None,
    tech: str | None = None,
    mode: str = Query("replace"),
    sheet_name: str = Query("Jobs"),
):
    import os
    creds = "credentials.json"
    sheet_id = settings.get("google_sheet_id")
    if not sheet_id:
        return {"error": "No Google Sheet configured. Add one in Settings -> Integrations."}
    if not os.path.exists(creds):
        return {"error": f"Credentials file not found: {creds}"}
    try:
        result = export_to_sheet(
            creds_file=creds, spreadsheet_id=sheet_id, sheet_name=sheet_name,
            min_score=min_score, location_fit=location_fit,
            source=source, search=search, tech=tech, mode=mode,
        )
        return result
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/export/sheets/status")
async def api_sheets_status():
    import os
    return {
        "configured": bool(settings.get("google_sheet_id")) and os.path.exists("credentials.json"),
        "sheet_id": (settings.get("google_sheet_id") or "")[:10] + "..." if settings.get("google_sheet_id") else "",
        "creds_exists": os.path.exists("credentials.json"),
    }


