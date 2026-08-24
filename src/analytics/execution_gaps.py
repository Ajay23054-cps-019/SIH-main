"""Execution-gap signals: claimed/expected behavior vs observed evidence.

Each ``detect_*`` is a pure function returning an optional Finding. All
return None (silently, by contract — the engine logs) when the data needed
to evaluate the signal is missing or below the minimum sample size.
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np

from src.analytics.finding import (
    Finding,
    combined_confidence,
    finding_id,
    margin_above,
    margin_below,
    sample_confidence,
    severity_from,
)
from src.analytics.signal_common import (
    PERIOD_ALL,
    SignalContext,
    inv_with_alerts,
)

SIGNAL_CATEGORY = "execution_gap"


def make_finding(ctx: SignalContext, signal_type: str, period: str, *,
                 evidence: dict, logic: str, confidence: float, actions: List[str],
                 record_ids: Optional[List[str]] = None,
                 quality_notes: Optional[List[str]] = None,
                 caveats: Optional[List[str]] = None,
                 category: Optional[str] = None) -> Finding:
    """Shared Finding factory for all signal modules (severity set by caller)."""
    return Finding(
        finding_id=finding_id(ctx.cse_id, signal_type),
        cse_id=ctx.cse_id,
        signal_type=signal_type,
        signal_category=category or SIGNAL_CATEGORY,
        period=period,
        severity="LOW",  # replaced by caller when margin is computed
        confidence=confidence,
        evidence=evidence,
        contributing_record_ids=record_ids or [],
        detection_logic=logic,
        caveats=caveats or [],
        recommended_actions=actions,
        data_quality_notes=quality_notes or [],
        created_at=None,  # stamped by the engine at persistence time
    )


# Backwards-compatible alias used throughout this module.
_finding = make_finding


# ---------------------------------------------------------------------------
# 1. superficial_closure
# ---------------------------------------------------------------------------


def detect_superficial_closure(ctx: SignalContext) -> Optional[Finding]:
    """Fast median closure AND shallow investigations in the same quarter."""
    t = ctx.thresholds["superficial_closure"]
    for period in reversed(ctx.quarter_periods()):
        prof = ctx.profile(period)
        velocity = prof.metrics.get("closure_velocity_median_h")
        depth = prof.metrics.get("inv_depth_median")
        n_alerts = prof.metrics.get("alert_volume_total") or 0
        if velocity is None or depth is None:
            continue
        if n_alerts < t["min_alerts"]:
            continue
        if velocity <= t["max_closure_hours"] and depth <= t["shallow_depth_max"]:
            m_vel = margin_below(velocity, t["max_closure_hours"],
                                 floor=t["velocity_bound"])
            m_depth = margin_below(depth, t["shallow_depth_max"],
                                  floor=t["depth_bound"])
            margin = max(m_vel, m_depth)
            conf = combined_confidence(
                sample_confidence(n_alerts, 100),
                min(m_vel, m_depth),
            )
            f = _finding(
                ctx, "superficial_closure", period,
                evidence={
                    "period": period,
                    "closure_velocity_median_h": velocity,
                    "inv_depth_median": depth,
                    "n_alerts": int(n_alerts),
                    "thresholds": {"max_closure_hours": t["max_closure_hours"],
                                   "shallow_depth_max": t["shallow_depth_max"]},
                },
                logic=(
                    f"Median alert-to-closure time {velocity}h is at/below "
                    f"{t['max_closure_hours']}h while median investigation "
                    f"depth is {depth} entries (at/below {t['shallow_depth_max']}) "
                    f"in {period}: closures appear fast but shallow."
                ),
                confidence=conf,
                actions=[
                    "Request case files for a sample of rapidly closed alerts",
                    "Ask the CSE to walk through its closure workflow",
                ],
                quality_notes=_profile_quality_notes(prof),
            )
            f.severity = severity_from(margin)
            return f
    return None


# ---------------------------------------------------------------------------
# 2. escalation_without_action
# ---------------------------------------------------------------------------


def detect_escalation_without_action(ctx: SignalContext) -> Optional[Finding]:
    """Escalations logged but follow-through rate below threshold."""
    t = ctx.thresholds["escalation_without_action"]
    esc = ctx.cse_frames.get("escalations")
    joined = inv_with_alerts(ctx.cse_frames)
    if esc is None or not len(esc) or not len(joined):
        return None
    linked = esc[esc["investigation_id"].isin(set(joined["investigation_id"]))]
    if len(linked) < t["min_escalations"]:
        return None
    followup = linked["has_followup"].dropna().astype(bool)
    if not len(followup):
        return None
    rate = float(followup.mean())
    if rate >= t["min_followthrough"]:
        return None
    margin = margin_below(rate, t["min_followthrough"])
    no_action_ids = linked.loc[~linked["has_followup"].astype(bool),
                               "escalation_id"].tolist()
    f = _finding(
        ctx, "escalation_without_action", PERIOD_ALL,
        evidence={
            "n_escalations_linked": int(len(linked)),
            "followthrough_rate": round(rate, 4),
            "n_without_followup": int((~followup).sum()),
            "threshold": t["min_followthrough"],
        },
        logic=(
            f"{int((~followup).sum())} of {len(linked)} escalations have no "
            f"recorded follow-up action (follow-through rate {rate:.2f} < "
            f"{t['min_followthrough']})."
        ),
        confidence=combined_confidence(sample_confidence(len(linked), 10), margin),
        actions=[
            "Obtain the post-escalation action log",
            "Confirm recipients acted on escalated incidents",
        ],
        record_ids=no_action_ids,
    )
    f.severity = severity_from(margin)
    return f


# ---------------------------------------------------------------------------
# 3. quality_degradation
# ---------------------------------------------------------------------------


def detect_quality_degradation(ctx: SignalContext) -> Optional[Finding]:
    """Investigation depth declining across quarters."""
    t = ctx.thresholds["quality_degradation"]
    periods = ctx.quarter_periods()
    series = [(p, ctx.metric("inv_depth_mean", p)) for p in periods]
    series = [(p, v) for p, v in series if v is not None]
    if len(series) < t["min_quarters"]:
        return None
    values = [v for _, v in series]
    first, last = values[0], values[-1]
    if first <= 0:
        return None
    decline_frac = (first - last) / first
    if decline_frac < t["min_decline_frac"]:
        return None
    slope = float(np.polyfit(range(len(values)), values, 1)[0])
    margin = margin_above(decline_frac, t["min_decline_frac"],
                          t["decline_bound"])
    f = _finding(
        ctx, "quality_degradation", series[-1][0],
        evidence={
            "depth_by_quarter": {p: v for p, v in series},
            "decline_frac_first_to_last": round(decline_frac, 4),
            "slope_per_quarter": round(slope, 4),
            "threshold": t["min_decline_frac"],
        },
        logic=(
            f"Investigation depth declined from {first:.2f} to {last:.2f} "
            f"entries ({decline_frac:.0%}) over {len(series)} quarters; "
            f"linear slope {slope:.2f}/quarter."
        ),
        confidence=combined_confidence(sample_confidence(len(series), 3), margin),
        actions=[
            "Compare Q1 vs latest-quarter investigation case files",
            "Ask whether staffing or tooling changes explain the trend",
        ],
        quality_notes=_series_quality_notes(series),
    )
    f.severity = severity_from(margin)
    return f


# ---------------------------------------------------------------------------
# 4. severity_mismatch
# ---------------------------------------------------------------------------


def detect_severity_mismatch(ctx: SignalContext) -> Optional[Finding]:
    """High-severity alerts closed without any linked investigation."""
    t = ctx.thresholds["severity_mismatch"]
    alerts = ctx.cse_frames.get("alerts")
    joined = inv_with_alerts(ctx.cse_frames)
    if alerts is None or not len(alerts):
        return None
    closed_hi = alerts[
        (alerts["status"] == "closed")
        & (alerts["severity"].isin(("CRITICAL", "HIGH")))
    ]
    if len(closed_hi) < t["min_high_sev_closed"]:
        return None
    investigated = set(joined["alert_id"]) if len(joined) else set()
    missing = closed_hi[~closed_hi["alert_id"].isin(investigated)]
    rate = len(missing) / len(closed_hi)
    if rate < t["max_triage_only_rate"]:
        return None
    margin = margin_above(rate, t["max_triage_only_rate"], t["rate_bound"])
    prof = ctx.profile(PERIOD_ALL)
    f = _finding(
        ctx, "severity_mismatch", PERIOD_ALL,
        evidence={
            "n_high_sev_closed": int(len(closed_hi)),
            "n_without_investigation": int(len(missing)),
            "triage_only_rate": round(rate, 4),
            "threshold": t["max_triage_only_rate"],
        },
        logic=(
            f"{len(missing)} of {len(closed_hi)} closed CRITICAL/HIGH alerts "
            f"({rate:.0%}) have no investigation record — closed as if benign."
        ),
        confidence=combined_confidence(sample_confidence(len(closed_hi), 50), margin),
        actions=[
            "Request closure justification for flagged alert IDs",
            "Re-open a sample of uninvestigated high-severity closures",
        ],
        record_ids=missing["alert_id"].tolist(),
        quality_notes=_profile_quality_notes(prof),
    )
    f.severity = severity_from(margin)
    return f


# ---------------------------------------------------------------------------
# 5. template_investigation
# ---------------------------------------------------------------------------


def detect_template_investigation(ctx: SignalContext) -> Optional[Finding]:
    """Investigation notes are highly repetitive (copy-paste pattern)."""
    t = ctx.thresholds["template_investigation"]
    inv = ctx.cse_frames.get("investigations")
    if inv is None or not len(inv):
        return None
    notes = inv["notes"].dropna()
    notes = notes[notes.astype(str).str.strip() != ""]
    if len(notes) < t["min_investigations"]:
        return None
    n_unique = int(notes.nunique())
    unique_ratio = n_unique / len(notes)
    if unique_ratio >= t["max_unique_ratio"]:
        return None
    # Map duplicated note texts back to example investigation IDs.
    dup_texts = set(notes.value_counts().loc[lambda s: s > 1].index)
    example_ids = inv.loc[inv["notes"].isin(dup_texts), "investigation_id"] \
        .dropna().tolist()[:50]
    margin = margin_below(unique_ratio, t["max_unique_ratio"])
    f = _finding(
        ctx, "template_investigation", PERIOD_ALL,
        evidence={
            "n_investigations": int(len(notes)),
            "n_unique_notes": n_unique,
            "unique_ratio": round(unique_ratio, 4),
            "most_common_note_count": int(notes.value_counts().iloc[0]),
            "threshold": t["max_unique_ratio"],
        },
        logic=(
            f"Only {n_unique} distinct note texts across {len(notes)} "
            f"investigations (unique ratio {unique_ratio:.2f} < "
            f"{t['max_unique_ratio']}) — notes appear templated."
        ),
        confidence=combined_confidence(sample_confidence(len(notes), 30), margin),
        actions=[
            "Request the underlying evidence attachments for templated cases",
            "Interview analysts about note-taking workflow",
        ],
        record_ids=list(example_ids)[:ctx.t("_global", "max_record_ids")],
    )
    f.severity = severity_from(margin)
    return f


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _profile_quality_notes(profile) -> List[str]:
    return list(profile.warnings) if profile else []


def _series_quality_notes(series) -> List[str]:
    gaps = [p for p, v in series if v is None]
    return [f"Missing depth metric for {p}" for p in gaps]


SIGNALS = [
    ("superficial_closure", detect_superficial_closure),
    ("escalation_without_action", detect_escalation_without_action),
    ("quality_degradation", detect_quality_degradation),
    ("severity_mismatch", detect_severity_mismatch),
    ("template_investigation", detect_template_investigation),
]


def main(argv=None):
    from src.analytics.signal_engine import run_category_cli
    return run_category_cli(SIGNAL_CATEGORY, argv)


if __name__ == "__main__":
    raise SystemExit(main())
