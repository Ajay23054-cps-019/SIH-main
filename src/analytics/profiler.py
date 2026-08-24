"""Behavioral profiler: per-CSE, per-period supervisory metrics.

Transforms normalized records into the metrics every detection engine
consumes. Missing tables degrade gracefully — a CSE with no investigation
records gets ``None`` investigation metrics plus an explicit warning, never
a crash.

Design decisions worth remembering downstream:
* Investigations and escalations are attributed to the quarter of their
  *alert's* timestamp (the work window), not their own open date.
* Assets are period-independent; density/coverage use the CSE's full roster.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.analytics.profiles import PERIOD_ALL, BehavioralProfile

BUSINESS_HOURS = range(7, 19)  # 07:00–18:59 counts as business hours
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    """Quarter-over-quarter fractional change; None when either side missing."""
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / abs(previous), 4)


def _period_mask(alerts: pd.DataFrame, period: str) -> pd.Series:
    """Boolean mask selecting alerts belonging to a 'YYYY-Qn' period."""
    ts = pd.to_datetime(alerts["timestamp"], errors="coerce")
    target = pd.Period(period, freq="Q")  # '2024-Q1' parses natively
    return ts.dt.to_period("Q") == target


def _headline(profile: BehavioralProfile) -> Dict[str, Optional[float]]:
    return {
        "inv_depth_mean": profile.metrics.get("inv_depth_mean"),
        "closure_velocity_median_h": profile.metrics.get("closure_velocity_median_h"),
        "esc_rate": profile.metrics.get("esc_rate"),
    }


# ---------------------------------------------------------------------------
# Metric groups (each returns a dict of metrics)
# ---------------------------------------------------------------------------


def _alert_metrics(alerts: pd.DataFrame, n_days: int) -> Dict[str, Any]:
    m: Dict[str, Any] = {}
    n = len(alerts)
    m["alert_volume_total"] = n
    m["alert_volume_per_day"] = round(n / n_days, 4)

    sev_counts = alerts["severity"].value_counts(dropna=False)
    total = max(n, 1)
    for sev in SEVERITIES:
        m[f"sev_{sev.lower()}_count"] = int(sev_counts.get(sev, 0))
        m[f"sev_{sev.lower()}_pct"] = round(sev_counts.get(sev, 0) / total, 4)

    cat_counts = alerts["category"].value_counts(normalize=True, dropna=True)
    m["category_distribution"] = {str(k): round(float(v), 4) for k, v in cat_counts.items()}
    m["n_categories_present"] = int(alerts["category"].nunique())

    ts = pd.to_datetime(alerts["timestamp"], errors="coerce")
    hours = ts.dt.hour
    weekdays = ts.dt.weekday
    m["diurnal_distribution"] = [int((hours == h).sum()) for h in range(24)]
    m["weekly_distribution"] = [int((weekdays == d).sum()) for d in range(7)]
    m["weekend_alert_share"] = round(float((weekdays >= 5).mean()), 4)
    m["after_hours_alert_share"] = round(float((~hours.isin(BUSINESS_HOURS)).mean()), 4)

    # Quiet periods: gaps between consecutive alerts exceeding 48h.
    ordered = ts.dropna().sort_values()
    if len(ordered) > 1:
        gaps_h = ordered.diff().dt.total_seconds().div(3600)
        m["quiet_period_count"] = int((gaps_h > 48).sum())
        m["max_gap_hours"] = round(float(gaps_h.max()), 2)
    else:
        m["quiet_period_count"] = 0
        m["max_gap_hours"] = None

    closed = alerts[alerts["status"] == "closed"]
    m["closed_alert_share"] = round(len(closed) / total, 4)
    velocity_h = (
        pd.to_datetime(closed["closure_timestamp"], errors="coerce")
        - pd.to_datetime(closed["timestamp"], errors="coerce")
    ).dt.total_seconds() / 3600
    valid_v = velocity_h.dropna()
    m["closure_velocity_median_h"] = round(float(valid_v.median()), 3) \
        if len(valid_v) else None
    return m


def _investigation_metrics(
    alerts: pd.DataFrame, investigations: pd.DataFrame
) -> Tuple[Dict[str, Any], pd.DataFrame]:
    """Metrics over investigations attributed to their alert's severity."""
    m: Dict[str, Any] = {}
    alert_ids = set(alerts["alert_id"])
    in_corpus = investigations["alert_id"].isin(alert_ids)
    m["orphan_investigations"] = int((~in_corpus).sum())
    linked = investigations[in_corpus].copy()

    m["investigation_rate"] = round(len(linked) / max(len(alerts), 1), 4)

    depth = linked["evidence_entries"].astype(float)
    m["inv_depth_mean"] = round(float(depth.mean()), 3) if len(depth) else None
    m["inv_depth_median"] = round(float(depth.median()), 3) if len(depth) else None
    m["inv_depth_p25"] = round(float(depth.quantile(0.25)), 3) if len(depth) else None
    m["inv_depth_p75"] = round(float(depth.quantile(0.75)), 3) if len(depth) else None

    dur_h = (
        pd.to_datetime(linked["timestamp_close"], errors="coerce")
        - pd.to_datetime(linked["timestamp_open"], errors="coerce")
    ).dt.total_seconds() / 3600
    valid_dur = dur_h.dropna()
    m["inv_duration_mean_h"] = round(float(valid_dur.mean()), 3) if len(valid_dur) else None
    m["inv_duration_p50_h"] = round(float(valid_dur.quantile(0.5)), 3) if len(valid_dur) else None
    m["inv_duration_p90_h"] = round(float(valid_dur.quantile(0.9)), 3) if len(valid_dur) else None

    # Attribution: severity comes from the investigated alert.
    linked = linked.merge(alerts[["alert_id", "severity"]], on="alert_id", how="left")
    m["inv_depth_by_severity"] = {
        str(sev): round(float(g["evidence_entries"].astype(float).mean()), 3)
        for sev, g in linked.groupby("severity") if len(g)
    }
    return m, linked


def _escalation_metrics(
    linked_investigations: pd.DataFrame, escalations: pd.DataFrame
) -> Dict[str, Any]:
    m: Dict[str, Any] = {}
    inv_ids = set(linked_investigations["investigation_id"])
    in_scope = escalations["investigation_id"].isin(inv_ids)
    m["esc_orphan_count"] = int((~in_scope).sum())
    linked = escalations[in_scope]

    n_linked_inv = max(len(linked_investigations), 1)
    m["esc_rate"] = round(len(linked) / n_linked_inv, 4)

    followup = linked["has_followup"].dropna()
    m["esc_followthrough_rate"] = round(float(followup.astype(bool).mean()), 4) \
        if len(followup) else None

    # Appropriateness: were high-severity investigations escalated?
    sev_map = linked_investigations[["investigation_id", "severity"]]
    with_sev = linked.merge(sev_map, on="investigation_id", how="left") \
        if len(linked) else linked
    for sev in ("CRITICAL", "HIGH"):
        denom = int((linked_investigations["severity"] == sev).sum())
        n_esc = int((with_sev["severity"] == sev).sum()) if len(with_sev) else 0
        m[f"esc_rate_{sev.lower()}"] = round(n_esc / denom, 4) if denom else None

    esc_ts = pd.to_datetime(linked["timestamp"], errors="coerce")
    m["esc_weekend_share"] = round(float((esc_ts.dt.weekday >= 5).mean()), 4) \
        if esc_ts.notna().any() else None
    return m


def _evidence_completeness(
    alerts: pd.DataFrame, investigations: pd.DataFrame
) -> float:
    """Mean field-presence over key fields, 0..1. Transparent by design:
      alerts: timestamp, severity, asset_id (+ closure_timestamp when closed)
      investigations: timestamp_open, timestamp_close, notes
    """
    checks: List[float] = []
    if len(alerts):
        for col in ("timestamp", "severity", "asset_id"):
            checks.append(float(alerts[col].notna().mean()))
        closed = alerts[alerts["status"] == "closed"]
        if len(closed):
            checks.append(float(closed["closure_timestamp"].notna().mean()))
    if len(investigations):
        for col in ("timestamp_open", "timestamp_close", "notes"):
            checks.append(float(investigations[col].notna().mean()))
    return round(float(np.mean(checks)), 4) if checks else 0.0


# ---------------------------------------------------------------------------
# Profile computation
# ---------------------------------------------------------------------------


def compute_profile(
    cse_id: str,
    period: str,
    alerts: pd.DataFrame,
    investigations: pd.DataFrame,
    escalations: pd.DataFrame,
    assets: pd.DataFrame,
    previous: Optional[Dict[str, Optional[float]]] = None,
) -> BehavioralProfile:
    """Build one profile for ``cse_id`` over ``period`` ('2024-Q1' or ALL).

    ``previous`` carries last quarter's headline metrics so trend fields can
    be filled; pass None (or omit) for the first period.
    """
    warnings: List[str] = []

    if period != PERIOD_ALL and len(alerts):
        alerts = alerts[_period_mask(alerts, period)]

    metrics: Dict[str, Any] = {}

    if not len(alerts):
        warnings.append(f"{cse_id} {period}: no alert records in period")
        metrics.update({
            "alert_volume_total": 0,
            "investigation_rate": None,
            "evidence_completeness_score": 0.0,
            "depth_trend_qoq_pct": None,
        })
        return BehavioralProfile(cse_id=cse_id, period=period, metrics=metrics,
                                 warnings=warnings, n_alerts=0)

    ts = pd.to_datetime(alerts["timestamp"], errors="coerce").dropna()
    span_days = max(int((ts.max() - ts.min()).days) + 1, 1)

    metrics.update(_alert_metrics(alerts, span_days))
    metrics["alert_density_per_asset"] = round(len(alerts) / len(assets), 4) \
        if len(assets) else None

    if not len(investigations):
        warnings.append(f"{cse_id} {period}: no investigation records submitted")
        for key in ("investigation_rate", "inv_depth_mean", "inv_depth_median",
                    "inv_duration_p50_h"):
            metrics[key] = None
        linked = investigations.iloc[0:0]
    else:
        im, linked = _investigation_metrics(alerts, investigations)
        metrics.update(im)
        if metrics["investigation_rate"] == 0:
            warnings.append(f"{cse_id} {period}: zero investigations linked to alerts")

    if not len(escalations):
        warnings.append(f"{cse_id} {period}: no escalation records submitted")
        metrics["esc_rate"] = None
    else:
        metrics.update(_escalation_metrics(linked, escalations))

    # Triage-only closures: high-severity alerts closed with no investigation.
    closed_hi = alerts[
        (alerts["status"] == "closed")
        & (alerts["severity"].isin(("CRITICAL", "HIGH")))
    ]
    if len(closed_hi):
        investigated = set(linked["alert_id"]) if len(linked) else set()
        metrics["triage_only_high_sev_rate"] = round(
            float((~closed_hi["alert_id"].isin(investigated)).mean()), 4
        )
    else:
        metrics["triage_only_high_sev_rate"] = None

    metrics["evidence_completeness_score"] = _evidence_completeness(alerts, investigations)
    metrics["monitored_asset_share"] = round(
        float((assets["monitoring_status"] == "monitored").mean()), 4
    ) if len(assets) else None

    # Trends vs previous period
    metrics["depth_trend_qoq_pct"] = _pct_change(
        metrics.get("inv_depth_mean"),
        previous.get("inv_depth_mean") if previous else None,
    )
    metrics["closure_velocity_trend_qoq_pct"] = _pct_change(
        metrics.get("closure_velocity_median_h"),
        previous.get("closure_velocity_median_h") if previous else None,
    )
    metrics["escalation_rate_trend_qoq_pct"] = _pct_change(
        metrics.get("esc_rate"),
        previous.get("esc_rate") if previous else None,
    )

    return BehavioralProfile(cse_id=cse_id, period=period, metrics=metrics,
                             warnings=warnings, n_alerts=int(len(alerts)))


def compute_all_profiles(frames: Dict[str, pd.DataFrame]) -> List[BehavioralProfile]:
    """Profiles for every CSE x quarter (chained for trends), plus one
    full-window profile per CSE."""
    alerts_all = frames.get("alerts", pd.DataFrame())
    invs_all = frames.get("investigations", pd.DataFrame())
    escs_all = frames.get("escalations", pd.DataFrame())
    assets_all = frames.get("assets", pd.DataFrame())

    def _subset(frame: pd.DataFrame, cse_id: str) -> pd.DataFrame:
        if not len(frame):
            return frame
        return frame[frame["cse_id"] == cse_id]

    profiles: List[BehavioralProfile] = []
    for cse_id, alerts in alerts_all.groupby("cse_id"):
        invs = _subset(invs_all, cse_id)
        escs = _subset(escs_all, cse_id)
        assets = _subset(assets_all, cse_id)

        quarters = sorted(
            pd.to_datetime(alerts["timestamp"], errors="coerce")
            .dt.to_period("Q").dropna().unique()
        )
        prev_headline: Optional[Dict[str, Optional[float]]] = None
        for quarter in quarters:
            label = f"{quarter.year}-Q{quarter.quarter}"
            prof = compute_profile(cse_id, label, alerts, invs, escs, assets,
                                   previous=prev_headline)
            profiles.append(prof)
            prev_headline = _headline(prof)

        profiles.append(compute_profile(cse_id, PERIOD_ALL, alerts, invs, escs, assets))

    return profiles


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

PROFILES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS behavioral_profiles (
    cse_id TEXT NOT NULL,
    period TEXT NOT NULL,
    n_alerts INTEGER,
    metrics_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    PRIMARY KEY (cse_id, period)
)
"""


def store_profiles(profiles: List[BehavioralProfile], db_path: Path) -> int:
    """Upsert profiles into the behavioral_profiles table."""
    from sqlalchemy import text

    from src.storage.db import get_engine

    engine = get_engine(db_path)
    with engine.begin() as conn:
        conn.execute(text(PROFILES_TABLE_SQL))
        for p in profiles:
            conn.execute(text(
                "INSERT OR REPLACE INTO behavioral_profiles "
                "(cse_id, period, n_alerts, metrics_json, warnings_json) "
                "VALUES (:cse_id, :period, :n_alerts, :metrics, :warnings)"
            ), {
                "cse_id": p.cse_id,
                "period": p.period,
                "n_alerts": p.n_alerts,
                "metrics": json.dumps(p.metrics),
                "warnings": json.dumps(p.warnings),
            })
    return len(profiles)


def load_profiles(db_path: Path, cse_id: Optional[str] = None) -> pd.DataFrame:
    """Read stored profiles back; metrics/warnings decoded from JSON."""
    from src.storage.db import get_engine

    query = "SELECT * FROM behavioral_profiles"
    params: Dict[str, Any] = {}
    if cse_id:
        query += " WHERE cse_id = :cse_id"
        params["cse_id"] = cse_id
    df = pd.read_sql(query, get_engine(db_path), params=params)
    if len(df):
        df["metrics"] = df["metrics_json"].map(json.loads)
        df["warnings"] = df["warnings_json"].map(json.loads)
    return df


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="profiler", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Compute profiles from stored submissions")
    run.add_argument("--db", type=Path, default=Path("data/sat_sa.db"),
                     help="SQLite DB holding submissions (also receives profiles)")
    args = parser.parse_args(argv)

    from src.storage.db import load_table

    frames = {name: load_table(name, args.db)
              for name in ("alerts", "investigations", "escalations", "assets")}
    profiles = compute_all_profiles(frames)
    store_profiles(profiles, args.db)

    print(f"Computed {len(profiles)} profiles "
          f"({len({p.cse_id for p in profiles})} CSEs) -> {args.db}")
    if profiles:
        counts = [len(p.scalar_metrics) for p in profiles]
        print(f"Scalar metrics per profile: min={min(counts)}, max={max(counts)}")
        flagged = sum(1 for p in profiles if p.warnings)
        if flagged:
            print(f"{flagged} profiles carry data-quality warnings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
