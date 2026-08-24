"""Pydantic models + the uniform response envelope.

Every endpoint answers with ``{"data": ..., "meta": ..., "errors": [...]}``
so dashboard code can be written once against one shape.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def envelope(data: Any = None, meta: Optional[Dict[str, Any]] = None,
             errors: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """The one response shape every endpoint returns."""
    return {"data": data,
            "meta": {"generated_at": utc_now(), **(meta or {})},
            "errors": errors or []}


class AnalyticsRunRequest(BaseModel):
    """Body for POST /api/analytics/run (all fields optional)."""
    categories: Optional[List[str]] = Field(
        default=None,
        description="Restrict signals to these categories "
                    "(execution_gap, negative_space, behavioral_anomaly, "
                    "peer_deviation)")
    include_benchmarks: bool = True
    include_scores: bool = True


class JobStatus(BaseModel):
    job_id: str
    state: str                     # queued | running | done | failed
    steps: List[str] = Field(default_factory=list)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class HealthOut(BaseModel):
    status: str
    version: str
    database: str


class FindingOut(BaseModel):
    finding_id: str
    cse_id: str
    signal_type: str
    signal_category: str
    period: str
    severity: str
    confidence: float
    detection_logic: str = ""
    caveats: List[str] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)


CATEGORY_SLUGS = {
    "execution-gaps": "execution_gap",
    "negative-space": "negative_space",
    "behavioral-anomalies": "behavioral_anomaly",
    "peer-deviations": "peer_deviation",
}

# Friendly trend-metric aliases -> profile metric keys.
METRIC_ALIASES = {
    "investigation_depth": "inv_depth_mean",
    "investigation_depth_mean": "inv_depth_mean",
    "closure_velocity": "closure_velocity_median_h",
    "escalation_rate": "esc_rate",
    "alert_volume": "alert_volume_total",
}
