"""Finding assembly: store, rehydrate, and look up findings as objects.

The signal engine writes rows; this module is the object-facing half —
turning ``findings`` table rows back into :class:`Finding` instances so the
tracer and (later) the API work with real objects instead of JSON blobs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.analytics.finding import Finding

_JSON_COLUMNS = {
    "evidence": "evidence_json",
    "contributing_record_ids": "contributing_record_ids_json",
    "caveats": "caveats_json",
    "recommended_actions": "recommended_actions_json",
    "data_quality_notes": "data_quality_notes_json",
}


def finding_from_row(row: Any) -> Finding:
    """Rebuild a Finding from a ``findings`` table row (Series or mapping)."""
    def get(key: str, default=None):
        if hasattr(row, "get"):
            value = row.get(key, default)
        else:
            value = getattr(row, key, default)
        return default if value is None else value

    finding = Finding(
        finding_id=get("finding_id"),
        cse_id=get("cse_id"),
        signal_type=get("signal_type"),
        signal_category=get("signal_category"),
        period=get("period"),
        severity=get("severity"),
        confidence=float(get("confidence", 0.0)),
        evidence=json.loads(get("evidence_json") or "{}"),
        contributing_record_ids=json.loads(
            get("contributing_record_ids_json") or "[]"),
        detection_logic=get("detection_logic") or "",
        caveats=json.loads(get("caveats_json") or "[]"),
        recommended_actions=json.loads(get("recommended_actions_json") or "[]"),
        data_quality_notes=json.loads(get("data_quality_notes_json") or "[]"),
        created_at=get("created_at"),
    )
    # The standard caveat is re-inserted by __post_init__; avoid duplication.
    return finding


def load_findings_as_objects(
    db_path: Path,
    finding_id: Optional[str] = None,
    cse_id: Optional[str] = None,
    category: Optional[str] = None,
) -> List[Finding]:
    """Query the findings table and return hydrated Finding objects."""
    from sqlalchemy import text

    from src.storage.db import get_engine

    clauses, params = [], {}
    if finding_id:
        clauses.append("finding_id = :finding_id")
        params["finding_id"] = finding_id
    if cse_id:
        clauses.append("cse_id = :cse_id")
        params["cse_id"] = cse_id
    if category:
        clauses.append("signal_category = :category")
        params["category"] = category
    query = "SELECT * FROM findings"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    engine = get_engine(db_path)
    try:
        df = pd.read_sql(text(query), engine, params=params)
    except Exception:
        return []  # no findings table yet
    return [finding_from_row(row) for _, row in df.iterrows()]


def get_finding(db_path: Path, finding_id: str) -> Optional[Finding]:
    matches = load_findings_as_objects(db_path, finding_id=finding_id)
    return matches[0] if matches else None
