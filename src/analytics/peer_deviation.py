"""Peer-deviation signals: statistically unusual behavior vs the portfolio.

Uses the *modified* (robust) z-score — 0.6745·(x − median)/MAD — so a few
extreme CSEs cannot inflate the spread and mask their own outliers. Peer
groups below ``peer.min_group_size`` are too small to judge; signals return
None with that reason recorded by the engine.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from src.analytics.execution_gaps import make_finding
from src.analytics.finding import margin_above, severity_from
from src.analytics.profiles import PERIOD_ALL
from src.analytics.signal_common import SignalContext

SIGNAL_CATEGORY = "peer_deviation"

# ALL-window profile metrics subjected to peer comparison.
PEER_METRICS = ("closure_velocity_median_h", "inv_depth_mean", "esc_rate")


# ---------------------------------------------------------------------------
# Peer statistics (built once per run by the engine)
# ---------------------------------------------------------------------------


def build_peer_stats(all_profiles: List[Any],
                     frames: Optional[Dict[str, pd.DataFrame]] = None,
                     ) -> Dict[str, Dict[str, float]]:
    """Robust summary stats per metric across the portfolio's ALL profiles.

    ``alerts_per_asset_day`` is derived from raw frames because the profile
    stores density over the whole window, not a daily rate.
    """
    stats: Dict[str, Dict[str, float]] = {}
    by_metric: Dict[str, List[float]] = {m: [] for m in PEER_METRICS}
    for p in all_profiles:
        if p.period != PERIOD_ALL:
            continue
        for m in PEER_METRICS:
            v = p.metrics.get(m)
            if v is not None:
                by_metric[m].append(float(v))

    for metric, values in by_metric.items():
        s = _summarize(values)
        if s:
            stats[metric] = s

    if frames is not None:
        rates = _per_asset_daily_rates(frames)
        s = _summarize(rates)
        if s:
            stats["alerts_per_asset_day"] = s
    return stats


def _summarize(values: List[float]) -> Optional[Dict[str, float]]:
    if len(values) < 2:
        return None
    arr = np.asarray(values, dtype=float)
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median)))
    std = float(arr.std(ddof=0))
    return {"median": round(median, 6), "mad": round(mad, 6),
            "std": round(std, 6), "n": len(values)}


def _per_asset_daily_rates(frames: Dict[str, pd.DataFrame]) -> List[float]:
    alerts = frames.get("alerts")
    assets = frames.get("assets")
    if alerts is None or not len(alerts) or assets is None or not len(assets):
        return []
    ts = pd.to_datetime(alerts["timestamp"], errors="coerce").dropna()
    span_days = max(int((ts.max() - ts.min()).days) + 1, 1)
    sizes = assets.groupby("cse_id").size()
    counts = alerts.groupby("cse_id").size()
    rates = []
    for cse_id, n_alerts in counts.items():
        n_assets = int(sizes.get(cse_id, 0))
        if n_assets:
            rates.append(n_alerts / (n_assets * span_days))
    return rates


def modified_z(value: float, stat: Dict[str, float]) -> Optional[float]:
    """0.6745·(x−median)/MAD with std fallback when MAD collapses to 0."""
    if not stat or stat["n"] < 2:
        return None
    if stat["mad"] > 0:
        return 0.6745 * (value - stat["median"]) / stat["mad"]
    if stat["std"] > 0:
        return (value - stat["median"]) / stat["std"]
    return None


# ---------------------------------------------------------------------------
# Signals 16–18
# ---------------------------------------------------------------------------


def _detect_peer_outlier(
    ctx: SignalContext,
    signal_type: str,
    metric: str,
    *,
    concern_direction: str,
    human_unit: str,
    actions: list,
) -> Optional[Finding]:
    stat = ctx.peer_stats.get(metric)
    value = ctx.metric(metric, PERIOD_ALL)
    if not stat or stat.get("n", 0) < ctx.t("peer", "min_group_size"):
        return None
    if value is None:
        return None
    z = modified_z(float(value), stat)
    if z is None or abs(z) < ctx.t("peer", "outlier_z"):
        return None

    outlier_z = ctx.t("peer", "outlier_z")
    direction = "below" if z < 0 else "above"
    margin = margin_above(abs(z), outlier_z, outlier_z * 2.5)
    f = make_finding(
        ctx, signal_type, PERIOD_ALL,
        category=SIGNAL_CATEGORY,
        evidence={
            "metric": metric,
            "value": value,
            "peer_median": stat["median"],
            "peer_mad": stat["mad"],
            "peer_group_size": int(stat["n"]),
            "modified_z": round(z, 3),
            "outlier_threshold_z": outlier_z,
            "direction": direction,
            "concern_when": concern_direction,
        },
        logic=(
            f"{human_unit} of {value} is {abs(z):.1f} robust-z {direction} "
            f"the peer median ({stat['median']}, group n={int(stat['n'])})."
        ),
        confidence=round(min(1.0, 0.5 + margin / 2), 3),
        actions=actions,
        caveats=[
            f"Peer group contains {int(stat['n'])} CSEs; small groups make "
            f"z-scores noisy."
        ] if stat["n"] < 10 else [],
    )
    f.severity = severity_from(margin)
    return f


def detect_closure_velocity_outlier(ctx: SignalContext) -> Optional[Finding]:
    """Closure speed far from peers (fast suggests rubber-stamping, slow neglect)."""
    return _detect_peer_outlier(
        ctx, "closure_velocity_outlier", "closure_velocity_median_h",
        concern_direction="either tail",
        human_unit="Median closure time",
        actions=[
            "Sample recently closed cases for depth-of-review",
            "Compare closure workflows with peer CSEs",
        ],
    )


def detect_investigation_depth_outlier(ctx: SignalContext) -> Optional[Finding]:
    """Investigation depth far from peers (shallow is the primary concern)."""
    return _detect_peer_outlier(
        ctx, "investigation_depth_outlier", "inv_depth_mean",
        concern_direction="low",
        human_unit="Mean investigation depth",
        actions=[
            "Request case files underlying the shallow mean",
            "Review investigator training and templates",
        ],
    )


def detect_escalation_rate_outlier(ctx: SignalContext) -> Optional[Finding]:
    """Escalation rate far from peers (too few or trigger-happy both matter)."""
    return _detect_peer_outlier(
        ctx, "escalation_rate_outlier", "esc_rate",
        concern_direction="either tail",
        human_unit="Escalation rate",
        actions=[
            "Review the escalation decision log against policy criteria",
        ],
    )


SIGNALS = [
    ("closure_velocity_outlier", detect_closure_velocity_outlier),
    ("investigation_depth_outlier", detect_investigation_depth_outlier),
    ("escalation_rate_outlier", detect_escalation_rate_outlier),
]


def main(argv=None):
    from src.analytics.signal_engine import run_category_cli
    return run_category_cli(SIGNAL_CATEGORY, argv)


if __name__ == "__main__":
    raise SystemExit(main())
