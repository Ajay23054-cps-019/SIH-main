"""Behavioral-anomaly signals: unusual temporal or operational patterns."""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from src.analytics.execution_gaps import make_finding
from src.analytics.finding import (
    combined_confidence,
    margin_above,
    sample_confidence,
    severity_from,
)
from src.analytics.signal_common import (
    PERIOD_ALL,
    SignalContext,
    inv_with_alerts,
)

SIGNAL_CATEGORY = "behavioral_anomaly"


# ---------------------------------------------------------------------------
# 11. temporal_drift
# ---------------------------------------------------------------------------


def detect_temporal_drift(ctx: SignalContext) -> Optional[Finding]:
    """Single-quarter step change in depth or closure velocity.

    Distinct from quality_degradation (cumulative multi-quarter trend):
    this fires on one abrupt quarter-over-quarter jump.
    """
    t = ctx.thresholds["temporal_drift"]
    periods = ctx.quarter_periods()
    best: Optional[Tuple[str, str, str, float]] = None  # metric, from, to, strength

    depth_by_q = {p: ctx.metric("inv_depth_mean", p) for p in periods}
    vel_by_q = {p: ctx.metric("closure_velocity_median_h", p) for p in periods}

    for a, b in zip(periods, periods[1:]):
        d_a, d_b = depth_by_q.get(a), depth_by_q.get(b)
        if d_a and d_b and d_a > 0:
            drop = (d_a - d_b) / d_a
            if drop >= t["depth_drop_frac"]:
                strength = drop / max(1.0 - t["depth_drop_frac"], 1e-9)
                if best is None or strength > best[3]:
                    best = ("inv_depth_mean", a, b, min(strength, 1.0))
        v_a, v_b = vel_by_q.get(a), vel_by_q.get(b)
        if v_a and v_b and v_a > 0:
            ratio = v_b / v_a
            if ratio >= t["velocity_jump_factor"] or ratio <= 1 / t["velocity_jump_factor"]:
                strength = abs(np.log(ratio)) / np.log(t["velocity_jump_factor"])
                if best is None or strength > best[3]:
                    best = ("closure_velocity_median_h", a, b, min(strength, 1.0))

    if best is None:
        return None
    metric, from_p, to_p, strength = best
    evidence = {
        "metric": metric,
        "from_period": from_p,
        "to_period": to_p,
        "value_from": depth_by_q.get(from_p) if metric == "inv_depth_mean"
        else vel_by_q.get(from_p),
        "value_to": depth_by_q.get(to_p) if metric == "inv_depth_mean"
        else vel_by_q.get(to_p),
        "thresholds": {"depth_drop_frac": t["depth_drop_frac"],
                       "velocity_jump_factor": t["velocity_jump_factor"]},
    }
    if metric == "inv_depth_mean":
        logic_txt = (
            f"Investigation depth stepped from "
            f"{evidence['value_from']:.2f} to {evidence['value_to']:.2f} between "
            f"{from_p} and {to_p}."
        )
    else:
        logic_txt = (
            f"Closure velocity jumped from {evidence['value_from']:.2f}h to "
            f"{evidence['value_to']:.2f}h between {from_p} and {to_p}."
        )
    conf = combined_confidence(sample_confidence(len(periods), 4), strength)
    f = make_finding(
        ctx, "temporal_drift", to_p,
        category=SIGNAL_CATEGORY,
        evidence=evidence,
        logic=logic_txt + " A single-quarter step change warrants explanation.",
        confidence=conf,
        actions=[
            "Ask what changed in the SOC during the transition quarter",
            "Review staffing, tooling and process changes for that period",
        ],
    )
    f.severity = severity_from(strength)
    return f


# ---------------------------------------------------------------------------
# 12. unusual_quiet_period
# ---------------------------------------------------------------------------


def detect_unusual_quiet_period(ctx: SignalContext) -> Optional[Finding]:
    """Alert stream goes silent far longer than operating tempo implies.

    Three triggers, calibrated so bursty-but-active feeds stay quiet:
      a) many gaps beyond ``quiet_gap_hours`` (chronic silences);
      b) one single gap beyond ``max_gap_hours`` (outright blackout);
      c) the longest gap dwarfing the CSE's own median alert cadence
         (adaptive: catches dead feeds regardless of volume).
    """
    t = ctx.thresholds["unusual_quiet_period"]
    prof = ctx.profile(PERIOD_ALL)
    alerts = ctx.cse_frames.get("alerts")
    if prof is None or alerts is None or not len(alerts):
        return None

    quiet_n = int(prof.metrics.get("quiet_period_count") or 0)
    max_gap = float(prof.metrics.get("max_gap_hours") or 0.0)

    ts = pd.to_datetime(alerts["timestamp"], errors="coerce").dropna().sort_values()
    median_gap = 0.0
    if len(ts) > 1:
        gaps_h = ts.diff().dt.total_seconds().div(3600)
        median_gap = float(gaps_h.median() or 0.0)

    fired = {
        "chronic_gaps": quiet_n >= t["min_quiet_periods"],
        "blackout_gap": max_gap >= t["max_gap_hours"],
        "gap_vs_own_cadence": (
            median_gap > 0 and max_gap >= t["gap_median_multiple"] * median_gap
        ),
    }
    if not any(fired.values()):
        return None

    margin = max(
        margin_above(float(quiet_n), float(t["min_quiet_periods"]),
                     float(t["min_quiet_periods"] * 2)),
        margin_above(max_gap, t["max_gap_hours"], t["max_gap_hours"] * 2),
        margin_above(
            max_gap / median_gap if median_gap > 0 else 0.0,
            t["gap_median_multiple"], t["gap_median_multiple"] * 2,
        ),
    )
    f = make_finding(
        ctx, "unusual_quiet_period", PERIOD_ALL,
        category=SIGNAL_CATEGORY,
        evidence={
            "triggers_fired": [k for k, v in fired.items() if v],
            "quiet_period_count": quiet_n,
            "max_gap_hours": round(max_gap, 2),
            "median_alert_gap_hours": round(median_gap, 3),
            "thresholds": {k: v for k, v in t.items()},
        },
        logic=(
            f"Longest inter-alert gap {max_gap:.1f}h against a median cadence "
            f"of {median_gap:.1f}h ({quiet_n} gaps > {t['quiet_gap_hours']}h) — "
            f"telemetry may be going dark."
        ),
        confidence=combined_confidence(0.5, margin),
        actions=["Verify telemetry continuity for the silent windows"],
        quality_notes=list(prof.warnings),
    )
    f.severity = severity_from(margin) if margin >= 0.25 else "LOW"
    return f


# ---------------------------------------------------------------------------
# 13. bulk_closure_pattern
# ---------------------------------------------------------------------------


def detect_bulk_closure_pattern(ctx: SignalContext) -> Optional[Finding]:
    """Mass closures concentrated on individual days."""
    t = ctx.thresholds["bulk_closure_pattern"]
    alerts = ctx.cse_frames.get("alerts")
    if alerts is None or not len(alerts):
        return None
    closed = alerts[alerts["status"] == "closed"].copy()
    closed["closure_day"] = pd.to_datetime(
        closed["closure_timestamp"], errors="coerce"
    ).dt.date
    closed = closed.dropna(subset=["closure_day"])
    per_day = closed.groupby("closure_day").size()
    if len(per_day) < t["min_days"]:
        return None
    peak_day = per_day.idxmax()
    peak = int(per_day.max())
    median = float(per_day.median())
    if median <= 0:
        return None
    ratio = peak / median
    if ratio < t["burst_factor"] or peak < t["min_peak_closures"]:
        return None
    margin = margin_above(ratio, t["burst_factor"], t["burst_factor"] * 2)
    day_ids = closed.loc[closed["closure_day"] == peak_day, "alert_id"].tolist()
    f = make_finding(
        ctx, "bulk_closure_pattern", PERIOD_ALL,
        category=SIGNAL_CATEGORY,
        evidence={
            "peak_closure_day": str(peak_day),
            "peak_closures": peak,
            "median_daily_closures": round(median, 1),
            "burst_ratio": round(ratio, 2),
            "n_active_days": int(len(per_day)),
            "threshold": t["burst_factor"],
        },
        logic=(
            f"{peak} alerts were closed on {peak_day} — {ratio:.1f}x the "
            f"median daily rate — consistent with batch/rubber-stamp closure."
        ),
        confidence=combined_confidence(sample_confidence(int(len(closed)), 200),
                                       margin),
        actions=["Sample closures from the flagged day and review their depth"],
        record_ids=day_ids[:ctx.t("_global", "max_record_ids")],
    )
    f.severity = severity_from(margin)
    return f


# ---------------------------------------------------------------------------
# 14. shift_variance
# ---------------------------------------------------------------------------

SHIFTS = {"day": range(7, 15), "evening": range(15, 23), "night": (23, 0, 1, 2, 3, 4, 5, 6)}


def detect_shift_variance(ctx: SignalContext) -> Optional[Finding]:
    """Investigation quality differs significantly across shift buckets."""
    t = ctx.thresholds["shift_variance"]
    joined = inv_with_alerts(ctx.cse_frames)
    if joined is None or not len(joined):
        return None
    opened = pd.to_datetime(joined["timestamp_open"], errors="coerce")
    hours = opened.dt.hour
    means: dict = {}
    counts: dict = {}
    for name, hours_def in SHIFTS.items():
        mask = hours.isin(list(hours_def)) if not isinstance(hours_def, range) \
            else hours.isin(hours_def)
        subset = joined[mask]
        counts[name] = int(len(subset))
        means[name] = float(subset["evidence_entries"].astype(float).mean()) \
            if len(subset) else None

    valid = {k: v for k, v in means.items() if v is not None}
    small = [k for k, n in counts.items() if 0 < n < t["min_per_shift"]]
    if len(valid) < 2:
        return None
    hi_k = max(valid, key=valid.get)
    lo_k = min(valid, key=valid.get)
    hi, lo = valid[hi_k], valid[lo_k]
    if lo <= 0:
        return None
    ratio = hi / lo
    if ratio < t["max_shift_ratio"]:
        return None
    margin = margin_above(ratio, t["max_shift_ratio"],
                          t["max_shift_ratio"] * 1.5)
    notes = [f"Shift '{k}' has only {counts[k]} cases" for k in small]
    f = make_finding(
        ctx, "shift_variance", PERIOD_ALL,
        category=SIGNAL_CATEGORY,
        evidence={
            "mean_depth_by_shift": {k: round(v, 3) for k, v in valid.items()},
            "n_by_shift": counts,
            "max_min_ratio": round(ratio, 3),
            "strongest_shift": hi_k,
            "weakest_shift": lo_k,
            "threshold": t["max_shift_ratio"],
        },
        logic=(
            f"Mean investigation depth on the {hi_k} shift ({hi:.2f}) is "
            f"{ratio:.2f}x the {lo_k} shift ({lo:.2f}) — quality depends on "
            f"who is on duty."
        ),
        confidence=combined_confidence(
            sample_confidence(min(counts.values()), t["min_per_shift"]), margin,
        ),
        actions=["Compare case files across shifts for the same alert classes"],
        quality_notes=notes,
    )
    f.severity = severity_from(margin)
    return f


# ---------------------------------------------------------------------------
# 15. recurring_incident
# ---------------------------------------------------------------------------


def detect_recurring_incident(ctx: SignalContext) -> Optional[Finding]:
    """The same (asset, category) pattern keeps firing without resolution."""
    t = ctx.thresholds["recurring_incident"]
    alerts = ctx.cse_frames.get("alerts")
    if alerts is None or not len(alerts):
        return None
    grouped = alerts.dropna(subset=["asset_id"]).groupby(["asset_id", "category"])
    best: Optional[Tuple[tuple, int, float]] = None
    for key, g in grouped:
        n = len(g)
        if n < t["min_repeats"]:
            continue
        unclosed_share = float((g["status"] != "closed").mean())
        if unclosed_share < t["min_unclosed_share"]:
            continue
        score = (n, unclosed_share)
        if best is None or score > (best[1], best[2]):
            best = (key, n, unclosed_share)
    if best is None:
        return None
    (asset_id, category), n, unclosed_share = best
    group = alerts[(alerts["asset_id"] == asset_id) & (alerts["category"] == category)]
    ids = group.sort_values("timestamp")["alert_id"].tolist()
    f = make_finding(
        ctx, "recurring_incident", PERIOD_ALL,
        category=SIGNAL_CATEGORY,
        evidence={
            "asset_id": asset_id,
            "category": str(category),
            "occurrences": n,
            "unclosed_share": round(unclosed_share, 4),
            "first_seen": str(group["timestamp"].min()),
            "last_seen": str(group["timestamp"].max()),
            "thresholds": {"min_repeats": t["min_repeats"],
                           "min_unclosed_share": t["min_unclosed_share"]},
        },
        logic=(
            f"'{category}' alerts on asset {asset_id} fired {n} times with "
            f"{unclosed_share:.0%} still unclosed — recurring pattern without "
            f"resolution."
        ),
        confidence=combined_confidence(sample_confidence(n, t["min_repeats"] * 2),
                                       unclosed_share),
        actions=[
            "Ask for the root-cause analysis of this recurring pattern",
            "Check whether a case was ever opened covering these alerts",
        ],
        record_ids=ids[:ctx.t("_global", "max_record_ids")],
    )
    f.severity = "MEDIUM" if unclosed_share < 0.8 else "HIGH"
    return f


# ---------------------------------------------------------------------------
# 16. changepoint_drift
# ---------------------------------------------------------------------------


def _best_single_changepoint(values: List[float], min_segment: int = 2
                             ) -> Tuple[float, int, float, float, float]:
    """Exhaustive single-change-point search (two-segment mean model).

    Returns (sse_split, split_index, mean_before, mean_after, sse_flat).
    Both segments must hold at least ``min_segment`` points, so the model
    always describes a *sustained* level shift — never a single anomalous
    quarter (that is temporal_drift's job). With the handful of quarterly
    points a profile window holds, exhaustive search is exact, cheaper than
    CUSUM approximations, and deterministic.
    """
    n = len(values)
    flat_mean = sum(values) / n
    sse_flat = sum((v - flat_mean) ** 2 for v in values)
    best: Optional[Tuple[float, int, float, float]] = None
    for k in range(min_segment, n - min_segment + 1):
        pre, post = values[:k], values[k:]
        m1 = sum(pre) / len(pre)
        m2 = sum(post) / len(post)
        sse = (sum((v - m1) ** 2 for v in pre)
               + sum((v - m2) ** 2 for v in post))
        if best is None or sse < best[0]:
            best = (sse, k, m1, m2)
    if best is None:                     # window too short for two segments
        best = (sse_flat, 0, flat_mean, flat_mean)
    return best + (sse_flat,)  # type: ignore[return-value]


def detect_changepoint_drift(ctx: SignalContext) -> Optional[Finding]:
    """Locates WHERE a quality decline began, not just THAT it declines.

    Single change-point search on quarterly investigation depth: the split
    that best separates a before/after level names the quarter the decline
    started. Complements quality_degradation (overall trend) and
    temporal_drift (single-quarter jump) with a dated onset. A split only
    counts when both segments are sustained (``min_segment`` quarters each)
    and the two-level model explains most of the window's variance
    (``min_explained_share``) — one bad quarter is not a regime change.
    """
    t = ctx.thresholds["changepoint_drift"]
    min_segment = int(t["min_segment"])
    periods = ctx.quarter_periods()
    series = [(p, ctx.metric("inv_depth_mean", p)) for p in periods]
    series = [(p, v) for p, v in series
              if v is not None and math.isfinite(v)]
    if len(series) < max(int(t["min_points"]), 2 * min_segment):
        return None
    values = [v for _, v in series]
    sse_split, k, m_pre, m_post, sse_flat = _best_single_changepoint(
        values, min_segment)
    drop = m_pre - m_post
    drop_frac = drop / m_pre if m_pre > 0 else 0.0
    if drop <= 0 or drop_frac < t["min_drop_frac"]:
        return None
    explained = 1 - sse_split / sse_flat if sse_flat > 0 else 0.0
    if explained < t["min_explained_share"]:
        return None          # an outlier quarter, not a level shift
    margin = min(margin_above(drop, t["min_drop"], t["drop_bound"]),
                 margin_above(drop_frac, t["min_drop_frac"], t["frac_bound"]))
    if margin <= 0:
        return None          # at least one leg below its threshold
    change_quarter = series[k][0]
    f = make_finding(
        ctx, "changepoint_drift", change_quarter,
        category=SIGNAL_CATEGORY,
        evidence={
            "depth_by_quarter": {p: v for p, v in series},
            "change_quarter": change_quarter,
            "change_index": k,
            "mean_before": round(m_pre, 4),
            "mean_after": round(m_post, 4),
            "drop": round(drop, 4),
            "drop_frac": round(drop_frac, 4),
            "sse_split": round(sse_split, 4),
            "sse_flat": round(sse_flat, 4),
            "explained_share": round(explained, 4),
            "thresholds": {"min_drop": t["min_drop"],
                           "min_drop_frac": t["min_drop_frac"],
                           "min_explained_share": t["min_explained_share"]},
        },
        logic=(
            f"Quarterly investigation depth averages {m_pre:.2f} entries "
            f"before {change_quarter} and {m_post:.2f} from that quarter on — "
            f"a step decline of {drop:.2f} entries ({drop_frac:.0%}) located "
            f"at {change_quarter} by single change-point search "
            f"({explained:.0%} of level variance explained). The decline has "
            "a start date; ask what changed in the SOC at that point."
        ),
        confidence=combined_confidence(sample_confidence(len(series), 4), margin),
        actions=[
            f"Ask what changed in the SOC in or just before {change_quarter}",
            "Compare staffing, tooling and process changes against the "
            "onset quarter",
            "Sample case files from before and after the change point",
        ],
    )
    f.severity = severity_from(margin)
    return f


SIGNALS = [
    ("temporal_drift", detect_temporal_drift),
    ("unusual_quiet_period", detect_unusual_quiet_period),
    ("bulk_closure_pattern", detect_bulk_closure_pattern),
    ("shift_variance", detect_shift_variance),
    ("recurring_incident", detect_recurring_incident),
    ("changepoint_drift", detect_changepoint_drift),
]


def main(argv=None):
    from src.analytics.signal_engine import run_category_cli
    return run_category_cli(SIGNAL_CATEGORY, argv)


if __name__ == "__main__":
    raise SystemExit(main())
