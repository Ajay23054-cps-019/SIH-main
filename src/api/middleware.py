"""Middleware wiring: CORS for the local dashboard frontend.

The tool runs fully offline; the dashboard is served on a neighbouring
localhost port, so permissive local CORS is the point — there is no public
surface to protect in the MVP deployment model.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def install_middleware(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # localhost-only deployment (MVP)
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
