"""Signal fusion: group corroborating findings into supervisory cases.

Individual signals are narrow lenses; an entity that trips several lenses
across *different* categories is a stronger supervisory concern than any
single finding. ``fuse_cases`` runs after the signal engine and groups a
CSE's findings into at most one case per CSE when they clear the fusion
gates (``thresholds["fusion"]``).

Joint confidence is a noisy-OR over member confidences — an upper bound,
since member signals share underlying records. That caveat ships with the
case. A case orders review; it is never a compliance determination.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

CASES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS supervisory_cases (
    case_id TEXT PRIMARY KEY,
    cse_id TEXT NOT NULL,
    finding_ids_json TEXT,
    signal_types_json TEXT,
    categories_json TEXT,
    n_findings INTEGER,
    joint_confidence REAL,
    severity TEXT,
    narrative TEXT,
    caveats_json TEXT,
    created_at TEXT
)
"""

_SEV_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

INDEPENDENCE_CAVEAT = (
    "Joint confidence assumes member signals are independent; they share "
    "underlying records, so treat it as an upper bound."
)
FRAMING_CAVEAT = (
    "A supervisory case aggregates potential concerns for review ordering; "
    "it is not a determination of non-compliance."
)


@dataclass
class SupervisoryCase:
    case_id: str            # CASE-<cse_id>; at most one case per CSE
    cse_id: str
    finding_ids: List[str] = field(default_factory=list)
    signal_types: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    n_findings: int = 0
    joint_confidence: float = 0.0
    severity: str = "LOW"
    narrative: str = ""
    caveats: List[str] = field(default_factory=list)
    created_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "cse_id": self.cse_id,
            "finding_ids": self.finding_ids,
            "signal_types": self.signal_types,
            "categories": self.categories,
            "n_findings": self.n_findings,
            "joint_confidence": self.joint_confidence,
            "severity": self.severity,
            "narrative": self.narrative,
            "caveats": self.caveats,
            "created_at": self.created_at,
        }


def noisy_or(confidences: List[float]) -> float:
    """Probability at least one member fires, assuming independence."""
    joint_absent = 1.0
    for c in confidences:
        joint_absent *= 1.0 - min(max(float(c), 0.0), 1.0)
    return round(1.0 - joint_absent, 4)


def fuse_cases(findings: List[Any],
               thresholds: Dict[str, Dict[str, Any]]) -> List[SupervisoryCase]:
    """Group findings per CSE into a case when corroboration clears the gates.

    Pure: takes finding-like objects (finding_id, cse_id, signal_type,
    signal_category, severity, confidence) and the loaded thresholds.
    """
    t = thresholds["fusion"]
    by_cse: Dict[str, List[Any]] = {}
    for f in findings:
        by_cse.setdefault(f.cse_id, []).append(f)

    cases: List[SupervisoryCase] = []
    for cse_id in sorted(by_cse):
        members = by_cse[cse_id]
        categories = sorted({m.signal_category for m in members})
        if len(members) < t["min_findings"]:
            continue
        if len(categories) < t["min_categories"]:
            continue

        members.sort(key=lambda m: (-_SEV_RANK.get(m.severity, 0),
                                    -m.confidence))
        strongest = members[0]
        joint = noisy_or([m.confidence for m in members])
        cats_txt = ", ".join(categories)
        narrative = (
            f"{len(members)} findings across {len(categories)} signal "
            f"categories ({cats_txt}) converge on this entity — joint "
            f"confidence {joint:.2f} (noisy-OR). Strongest member: "
            f"{strongest.signal_type} ({strongest.severity}, confidence "
            f"{strongest.confidence:.2f}). Corroboration across independent "
            "lenses is what separates a supervisory case from a one-off "
            "anomaly."
        )
        cases.append(SupervisoryCase(
            case_id=f"CASE-{cse_id}",
            cse_id=cse_id,
            finding_ids=[m.finding_id for m in members],
            signal_types=sorted({m.signal_type for m in members}),
            categories=categories,
            n_findings=len(members),
            joint_confidence=joint,
            severity=max(members, key=lambda m: _SEV_RANK.get(m.severity, 0)).severity,
            narrative=narrative,
            caveats=[INDEPENDENCE_CAVEAT, FRAMING_CAVEAT],
        ))
    return cases


# ---------------------------------------------------------------------------
# Persistence (same pattern as the findings table)
# ---------------------------------------------------------------------------

_CASE_COLUMNS = ("case_id", "cse_id", "finding_ids_json", "signal_types_json",
                 "categories_json", "n_findings", "joint_confidence",
                 "severity", "narrative", "caveats_json", "created_at")


def store_cases(cases: List[SupervisoryCase], db_path: Path) -> int:
    from sqlalchemy import text

    from src.storage.db import get_engine

    engine = get_engine(db_path)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with engine.begin() as conn:
        conn.execute(text(CASES_TABLE_SQL))
        for c in cases:
            if not c.created_at:
                c.created_at = stamp
            row = c.to_dict()
            params = {
                "case_id": row["case_id"], "cse_id": row["cse_id"],
                "finding_ids_json": json.dumps(row["finding_ids"]),
                "signal_types_json": json.dumps(row["signal_types"]),
                "categories_json": json.dumps(row["categories"]),
                "n_findings": row["n_findings"],
                "joint_confidence": row["joint_confidence"],
                "severity": row["severity"],
                "narrative": row["narrative"],
                "caveats_json": json.dumps(row["caveats"]),
                "created_at": row["created_at"],
            }
            cols = ", ".join(_CASE_COLUMNS)
            binds = ", ".join(f":{c}" for c in _CASE_COLUMNS)
            conn.execute(text(
                f"INSERT OR REPLACE INTO supervisory_cases ({cols}) "
                f"VALUES ({binds})"), params)
    return len(cases)


def load_cases(db_path: Path, cse_id: Optional[str] = None) -> List[Dict[str, Any]]:
    from src.storage.db import get_engine

    query = "SELECT * FROM supervisory_cases"
    params: Dict[str, Any] = {}
    if cse_id:
        query += " WHERE cse_id = :cse_id"
        params["cse_id"] = cse_id
    try:
        df = pd.read_sql(query, get_engine(db_path), params=params)
    except Exception:
        return []          # table not created yet -> no cases
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "case_id": r["case_id"], "cse_id": r["cse_id"],
            "finding_ids": json.loads(r["finding_ids_json"]),
            "signal_types": json.loads(r["signal_types_json"]),
            "categories": json.loads(r["categories_json"]),
            "n_findings": int(r["n_findings"]),
            "joint_confidence": float(r["joint_confidence"]),
            "severity": r["severity"],
            "narrative": r["narrative"],
            "caveats": json.loads(r["caveats_json"]),
            "created_at": r["created_at"],
        })
    rows.sort(key=lambda c: (-_SEV_RANK.get(c["severity"], 0),
                             -c["joint_confidence"]))
    return rows


def clear_cases(db_path: Path) -> int:
    """Wipe stored cases (fusion is deterministic; a re-run replaces state)."""
    from sqlalchemy import text

    from src.storage.db import get_engine

    with get_engine(db_path).begin() as conn:
        conn.execute(text(CASES_TABLE_SQL))
        result = conn.execute(text("DELETE FROM supervisory_cases"))
    return getattr(result, "rowcount", 0) or 0
