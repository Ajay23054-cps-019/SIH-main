"""Examiner feedback loop (post-MVP capability #7).

Examiners record a disposition per finding — worthwhile / not worthwhile /
uncertain — as they work the review queue. Feedback is stored one row per
finding (the latest disposition wins) and summarised per signal type as
*advisory* calibration guidance. The loop surfaces recommendations; it
never rewrites thresholds or scores by itself — a human applies any change
via ``data/config/thresholds.json``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

DISPOSITIONS = ("worthwhile", "not_worthwhile", "uncertain")

FEEDBACK_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS examiner_feedback (
    finding_id TEXT PRIMARY KEY,
    disposition TEXT NOT NULL,
    examiner TEXT,
    note TEXT,
    updated_at TEXT
)
"""


def store_feedback(db_path: Path, finding_id: str, disposition: str,
                   examiner: Optional[str] = None,
                   note: Optional[str] = None) -> Dict[str, Any]:
    """Upsert the disposition for one finding; returns the stored row."""
    from sqlalchemy import text

    from src.storage.db import get_engine

    if disposition not in DISPOSITIONS:
        raise ValueError(f"disposition must be one of {DISPOSITIONS}")
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row = {"finding_id": finding_id, "disposition": disposition,
           "examiner": examiner, "note": note, "updated_at": stamp}
    with get_engine(db_path).begin() as conn:
        conn.execute(text(FEEDBACK_TABLE_SQL))
        conn.execute(text(
            "INSERT OR REPLACE INTO examiner_feedback "
            "(finding_id, disposition, examiner, note, updated_at) VALUES "
            "(:finding_id, :disposition, :examiner, :note, :updated_at)"),
            row)
    return row


def load_feedback(db_path: Path, finding_id: Optional[str] = None) \
        -> List[Dict[str, Any]]:
    from src.storage.db import get_engine

    query = "SELECT * FROM examiner_feedback"
    params: Dict[str, Any] = {}
    if finding_id:
        query += " WHERE finding_id = :finding_id"
        params["finding_id"] = finding_id
    try:
        df = pd.read_sql(query, get_engine(db_path), params=params)
    except Exception:
        return []          # table not created yet -> no feedback
    return df.to_dict(orient="records")


def calibration_summary(findings: List[Any], feedback: List[Dict[str, Any]],
                        thresholds: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-signal-type disposition tallies + advisory calibration text.

    Pure: joins feedback rows to finding-like objects (finding_id,
    signal_type). A signal type only earns a recommendation once it has
    ``min_feedback`` dispositions; recommendations are strings for a human,
    never applied automatically.
    """
    t = thresholds["feedback"]
    signal_of = {f.finding_id: f.signal_type for f in findings}
    by_signal: Dict[str, Dict[str, Any]] = {}
    for row in feedback:
        sig = signal_of.get(row["finding_id"])
        if sig is None:
            continue          # feedback for a finding from an earlier run
        bucket = by_signal.setdefault(
            sig, {"worthwhile": 0, "not_worthwhile": 0, "uncertain": 0})
        if row["disposition"] in bucket:
            bucket[row["disposition"]] += 1

    out = []
    for sig in sorted(by_signal):
        b = by_signal[sig]
        n = sum(b.values())
        rate = b["worthwhile"] / n if n else 0.0
        advisory = None
        if n >= t["min_feedback"]:
            if rate < t["low_worthwhile_rate"]:
                advisory = (f"worthwhile rate {rate:.0%} over {n} "
                            "dispositions — consider tightening this "
                            "signal's thresholds or lowering its scoring "
                            "weight (apply via data/config/thresholds.json; "
                            "not applied automatically)")
            elif rate > t["high_worthwhile_rate"]:
                advisory = (f"worthwhile rate {rate:.0%} over {n} "
                            "dispositions — signal is earning its keep")
        out.append({
            "signal_type": sig, "n_feedback": n,
            "worthwhile": b["worthwhile"],
            "not_worthwhile": b["not_worthwhile"],
            "uncertain": b["uncertain"],
            "worthwhile_rate": round(rate, 4),
            "advisory": advisory,
        })
    out.sort(key=lambda r: (-(r["worthwhile_rate"] if r["n_feedback"] else 1),
                            r["signal_type"]))
    return out
