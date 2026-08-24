"""Canonical SAT-SA data schema.

All ingestion formats (CSV, JSON, JSONL) are normalized into these Pydantic
models before any analytics run. Analytics code depends only on this module,
never on raw input formats.

Design rules (see phases.md):
- Fields are Optional with None defaults: missing data is None, never "" or -1.
- Invalid values are normalized where safe; impossible timestamp orderings
  (close before open) are the only hard failures.
- Referential integrity is a *data-quality* concern handled at ingestion,
  not enforced here.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Dict, List, Optional

import pandas as pd
from pydantic import BaseModel, Field, field_validator, model_validator

SEVERITY_LEVELS = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
ALERT_STATUSES = ("open", "investigating", "escalated", "closed")

_SEVERITY_ALIASES = {
    "CRIT": "CRITICAL",
    "CRITICAL": "CRITICAL",
    "HIGH": "HIGH",
    "MED": "MEDIUM",
    "MEDIUM": "MEDIUM",
    "LOW": "LOW",
}


def _normalize_severity(value: Optional[str]) -> Optional[str]:
    """Uppercase/alias-map severity. Unknown values pass through unchanged."""
    if value is None:
        return None
    stripped = str(value).strip()
    if not stripped:
        return None
    return _SEVERITY_ALIASES.get(stripped.upper(), stripped.upper())


class CSEMetadata(BaseModel):
    """Entity-level metadata for a Critical Sector Entity."""

    cse_id: str
    name: Optional[str] = None
    sector: Optional[str] = None  # Telecom, Financial, Power, ...
    size_band: Optional[str] = None  # Small, Medium, Large
    claimed_capabilities: Optional[Dict[str, Any]] = None
    submitted_at: Optional[datetime] = None


class Alert(BaseModel):
    alert_id: str
    cse_id: str
    timestamp: Optional[datetime] = None
    severity: Optional[str] = None  # CRITICAL, HIGH, MEDIUM, LOW
    category: Optional[str] = None  # malware, authentication, network, endpoint, ...
    asset_id: Optional[str] = None
    status: Optional[str] = None  # open, investigating, escalated, closed
    closure_timestamp: Optional[datetime] = None
    description: Optional[str] = None

    @field_validator("severity")
    @classmethod
    def _severity(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_severity(v)

    @field_validator("status")
    @classmethod
    def _status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        stripped = str(v).strip().lower()
        return stripped or None

    @model_validator(mode="after")
    def _closure_after_creation(self) -> "Alert":
        if (
            self.timestamp is not None
            and self.closure_timestamp is not None
            and self.closure_timestamp < self.timestamp
        ):
            raise ValueError(
                f"Alert {self.alert_id}: closure_timestamp precedes timestamp"
            )
        return self


class Investigation(BaseModel):
    investigation_id: str
    alert_id: Optional[str] = None
    cse_id: Optional[str] = None
    timestamp_open: Optional[datetime] = None
    timestamp_close: Optional[datetime] = None
    evidence_entries: int = 0
    assigned_to: Optional[str] = None
    notes: Optional[str] = None
    depth_score: Optional[float] = None

    @field_validator("evidence_entries", mode="before")
    @classmethod
    def _non_negative(cls, v: Any) -> Any:
        if isinstance(v, (int, float)) and v < 0:
            raise ValueError("evidence_entries cannot be negative")
        return v

    @model_validator(mode="after")
    def _close_after_open(self) -> "Investigation":
        if (
            self.timestamp_open is not None
            and self.timestamp_close is not None
            and self.timestamp_close < self.timestamp_open
        ):
            raise ValueError(
                f"Investigation {self.investigation_id}: "
                "timestamp_close precedes timestamp_open"
            )
        return self


class Escalation(BaseModel):
    escalation_id: str
    investigation_id: Optional[str] = None
    cse_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    decision: Optional[str] = None  # escalated, not_escalated, escalated_with_action
    has_followup: bool = False
    recipient: Optional[str] = None
    rationale: Optional[str] = None

    @field_validator("decision")
    @classmethod
    def _decision(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        stripped = str(v).strip().lower()
        return stripped or None


class Case(BaseModel):
    case_id: str
    related_alerts: List[str] = Field(default_factory=list)
    cse_id: Optional[str] = None
    case_type: Optional[str] = None
    severity: Optional[str] = None
    closure_time: Optional[datetime] = None
    resolution: Optional[str] = None

    @field_validator("severity")
    @classmethod
    def _severity(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_severity(v)


class Asset(BaseModel):
    asset_id: str
    cse_id: str
    asset_type: Optional[str] = None  # server, endpoint, network_device, database
    criticality: Optional[str] = None  # CRITICAL, HIGH, MEDIUM, LOW
    environment: Optional[str] = None  # production, staging, development
    monitoring_status: Optional[str] = None  # monitored, partially_monitored, unmonitored

    @field_validator("criticality")
    @classmethod
    def _criticality(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_severity(v)


class Dataset(BaseModel):
    """Container for one CSE submission (or any collection of records).

    Every entity list defaults to empty so analytics can run on partial
    submissions without crashing.
    """

    cse_metadata: List[CSEMetadata] = Field(default_factory=list)
    alerts: List[Alert] = Field(default_factory=list)
    investigations: List[Investigation] = Field(default_factory=list)
    escalations: List[Escalation] = Field(default_factory=list)
    cases: List[Case] = Field(default_factory=list)
    assets: List[Asset] = Field(default_factory=list)

    ENTITY_FIELDS: ClassVar[tuple] = (
        "cse_metadata",
        "alerts",
        "investigations",
        "escalations",
        "cases",
        "assets",
    )

    def to_pandas(self) -> Dict[str, pd.DataFrame]:
        """Convert every entity list to a DataFrame.

        Returns a dict keyed by entity-field name. Empty lists produce an
        empty (zero-row) DataFrame rather than an error, so downstream
        profiling can rely on consistent keys.
        """
        frames: Dict[str, pd.DataFrame] = {}
        for field_name in self.ENTITY_FIELDS:
            records = getattr(self, field_name)
            rows = [r.model_dump(mode="python") for r in records]
            columns = list(type(records[0]).model_fields.keys()) if records else []
            frames[field_name] = pd.DataFrame(rows, columns=columns)
        return frames

    def summary(self) -> Dict[str, int]:
        """Record counts per entity type — quick ingestion sanity check."""
        return {f: len(getattr(self, f)) for f in self.ENTITY_FIELDS}
