from pathlib import Path
from typing import Optional, Union

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from src.api.errors import install_error_handlers
from src.api.models import envelope
from src.api.routes import router
from src.dashboard.routes import router as dashboard_router

DEFAULT_DB_PATH = Path("data/sat_sa.db")


def create_app(db_path: Optional[Union[str, Path]] = None) -> FastAPI:
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    app = FastAPI(
        title="SAT-SA",
        description="Supervisory Analytics Tool for SOC Assessment",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.state.db_path = str(db_path)

    install_error_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    def health():
        data = {"status": "ok", "version": "0.1.0", "service": "SAT-SA"}
        try:
            from src.storage.db import table_counts
            data["table_counts"] = table_counts(db_path)
        except Exception:
            data["table_counts"] = {}
        return JSONResponse(envelope(data=data))

    @app.get("/", tags=["system"])
    def root():
        return JSONResponse(envelope(data={
            "name": "SAT-SA",
            "version": "0.1.0",
            "description": "Supervisory Analytics Tool for SOC Assessment",
            "docs": "/docs",
            "health": "/health",
        }))

    api_router = router
    app.include_router(api_router)

    dashboard_dir = Path(__file__).resolve().parent.parent / "dashboard"
    static_dir = dashboard_dir / "static"
    if static_dir.exists():
        app.mount("/dashboard/static", StaticFiles(directory=str(static_dir)), name="dashboard-static")

    app.include_router(dashboard_router)

    return app


app = create_app()
