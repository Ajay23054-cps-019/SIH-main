"""Supervisory Attention Priority: transparent ranking of CSEs for review.

This is a *prioritization heuristic*, deliberately not called a "risk
score" or "compliance score":

- A high priority means "look here first this review cycle".
- A low priority does NOT mean safe — it means lower priority relative to
  peers under the current detection set.

The formula and every component are public and logged per CSE so an
examiner can recompute the number by hand:

    priority = scale × (
        w_conf   × mean(finding confidence)
      + w_sev    × mean(severity points: HIGH=1.0, MEDIUM=0.6, LOW=0.3)
      + w_breadth × 0.5·min(n_findings / target, 1)
                   + 0.5·min(n_categories / max_categories, 1))

Weights come from the ``scoring`` section of ``data/config/thresholds.json``.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import pandas as pd

from src.analytics.finding import Finding

# Spec severity points (phases.md Phase 8); unknown severities score as LOW.
SEVERITY_POINTS = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}

DEFAULT_SCORING = {
    "confidence_weight": 0.4,
    "severity_weight": 0.3,
    "breadth_weight": 0.3,
    "signal_count_target": 10,
    "max_diversity_categories": 4,
    "scale": 100,
}


def _scoring_cfg(thresholds: Optional[Mapping[str, Any]] = None) \
        -> Dict[str, Any]:
    cfg = dict(DEFAULT_SCORING)
    if thresholds:
        cfg.update(thresholds.get("scoring") or {})
    return cfg


# ---------------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------------


@dataclass
class AttentionScore:
    cse_id: str
    priority: float                     # final 0–scale number
    n_findings: int
    n_signal_types: int                 # distinct detectors that fired
    n_categories: int                   # distinct signal categories
    avg_confidence: float
    avg_severity: float                 # mapped to 0..1 points
    components: Dict[str, float] = field(default_factory=dict)

    @property
    def signal_count_score(self) -> float:
        return self.components.get("signal_count_score", 0.0)

    @property
    def diversity_score(self) -> float:
        return self.components.get("diversity_score", 0.0)

    def explanation(self) -> str:
        """One-line transparency breakdown (weights + raw components)."""
        c = self.components
        return (
            f"{self.cse_id}: {self.priority:.1f} — "
            f"confidence {c.get('avg_confidence', 0):.2f} "
            f"(w={c.get('confidence_weight', 0):.2f}), "
            f"severity {c.get('avg_severity', 0):.2f} "
            f"(w={c.get('severity_weight', 0):.2f}), breadth: count "
            f"{c.get('signal_count_score', 0):.2f} + diversity "
            f"{c.get('diversity_score', 0):.2f} "
            f"(w={c.get('breadth_weight', 0):.2f}); "
            f"{self.n_findings} finding(s), {self.n_signal_types} signal "
            f"type(s), {self.n_categories} category(ies)"
        )


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def compute_attention_scores(
    findings: Iterable[Finding],
    all_cse_ids: Iterable[str] = (),
    thresholds: Optional[Mapping[str, Any]] = None,
) -> List[AttentionScore]:
    """Score every CSE; CSEs without findings get priority 0 (still listed).

    Zero findings must not be read as "safe" — only as "nothing flagged by
    the current signal set", which is why they still appear in the output.
    """
    cfg = _scoring_cfg(thresholds)
    w_conf = float(cfg["confidence_weight"])
    w_sev = float(cfg["severity_weight"])
    w_breadth = float(cfg["breadth_weight"])
    target = int(cfg["signal_count_target"])
    max_cat = int(cfg["max_diversity_categories"])
    scale = float(cfg["scale"])

    by_cse: Dict[str, List[Finding]] = {}
    for f in findings:
        by_cse.setdefault(f.cse_id, []).append(f)
    for cse_id in all_cse_ids:
        by_cse.setdefault(cse_id, [])

    scores: List[AttentionScore] = []
    for cse_id, cse_findings in sorted(by_cse.items()):
        confidences = [float(f.confidence) for f in cse_findings]
        severities = [SEVERITY_POINTS.get(str(f.severity).upper(), 0.3)
                      for f in cse_findings]
        avg_conf = round(_mean(confidences), 4)
        avg_sev = round(_mean(severities), 4)

        n = len(cse_findings)
        types = {f.signal_type for f in cse_findings}
        cats = {f.signal_category for f in cse_findings}
        count_score = min(n / target, 1.0) if target > 0 else 1.0
        diversity = min(len(cats) / max_cat, 1.0) if max_cat > 0 else 1.0

        components = {
            "avg_confidence": avg_conf,
            "avg_severity": avg_sev,
            "signal_count_score": round(count_score, 4),
            "diversity_score": round(diversity, 4),
            "confidence_component": round(w_conf * avg_conf, 4),
            "severity_component": round(w_sev * avg_sev, 4),
            "breadth_component": round(
                w_breadth * (0.5 * count_score + 0.5 * diversity), 4),
            "confidence_weight": w_conf,
            "severity_weight": w_sev,
            "breadth_weight": w_breadth,
        }
        raw = (components["confidence_component"]
               + components["severity_component"]
               + components["breadth_component"])
        scores.append(AttentionScore(
            cse_id=cse_id, priority=round(raw * scale, 1),
            n_findings=n, n_signal_types=len(types), n_categories=len(cats),
            avg_confidence=avg_conf, avg_severity=avg_sev,
            components=components,
        ))
    return scores


def rank_scores(scores: Iterable[AttentionScore]) -> List[AttentionScore]:
    """Highest priority first; ties broken deterministically."""
    return sorted(scores, key=lambda s: (-s.priority, -s.n_findings,
                                         -s.n_signal_types, s.cse_id))


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

SCORES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS attention_scores (
    cse_id TEXT PRIMARY KEY,
    priority REAL NOT NULL,
    n_findings INTEGER NOT NULL,
    n_signal_types INTEGER NOT NULL,
    n_categories INTEGER NOT NULL,
    avg_confidence REAL NOT NULL,
    avg_severity REAL NOT NULL,
    components_json TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


def store_scores(scores: Iterable[AttentionScore], db_path: Path) -> int:
    """Replace the whole ranking table (scores are run-scoped, not scoped)."""
    from sqlalchemy import text

    from src.storage.db import get_engine

    engine = get_engine(db_path)
    created_at = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "cse_id": s.cse_id, "priority": s.priority,
            "n_findings": s.n_findings, "n_signal_types": s.n_signal_types,
            "n_categories": s.n_categories,
            "avg_confidence": s.avg_confidence,
            "avg_severity": s.avg_severity,
            "components_json": json.dumps(s.components),
            "created_at": created_at,
        }
        for s in scores
    ]
    with engine.begin() as conn:
        conn.execute(text(SCORES_TABLE_SQL))
        conn.execute(text("DELETE FROM attention_scores"))
        conn.execute(text(
            "INSERT INTO attention_scores "
            "(cse_id, priority, n_findings, n_signal_types, n_categories, "
            " avg_confidence, avg_severity, components_json, created_at) "
            "VALUES (:cse_id, :priority, :n_findings, :n_signal_types, "
            " :n_categories, :avg_confidence, :avg_severity, "
            " :components_json, :created_at)"
        ), rows)
    return len(rows)


def load_scores(db_path: Path) -> pd.DataFrame:
    from sqlalchemy import text

    from src.storage.db import get_engine

    engine = get_engine(db_path)
    try:
        return pd.read_sql(text(
            "SELECT * FROM attention_scores ORDER BY priority DESC"), engine)
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_DISCLAIMER = (
    "Supervisory Attention Priority — a review-prioritization heuristic.\n"
    "NOT a risk or compliance score. Low priority does not mean safe;\n"
    "it means lower priority for this review cycle."
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="scoring", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    rank = sub.add_parser("rank", help="Rank CSEs by attention priority")
    rank.add_argument("--db", "--profiles", "--findings", dest="db",
                      type=Path, default=Path("data/sat_sa.db"))
    rank.add_argument("--top", type=int, default=None,
                      help="show only the first N entries")
    args = parser.parse_args(argv)

    from src.evidence.findings import load_findings_as_objects
    from src.analytics.finding import load_thresholds
    from src.storage.db import load_table

    findings = load_findings_as_objects(args.db)
    try:
        metadata = load_table("cse_metadata", args.db)
        all_ids = metadata["cse_id"].astype(str).tolist() if len(metadata) \
            else []
    except Exception:
        all_ids = []

    scores = rank_scores(compute_attention_scores(findings, all_ids,
                                                  load_thresholds()))
    print(_DISCLAIMER)
    shown = scores if args.top is None else scores[:args.top]
    for s in shown:
        print(f"  {s.cse_id}: {s.priority:.1f} ({s.n_findings} findings, "
              f"{s.n_signal_types} signal types, "
              f"avg confidence {s.avg_confidence:.2f})")
    store_scores(scores, args.db)
    print(f"\n{len(scores)} CSEs ranked; full component breakdown stored in "
          f"attention_scores ({args.db}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
