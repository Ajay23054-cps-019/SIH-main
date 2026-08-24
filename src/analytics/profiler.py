"""Behavioral profiler: per-CSE, per-period supervisory metrics.

Transforms normalized records into the metrics every detection engine
consumes. Missing tables degrade gracefully — a CSE with no investigation
records gets ``inv_rate = 0`` and an explicit warning, never a crash.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.analytics.profiles import PERIOD_ALL, BehavioralProfile

BUSINESS_HOURS = range(7, 19)  # 07:00–18:59 counts as business hours


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_div(num: float, den: float) -> Optional[float]:
    return num / den if den else None


def _pct_change(current: Optional[float], previous: Optional[float]) -> Optional[float]:
    """Quarter-over-quarter change; None when either side is unavailable."""
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous)


def _empty_metrics(warnings: List[str], reason: str) -> Dict[str, any]:
    warnings.append(reason)
    return {}


# ---------------------------------------------------------------------------
# Metric groups (each returns dict of metrics; may append warnings)
# ---------------------------------------------------------------------------


def _alert_metrics(alerts: pd.DataFrame, n_days: float) -> Tuple[Dict, dict]:
    m: Dict = {}
    m["alert_volume_total"] = int(len(alerts))
    m["alert_volume_per_day"] = round(len(alerts) / n_days, 4) if n_days else None

    sev_counts = alerts["severity"].value_counts(dropna=False)
    total = max(len(alerts), 1)
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        m[f"sev_{sev.lower()}_count"] = int(sev_counts.get(sev, 0))
        m[f"sev_{sev.lower()}_pct"] = round(sev_counts.get(sev, 0) / total, 4)

    cat_counts = alerts["category"].value_counts(normalize=True, dropna=True)
    m["category_distribution"] = {str(k): round(float(v), 4) for k, v in cat_counts.items()}
    m["n_categories_present"] = int(alerts["category"].nunique())

    ts = pd.to_datetime(alerts["timestamp"], errors="coerce")
    hours = ts.dt.hour
    m["diurnal_distribution"] = [int((hours == h).sum()) for h in range(24)]
    weekdays = ts.dt.weekday
    m["weekly_distribution"] = [int((weekdays == d).sum()) for d in range(7)]
    m["weekend_alert_share"] = round(float((weekdays >= 5).mean()), 4) if len(alerts) else None
    m["after_hours_alert_share"] = round(
        float((~hours.isin(BUSINESS_HOURS)).mean()), 4
    ) if len(alerts) else None

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
    closure = pd.to_datetime(closed["closure_timestamp"], errors="coerce")
    velocity_h = (closure - pd.to_datetime(closed["timestamp"], errors="coerce")) \
        .dt.total_seconds() / 3600
    m["closure_velocity_median_h"] = round(float(velocity_h.median()), 3) \
        if velocity_h.notna().any() else None
    m["triage_only_close_share"] = round(
        float((closed["closure_timestamp"].notna()
               & ~closed["alert_id"].isin([])).mean() * 0 + len(closed) / total),
        4,
    )
    return m, {"closed": closed}


def _investigation_metrics(
    alerts: pd.DataFrame, investigations: pd.DataFrame
) -> Tuple[Dict, pd.DataFrame]:
    """Metrics over investigations attributed to their alert's severity."""
    m: Dict = {}
    alert_ids = set(alerts["alert_id"])
    linked = investigations[investigations["alert_id"].isin(alert_ids)].copy()
    m["orphan_investigations"] = int((~investigations["alert_id"].isin(alert_ids)).sum())

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
    valid_dur = dur_h[dur_h.notna()]
    m["inv_duration_mean_h"] = round(float(valid_dur.mean()), 3) if len(valid_dur) else None
    m["inv_duration_p50_h"] = round(float(valid_dur.quantile(0.5)), 3) if len(valid_dur) else None
    m["inv_duration_p90_h"] = round(float(valid_dur.quantile(0.9)), 3) if len(valid_dur) else None

    if "severity" not in linked.columns and len(linked):
        linked = linked.merge(
            alerts[["alert_id", "severity"]], on="alert_id", how="left"
        )
    m["inv_depth_by_severity"] = {
        sev: round(float(g["evidence_entries"].astype(float).mean()), 3)
        for sev, g in linked.groupby("severity") if len(g)
    } if len(linked) else {}

    return m, linked


def _escalation_metrics(
    linked_investigations: pd.DataFrame, escalations: pd.DataFrame
) -> Tuple[Dict, dict]:
    m: Dict = {}
    inv_ids = set(linked_investigations["investigation_id"]) if len(linked_investigations) else set()
    linked = escalations[escalations["investigation_id"].isin(inv_ids)] \
        if len(escalations) and inv_ids else escalations.iloc[0:0]

    m["esc_orphan_count"] = int(
        (~escalations["investigation_id"].isin(inv_ids)).sum()
    ) if len(escalations) else 0

    m["esc_rate"] = round(len(linked) / max(len(linked_investigations), 1), 4)

    followup = linked["has_followup"].dropna()
    m["esc_followthrough_rate"] = round(float(followup.astype(bool).mean()), 4) if len(followup) else None
    no_followup = float((~linked["has_followup"].astype(bool)).mean()) if len(linked) else None
    m["esc_no_followup_rate"] = round(no_followup, 4) if no_followup is not None else None

    # Appropriateness: critical alerts that were escalated.
    sev_map = linked_investigations[["investigation_id", "severity"]]
    with_sev = linked.merge(sev_map, on="investigation_id", how="left") \
        if len(linked) and len(sev_map) else linked
    for sev in ("CRITICAL", "HIGH"):
        denom = linked_investigations[
            linked_investigations["severity"] == sev
        ] if "severity" in linked_investigations.columns else []
        n_denom = len(denom)
        n_esc = int((with_sev["severity"] == sev).sum()) if len(with_sev) else 0
        m[f"esc_rate_{sev.lower()}"] = round(n_esc / n_denom, 4) if n_denom else None

    esc_ts = pd.to_datetime(linked["timestamp"], errors="coerce")
    m["esc_weekend_share"] = round(float((esc_ts.dt.weekday >= 5).mean()), 4) \
        if esc_ts.notna().any() else None

    return m, linked


def _evidence_completeness(
    alerts: pd.DataFrame, investigations: pd.DataFrame
) -> float:
    """Fraction of expected fields actually populated across key records.

    Transparent definition: mean field-presence over
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
    """Build one profile. ``previous`` carries last quarter's headline metrics
    for trend computation ({metric_name: value})."""
    warnings: List[str] = []

    if period != PERIOD_ALL:
        alerts = alerts[pd.to_datetime(alerts["timestamp"]).dt.to_period("Q").astype(str)
                        == period.replace("-", "Q")] if len(alerts) else alerts

    metrics: Dict[str, any] = {}

    if not len(alerts):
        warnings.append(f"{cse_id} {period}: no alert records in period")
        metrics.update({
            "alert_volume_total": 0,
            "investigation_rate": None,
            "evidence_completeness_score": 0.0,
        })
        return BehavioralProfile(cse_id, period, metrics, warnings, n_alerts=0)

    ts = pd.to_datetime(alerts["timestamp"], errors="coerce").dropna()
    span_days = max((ts.max() - ts.min()).days + 1, 1)

    am, aux = _alert_metrics(alerts, span_days)
    metrics.update(am)
    metrics["alert_density_per_asset"] = round(
        len(alerts) / max(len(assets), 1), 4
    ) if len(assets) else None

    if not len(investigations):
        warnings.append(f"{cse_id} {period}: no investigation records submitted")
        for k in ("investigation_rate", "inv_depth_mean", "inv_depth_median",
                  "inv_duration_p50_h"):
            metrics[k] = None
        linked = investigations.iloc[0:0].assign(severity=pd.Series(dtype=object))
    else:
        im, linked = _investigation_metrics(alerts, investigations)
        metrics.update(im)
        if metrics["investigation_rate"] == 0:
            warnings.append(f"{cse_id} {period}: zero investigations linked to alerts")

    if not len(escalations):
        warnings.append(f"{cse_id} {period}: no escalation records submitted")
        metrics["esc_rate"] = None
    else:
        em, _ = _escalation_metrics(linked, escalations)
        metrics.update(em)

    metrics["evidence_completeness_score"] = _evidence_completeness(alerts, investigations)
    metrics["monitored_asset_share"] = round(
        float((assets["monitoring_status"] == "monitored").mean()), 4
    ) if len(assets) else None

    # Trends vs previous period
    if previous:
        metrics["depth_trend_qoq_pct"] = _pct_change(
            metrics.get("inv_depth_mean"),
            previous.get("inv_depth_mean"),
        )
        metrics["closure_velocity_trend_qoq_pct"] = _pct_change(
            metrics.get("closure_velocity_median_h"),
            previous.get("closure_velocity_median_h"),
        )
        metrics["escalation_rate_trend_qoq_pct"] = _pct_change(
            metrics.get("esc_rate"), previous.get("esc_rate")
        )
    else:
        metrics["depth_trend_qoq_pct"] = None
        metrics["closure_velocity_trend_qoq_pct"] = None
        metrics["escalation_rate_trend_qoq_pct"] = None

    profile = BehavioralProfile(cse_id=cse_id, period=period, metrics=metrics,
                                warnings=warnings, n_alerts=int(len(alerts)))
    return profile


def compute_all_profiles(frames: Dict[str, pd.DataFrame]) -> List[BehavioralProfile]:
    """Profiles for every CSE × quarter, plus one full-window profile each."""
    alerts_all = frames.get("alerts", pd.DataFrame())
    invs_all = frames.get("investigations", pd.DataFrame())
    escs_all = frames.get("escalations", pd.DataFrame())
    assets_all = frames.get("assets", pd.DataFrame())

    profiles: List[BehavioralProfile] = []
    for cse_id, alerts in alerts_all.groupby("cse_id"):
        invs = invs_all[invs_all["cse_id"] == cse_id] if len(invs_all) else invs_all
        escs = escs_all[escs_all["cse_id"] == cse_id] if len(escs_all) else escs_all
        assets = assets_all[assets_all["cse_id"] == cse_id] if len(assets_all) else assets_all

        periods = sorted(
            pd.to_datetime(alerts["timestamp"]).dt.to_period("Q").astype(str).unique()
        )

        prev_headline: Optional[Dict[str, Optional[float]]] = None
        for p_str in periods:
            label = f"{p_str[:4]}-Q{p_str[-1]}"
            prof = compute_profile(cse_id, label, alerts, invs, escs, assets,
                                   previous=prev_headline)
            profiles.append(prof)
            prev_headline = {
                "inv_depth_mean": prof.metrics.get("inv_depth_mean"),
                "closure_velocity_median_h": prof.metrics.get("closure_velocity_median_h"),
                "esc_rate": prof.metrics.get("esc_rate"),
            }

        full = compute_profile(cse_id, PERIOD_ALL, alerts, invs, escs, assets)
        profiles.append(full)

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
                "cse_id": p.cse_id, "period": p.period, "n_alerts": p.n_alerts,
                "metrics": json.dumps(p.metrics), "warnings": json.dumps(p.warnings),
            })
    return len(profiles)


def load_profiles(db_path: Path, cse_id: Optional[str] = None) -> pd.DataFrame:
    from src.storage.db import get_engine

    query = "SELECT * FROM behavioral_profiles"
    params = {}
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

    scalar_counts = [len(p.scalar_metrics) for p in profiles]
    print(f"Computed {len(profiles)} profiles "
          f"({len(set(p.cse_id for p in profiles))} CSEs) -> {args.db}")
    print(f"Scalar metrics per profile: min={min(scalar_counts)}, "
          f"max={max(scalar_counts)}")
    flagged = [p for p in profiles if p.warnings]
    if flagged:
        print(f"{len(flagged)} profiles carry data-quality warnings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
