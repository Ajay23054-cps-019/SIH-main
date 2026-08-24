"""Examiner dashboard: Jinja2 pages over the REST API (Phase 11).

Pages are thin shells rendered server-side; all data is fetched client-side
with vanilla ``fetch()`` from the API, so the dashboard can never show a
number that did not come through the same endpoint an auditor would call.
No build step, no CDN — Chart.js is bundled under static/js/lib/.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

DASHBOARD_DIR = Path(__file__).parent
TEMPLATES_DIR = DASHBOARD_DIR / "templates"
STATIC_DIR = DASHBOARD_DIR / "static"

router = APIRouter(prefix="/dashboard", include_in_schema=False)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
def portfolio_page(request: Request):
    return templates.TemplateResponse(request, "portfolio.html")


@router.get("/entity/{cse_id}", response_class=HTMLResponse)
def entity_page(request: Request, cse_id: str):
    return templates.TemplateResponse(request, "entity.html",
                                      {"cse_id": cse_id})


@router.get("/finding/{finding_id:path}", response_class=HTMLResponse)
def finding_page(request: Request, finding_id: str):
    # finding IDs contain a colon ("CSE-042:quality_degradation"); the
    # :path converter keeps them intact.
    return templates.TemplateResponse(request, "finding.html",
                                      {"finding_id": finding_id})
