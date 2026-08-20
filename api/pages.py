"""The pages themselves. No business logic lives here."""


from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from api.deps import page_context, templates

router = APIRouter()

# ── UI Routes ──────────────────────────────────────────────────



@router.get("/", response_class=HTMLResponse)
async def page_today(request: Request):
    return templates.TemplateResponse(request, "today.html", page_context(request, "today"))


@router.get("/roles", response_class=HTMLResponse)
async def page_roles(request: Request):
    return templates.TemplateResponse(request, "roles.html", page_context(request, "roles"))


@router.get("/intros", response_class=HTMLResponse)
async def page_intros(request: Request):
    return templates.TemplateResponse(request, "intros.html", page_context(request, "intros"))


@router.get("/companies", response_class=HTMLResponse)
async def page_companies(request: Request):
    return templates.TemplateResponse(request, "companies.html", page_context(request, "companies"))


@router.get("/activity", response_class=HTMLResponse)
async def page_activity(request: Request):
    return templates.TemplateResponse(request, "activity.html", page_context(request, "activity"))


@router.get("/settings", response_class=HTMLResponse)
async def page_settings(request: Request):
    return templates.TemplateResponse(request, "settings.html", page_context(request, "settings"))


# Older paths, kept working so bookmarks and the docs do not rot.
_MOVED = {
    "/jobs": "/roles",
    "/dashboard": "/roles",
    "/outreach": "/intros",
    "/automation": "/activity",
    "/profile": "/settings",
}

for _old, _new in _MOVED.items():
    def _redirect(_target=_new):
        async def handler():
            return RedirectResponse(_target, status_code=308)
        return handler
    router.get(_old, response_class=HTMLResponse)(_redirect())
