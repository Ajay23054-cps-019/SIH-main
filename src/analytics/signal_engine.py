"""Supervisory signal engine: runs all 18 signals and persists findings.

Usage:
    python -m src.analytics.signal_engine run --db data/sat_sa.db
    python -m src.analytics.signal_engine run --cse-id CSE-042 --db data/sat_sa.db
    python -m src.analytics.signal_engine run --category negative_space --db data/sat_sa.db

Pipeline: stored profiles + raw frames -> per-CSE SignalContext (peer stats
computed once) -> each registered signal -> findings upserted into the
``findings`` table. Signals are pure functions; all I/O lives here.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from src.analytics import (
    behavioral_anomalies,
    execution_gaps,
    negative_space,
    peer_deviation,
)
from src.analytics.finding import load_thresholds
from src.analytics.profiles import BehavioralProfile
from src.analytics.signal_common import SignalContext

CATEGORY_MODULES = {
    "execution_gap": execution_gaps,
    "negative_space": negative_space,
    "behavioral_anomaly": behavioral_anomalies,
    "peer_deviation": peer_deviation,
}

SIGNAL_REGISTRY: Dict[str, tuple] = {}
for _cat, _mod in CATEGORY_MODULES.items():
    for _name, _fn in _mod.SIGNALS:
        SIGNAL_REGISTRY[_name] = (_cat, _fn)

assert len(SIGNAL_REGISTRY) == 18, \
    f"expected 18 registered signals, found {len(SIGNAL_REGISTRY)}"

FINDINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT PRIMARY KEY,
    cse_id TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    signal_category TEXT NOT NULL,
    period TEXT,
    severity TEXT,
    confidence REAL,
    evidence_json TEXT,
    contributing_record_ids_json TEXT,
    detection_logic TEXT,
    caveats_json TEXT,
    recommended_actions_json TEXT,
    data_quality_notes_json TEXT,
    created_at TEXT
)
"""


# ---------------------------------------------------------------------------
# Context assembly (testable without a database)
# ---------------------------------------------------------------------------


def build_peer_stats(profiles: List[BehavioralProfile],
                     frames: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, float]]:
    return peer_deviation.build_peer_stats(profiles, frames)


def build_contexts(
    frames: Dict[str, pd.DataFrame],
    profiles: List[BehavioralProfile],
    thresholds: Optional[Dict[str, Any]] = None,
    quality_score: float = 1.0,
) -> Dict[str, SignalContext]:
    """One SignalContext per CSE, sharing precomputed peer stats."""
    thresholds = thresholds or load_thresholds()
    peer_stats = build_peer_stats(profiles, frames)

    by_cse: Dict[str, List[BehavioralProfile]] = {}
    for p in profiles:
        by_cse.setdefault(p.cse_id, []).append(p)

    contexts: Dict[str, SignalContext] = {}
    for cse_id in sorted({*by_cse.keys(), *_cse_ids(frames)}):
        cse_frames = {
            entity: (frame[frame["cse_id"] == cse_id].copy()
                     if len(frame) else frame)
            for entity, frame in frames.items() if isinstance(frame, pd.DataFrame)
        }
        contexts[cse_id] = SignalContext(
            cse_id=cse_id,
            profiles=by_cse.get(cse_id, []),
            cse_frames=cse_frames,
            frames=frames,
            peer_stats=peer_stats,
            quality_score=quality_score,
            thresholds=thresholds,
        )
    return contexts


def run_context(ctx: SignalContext,
                only: Optional[List[str]] = None) -> List[Any]:
    """Run every registered signal (or a subset) against one context."""
    quality_gate = ctx.t("_global", "quality_gate")
    findings: List[Any] = []
    for name, (category, fn) in SIGNAL_REGISTRY.items():
        if only and name not in only:
            continue
        try:
            finding = fn(ctx)
        except Exception as exc:  # a broken signal must not kill the sweep
            print(f"[warn] signal {name} failed for {ctx.cse_id}: {exc}")
            continue
        if finding is None:
            continue
        if ctx.quality_score < quality_gate:
            finding.data_quality_notes.append(
                f"Ingestion quality score {ctx.quality_score:.2f} below gate "
                f"{quality_gate}; treat this finding as indicative only."
            )
        findings.append(finding)
    return findings


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

_FINDING_COLUMNS = (
    "finding_id", "cse_id", "signal_type", "signal_category", "period",
    "severity", "confidence", "evidence_json", "contributing_record_ids_json",
    "detection_logic", "caveats_json", "recommended_actions_json",
    "data_quality_notes_json", "created_at",
)


def store_findings(findings: List[Any], db_path: Path) -> int:
    from sqlalchemy import text

    from src.storage.db import get_engine

    engine = get_engine(db_path)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with engine.begin() as conn:
        conn.execute(text(FINDINGS_TABLE_SQL))
        for f in findings:
            if not f.created_at:
                f.created_at = stamp
            row = f.to_dict()
            params = {
                **{k: row[k] for k in _FINDING_COLUMNS if not k.endswith("_json")},
                "evidence_json": json.dumps(row["evidence"]),
                "contributing_record_ids_json":
                    json.dumps(row["contributing_record_ids"]),
                "caveats_json": json.dumps(row["caveats"]),
                "recommended_actions_json":
                    json.dumps(row["recommended_actions"]),
                "data_quality_notes_json":
                    json.dumps(row["data_quality_notes"]),
            }
            cols = ", ".join(_FINDING_COLUMNS)
            binds = ", ".join(f":{c}" for c in _FINDING_COLUMNS)
            conn.execute(text(
                f"INSERT OR REPLACE INTO findings ({cols}) VALUES ({binds})"
            ), params)
    return len(findings)


def load_findings(db_path: Path, cse_id: Optional[str] = None,
                  category: Optional[str] = None) -> pd.DataFrame:
    from src.storage.db import get_engine

    query = "SELECT * FROM findings"
    clauses, params = [], {}
    if cse_id:
        clauses.append("cse_id = :cse_id")
        params["cse_id"] = cse_id
    if category:
        clauses.append("signal_category = :category")
        params["category"] = category
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    df = pd.read_sql(query, get_engine(db_path), params=params)
    if len(df):
        df["evidence"] = df["evidence_json"].map(json.loads)
        df["contributing_record_ids"] = \
            df["contributing_record_ids_json"].map(json.loads)
    return df


# ---------------------------------------------------------------------------
# End-to-end entry point
# ---------------------------------------------------------------------------


def _cse_ids(frames: Dict[str, pd.DataFrame]) -> List[str]:
    alerts = frames.get("alerts")
    if alerts is None or not len(alerts):
        return []
    return sorted(alerts["cse_id"].dropna().unique().tolist())


def run_signals(db_path: Path, cse_id: Optional[str] = None,
                category: Optional[str] = None,
                thresholds: Optional[Dict[str, Any]] = None) -> List[Any]:
    """Profiles + frames from ``db_path`` -> findings stored back into it."""
    from src.analytics.profiler import load_profiles, rows_to_profiles
    from src.ingestion.quality import assess_quality
    from src.storage.db import load_table

    entities = ("cse_metadata", "alerts", "investigations", "escalations",
                "cases", "assets")
    frames = {name: load_table(name, db_path) for name in entities}
    report = assess_quality(frames, rejections=[], unknown_columns=set())
    profiles = rows_to_profiles(load_profiles(db_path))

    contexts = build_contexts(frames, profiles, thresholds,
                              quality_score=report.overall_score())
    if cse_id:
        contexts = {k: v for k, v in contexts.items() if k == cse_id}

    only = None
    if category:
        only = [n for n, (cat, _) in SIGNAL_REGISTRY.items() if cat == category]

    findings: List[Any] = []
    for ctx in contexts.values():
        findings.extend(run_context(ctx, only=only))
    store_findings(findings, db_path)
    return findings


def _print_findings(findings: List[Any]) -> None:
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    for f in sorted(findings, key=lambda x: (order.get(x.severity, 9),
                                             -x.confidence)):
        print(f"  [{f.severity:6}] conf={f.confidence:.2f} "
              f"{f.cse_id} {f.signal_type} ({f.period})")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="signal_engine", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run signals over stored submissions")
    run.add_argument("--db", type=Path, default=Path("data/sat_sa.db"))
    run.add_argument("--cse-id", default=None)
    run.add_argument("--category", default=None,
                     choices=sorted(CATEGORY_MODULES))
    args = parser.parse_args(argv)

    findings = run_signals(args.db, cse_id=args.cse_id, category=args.category)
    print(f"Produced {len(findings)} findings"
          + (f" for {args.cse_id}" if args.cse_id else "")
          + f" -> {args.db}/findings")
    _print_findings(findings)
    return 0


def run_category_cli(category: str, argv: Optional[List[str]] = None) -> int:
    """Entry point behind the per-category modules
    (src.analytics.execution_gaps / negative_space / ...)."""
    parser = argparse.ArgumentParser(
        prog=f"src.analytics.{category}", description=f"{category} signals",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--db", type=Path, default=Path("data/sat_sa.db"))
    run.add_argument("--cse-id", default=None)
    args = parser.parse_args(argv)

    findings = run_signals(args.db, cse_id=args.cse_id, category=category)
    print(f"[{category}] {len(findings)} findings"
          + (f" for {args.cse_id}" if args.cse_id else ""))
    _print_findings(findings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
