"""FastAPI application factory for SAT-SA.

Run against the demo database with:

    uvicorn src.api.main:app --reload
    # Swagger UI at http://localhost:8000/docs

The app is a read-mostly window over the SQLite store the analytics
pipeline writes; POST /api/analytics/run triggers that same pipeline.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

from fastapi import FastAPI

from src.api.errors import install_error_handlers
from src.api.middleware import install_middleware
from src.api.routes import VERSION, router

DEFAULT_DB = Path("data/sat_sa.db")

DESCRIPTION = """
Supervisory Analytics Tool for SOC Assessment (SAT-SA) — NCIIPC examiner tooling.

All findings are framed as **potential supervisory concerns**, never
determinations of non-compliance. The attention ranking is a review
prioritization heuristic — **not** a risk or compliance score.
"""


def create_app(db_path: Union[str, Path, None] = None) -> FastAPI:
    """Build the app; ``db_path`` (or env SAT_SA_DB) selects the store."""
    resolved = Path(
        db_path
        or os.environ.get("SAT_SA_DB")
        or DEFAULT_DB
    )
    app = FastAPI(
        title="SAT-SA Supervisory Analytics API",
        version=VERSION,
        description=DESCRIPTION,
    )
    app.state.db_path = resolved
    install_middleware(app)
    install_error_handlers(app)
    app.include_router(router)

    @app.get("/health", tags=["system"])
    def root_health():
        from src.api.models import envelope
        from src.storage.db import table_counts

        return envelope({
            "status": "ok", "version": VERSION, "database": str(resolved),
            "table_counts": table_counts(resolved),
        })

    return app


app = create_app()
