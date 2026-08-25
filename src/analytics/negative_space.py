"""Negative-space signals: expected evidence that is *absent*.

Absence cannot contribute record IDs the way a bad pattern can — where a
finding fires on missing records, ``contributing_record_ids`` lists the
records that *should* have companions (the un-investigated alerts, the
silent assets), and the absence itself is documented in evidence/caveats.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from src.analytics.expected_evidence import DIMENSIONS, evidence_table_for
from src.analytics.execution_gaps import make_finding
from src.analytics.finding import (
    cap_ids,
    combined_confidence,
    margin_above,
    margin_below,
    sample_confidence,
    severity_from,
)
from src.analytics.signal_common import (
    PERIOD_ALL,
    SignalContext,
    esc_with_severity,
    inv_with_alerts,
    silent_assets,
)

SIGNAL_CATEGORY = "negative_space"


def _weekend_mask(ts: pd.Series) -> pd.Series:
    return pd.to_datetime(ts, errors="coerce").dt.weekday.ge(5)


# ---------------------------------------------------------------------------
# 6. alert_volume_gap
# ---------------------------------------------------------------------------


def detect_alert_volume_gap(ctx: SignalContext) -> Optional[Finding]:
    """Observed alert volume far below what the asset base implies."""
    t = ctx.thresholds["alert_volume_gap"]
    prof = ctx.profile(PERIOD_ALL)
    assets = ctx.cse_frames.get("assets")
    if prof is None or assets is None or len(assets) < t["min_assets"]:
        return None

    peer = ctx.peer_stats.get("alerts_per_asset_day")
    if not peer or peer.get("n", 0) < ctx.t("peer", "min_group_size"):
        return None

    # Peer stat is alerts per asset per day; expected volume scales with our
    # own asset count at that rate.
    expected_daily = float(peer["median"]) * len(assets)
    observed_daily = prof.metrics.get("alert_volume_per_day") or 0.0
    if expected_daily <= 0:
        return None
    ratio = observed_daily / expected_daily
    if ratio >= t["min_volume_ratio"]:
        return None
    margin = margin_below(ratio, t["min_volume_ratio"],
                          floor=t["ratio_bound"])
    f = make_finding(
        ctx, "alert_volume_gap", PERIOD_ALL,
        category=SIGNAL_CATEGORY,
        evidence={
            "observed_alerts_per_day": round(observed_daily, 4),
            "expected_alerts_per_day": round(expected_daily, 4),
            "ratio_observed_over_expected": round(ratio, 4),
            "peer_median_density_per_asset": peer["median"],
            "n_assets": int(len(assets)),
            "threshold": t["min_volume_ratio"],
        },
        logic=(
            f"Observed volume is {ratio:.0%} of the volume implied by "
            f"{len(assets)} assets at the peer-median rate — telemetry may "
            f"be under-reporting."
        ),
        confidence=combined_confidence(sample_confidence(len(assets), 20), margin),
        actions=[
            "Verify log-source coverage against the asset inventory",
            "Ask whether alerting rules were recently disabled or narrowed",
        ],
        quality_notes=list(prof.warnings),
    )
    f.severity = severity_from(margin)
    return f


# ---------------------------------------------------------------------------
# 7. missing_investigations
# ---------------------------------------------------------------------------


def detect_missing_investigations(ctx: SignalContext) -> Optional[Finding]:
    """High-severity alerts with no investigation record at all."""
    t = ctx.thresholds["missing_investigations"]
    alerts = ctx.cse_frames.get("alerts")
    joined = inv_with_alerts(ctx.cse_frames)
    if alerts is None or not len(alerts):
        return None
    high = alerts[alerts["severity"].isin(("CRITICAL", "HIGH"))]
    if len(high) < t["min_high_sev_alerts"]:
        return None
    investigated = set(joined["alert_id"]) if len(joined) else set()
    missing = high[~high["alert_id"].isin(investigated)]
    rate = len(missing) / len(high)
    if rate < t["max_missing_rate"]:
        return None
    margin = margin_above(rate, t["max_missing_rate"], t["rate_bound"])
    f = make_finding(
        ctx, "missing_investigations", PERIOD_ALL,
        category=SIGNAL_CATEGORY,
        evidence={
            "n_high_sev_alerts": int(len(high)),
            "n_without_investigation_record": int(len(missing)),
            "missing_rate": round(rate, 4),
            "threshold": t["max_missing_rate"],
        },
        logic=(
            f"{len(missing)} of {len(high)} CRITICAL/HIGH alerts "
            f"({rate:.0%}) have no investigation record in the submission."
        ),
        confidence=combined_confidence(sample_confidence(len(high), 50), margin),
        actions=[
            "Request investigation records for the flagged alert IDs",
            "Confirm whether the alerts were triaged outside this system",
        ],
        record_ids=cap_ids(missing["alert_id"].tolist(), ctx.thresholds),
    )
    f.severity = severity_from(margin)
    return f


# ---------------------------------------------------------------------------
# 8. missing_alert_categories
# ---------------------------------------------------------------------------


def detect_missing_alert_categories(ctx: SignalContext) -> Optional[Finding]:
    """Alert categories reported by nearly all peers but absent here."""
    t = ctx.thresholds["missing_alert_categories"]
    alerts = ctx.cse_frames.get("alerts")
    portfolio = ctx.frames.get("alerts")
    if alerts is None or portfolio is None or not len(portfolio):
        return None
    own = set(alerts["category"].dropna()) if len(alerts) else set()
    n_cses = max(portfolio["cse_id"].nunique() - 1, 1)  # peers exclude self

    presence: Dict[str, int] = {}
    for cat, g in portfolio.dropna(subset=["category"]).groupby("category"):
        n_with = g["cse_id"].nunique()
        if ctx.cse_id in set(g["cse_id"]):
            n_with -= 1
        presence[str(cat)] = n_with

    expected = sorted(
        c for c, n in presence.items()
        if c not in own and n / n_cses >= t["presence_frac"]
    )
    prof = ctx.profile(PERIOD_ALL)
    if not expected or not len(alerts) or \
            (prof and (prof.metrics.get("alert_volume_total") or 0) < t["min_alerts"]):
        return None
    f = make_finding(
        ctx, "missing_alert_categories", PERIOD_ALL,
        category=SIGNAL_CATEGORY,
        evidence={
            "categories_present": sorted(own),
            "categories_expected_but_absent": expected,
            "peer_presence_frac_required": t["presence_frac"],
        },
        logic=(
            f"No alerts of category {expected} were submitted, though "
            f">={t['presence_frac']:.0%} of peer CSEs report them — possible "
            f"detection-coverage gap."
        ),
        confidence=0.6,  # absence evidence; no sample-size signal available
        actions=[
            "Ask why these alert categories never appear in submissions",
            "Cross-check detection-rule coverage for the missing types",
        ],
        caveats=[
            "Absence of records is inferred from the rest of the portfolio's "
            "reporting behaviour; a legitimately different threat profile is "
            "possible.",
        ],
        quality_notes=list(prof.warnings) if prof else [],
    )
    f.severity = "MEDIUM" if len(expected) == 1 else "HIGH"
    return f


# ---------------------------------------------------------------------------
# 9. telemetry_absence
# ---------------------------------------------------------------------------


def detect_telemetry_absence(ctx: SignalContext) -> Optional[Finding]:
    """Whole groups of assets producing zero alerts."""
    t = ctx.thresholds["telemetry_absence"]
    alerts = ctx.cse_frames.get("alerts")
    assets = ctx.cse_frames.get("assets")
    if alerts is None or assets is None or not len(assets):
        return None

    findings: List[pd.DataFrame] = []
    for group_col in ("asset_type", "criticality"):
        stats = silent_assets(alerts, assets, group_col)
        stats = stats[stats["n_assets"] >= t["min_group_assets"]]
        stats = stats[stats["silent_share"] >= t["min_silent_share"]]
        if len(stats):
            stats = stats.assign(group_col=group_col)
            findings.append(stats)

    prof = ctx.profile(PERIOD_ALL)
    if not findings:
        return None
    table = pd.concat(findings, ignore_index=True)
    worst_idx = table["silent_share"].idxmax()
    worst = table.loc[worst_idx]
    silent_ids = assets[
        (assets[worst["group_col"]] == worst[worst["group_col"]])
    ]["asset_id"].tolist()
    margin = margin_above(float(worst["silent_share"]),
                          t["min_silent_share"], t["share_bound"])
    f = make_finding(
        ctx, "telemetry_absence", PERIOD_ALL,
        category=SIGNAL_CATEGORY,
        evidence={
            "groups_flagged": table.to_dict(orient="records"),
            "worst_group": str(worst[worst["group_col"]]),
            "worst_group_by": worst["group_col"],
            "worst_silent_share": float(worst["silent_share"]),
            "threshold": t["min_silent_share"],
        },
        logic=(
            f"{int(worst['n_silent'])} of {int(worst['n_assets'])} assets of "
            f"{worst['group_col']} '{worst[worst['group_col']]}' produced zero "
            f"alerts across the whole window — telemetry likely absent."
        ),
        confidence=combined_confidence(
            sample_confidence(int(worst["n_assets"]), 10), margin,
        ),
        actions=[
            "Confirm sensor deployment on the listed silent assets",
            "Reconcile asset inventory against actual data sources",
        ],
        record_ids=silent_ids[:ctx.t("_global", "max_record_ids")],
        quality_notes=list(prof.warnings) if prof else [],
    )
    f.severity = severity_from(margin)
    return f


# ---------------------------------------------------------------------------
# 10. escalation_absence
# ---------------------------------------------------------------------------


def detect_escalation_absence(ctx: SignalContext) -> Optional[Finding]:
    """Critical alerts (overall or weekend-specific) never escalated.

    Two sub-checks:
      a) many critical alerts but zero escalations traceable to them;
      b) critical alerts occur on weekends but no escalation ever did —
         an after-hours escalation gap.
    """
    t = ctx.thresholds["escalation_absence"]
    alerts = ctx.cse_frames.get("alerts")
    if alerts is None or not len(alerts):
        return None
    esc_joined = esc_with_severity(ctx.cse_frames)
    joined = inv_with_alerts(ctx.cse_frames)

    critical_ids = set(alerts.loc[alerts["severity"] == "CRITICAL", "alert_id"])
    n_critical = len(critical_ids)
    investigated_critical = set()
    if len(joined):
        investigated_critical = set(
            joined.loc[joined["severity"] == "CRITICAL", "investigation_id"]
        )
    escalated_inv_ids = set(esc_joined["investigation_id"]) if len(esc_joined) else set()

    subchecks = {}
    overall_fired = (
        n_critical >= t["min_critical_alerts"]
        and not (investigated_critical & escalated_inv_ids)
    )
    subchecks["zero_escalations_from_critical"] = overall_fired

    weekend_crit = alerts[alerts["severity"] == "CRITICAL"]
    weekend_crit = weekend_crit[_weekend_mask(weekend_crit["timestamp"])] \
        if len(weekend_crit) else weekend_crit.iloc[0:0]
    esc = ctx.cse_frames.get("escalations")
    weekend_esc_n = 0
    if esc is not None and len(esc):
        weekend_esc_n = int(_weekend_mask(esc["timestamp"]).sum())
    weekend_fired = (
        len(weekend_crit) >= t["min_weekend_critical"] and weekend_esc_n == 0
    )
    subchecks["no_weekend_escalations_despite_weekend_criticals"] = weekend_fired

    if not any(subchecks.values()):
        return None
    fired = [k for k, v in subchecks.items() if v]
    conf = combined_confidence(
        sample_confidence(n_critical, t["min_critical_alerts"] * 2),
        0.8,
    )
    f = make_finding(
        ctx, "escalation_absence", PERIOD_ALL,
        category=SIGNAL_CATEGORY,
        evidence={
            "subchecks_fired": fired,
            "n_critical_alerts": n_critical,
            "n_weekend_critical_alerts": int(len(weekend_crit)),
            "n_weekend_escalations": weekend_esc_n,
            "thresholds": {"min_critical_alerts": t["min_critical_alerts"],
                           "min_weekend_critical": t["min_weekend_critical"]},
        },
        logic=(
            "Escalation records absent where expected: " + "; ".join(fired) + "."
        ),
        confidence=conf,
        actions=[
            "Obtain the escalation policy and on-call rosters",
            "Trace a sample of critical incidents end-to-end",
        ],
    )
    f.severity = "HIGH" if overall_fired else "MEDIUM"
    return f


# ---------------------------------------------------------------------------
# 11. evidence_deficit
# ---------------------------------------------------------------------------


def detect_evidence_deficit(ctx: SignalContext) -> Optional[Finding]:
    """Total evidence below what the portfolio model expects for this CSE.

    Generalises negative space from 'category absent' to 'quantitatively
    thin': the expected-evidence model (see
    ``src.analytics.expected_evidence``) states how many alerts,
    investigations, evidence entries and escalations a portfolio-typical
    SOC would have produced given this CSE's size band and severity mix —
    every baseline estimated leave-self-out. A dimension is thin only when
    it clears BOTH its calibrated ratio gate AND the model band's lower
    edge; the worst dimension becomes the headline.
    """
    t = ctx.thresholds["evidence_deficit"]
    alerts = ctx.cse_frames.get("alerts")
    if alerts is None or len(alerts) < t["min_alerts"]:
        return None
    table = evidence_table_for(
        ctx.cse_id, ctx.frames, band_z=t["band_z"],
        overdispersion=t["overdispersion"],
    )
    if table is None:
        return None

    verdicts: List[Dict[str, Any]] = []
    for dim in DIMENSIONS:
        entry = table[dim]
        expected, observed = entry["expected"], entry["observed"]
        if expected is None or expected < t["min_expected"]:
            continue
        ratio = entry["ratio"]
        gate = t[f"min_ratio_{dim}"]
        # The band protects small-count dimensions: below the ratio gate
        # but inside the statistical band is not called thin.
        if ratio >= gate or observed >= entry["band_low"]:
            continue
        verdicts.append({
            "dimension": dim,
            "ratio": ratio,
            "gate": gate,
            "margin": margin_below(ratio, gate, t[f"ratio_bound_{dim}"]),
            "observed": observed,
            "expected": expected,
            "band_low": entry["band_low"],
            "band_high": entry["band_high"],
        })

    if not verdicts:
        return None
    worst = max(verdicts, key=lambda v: v["margin"])
    f = make_finding(
        ctx, "evidence_deficit", PERIOD_ALL,
        category=SIGNAL_CATEGORY,
        evidence={
            "headline_dimension": worst["dimension"],
            "headline_observed": worst["observed"],
            "headline_expected": worst["expected"],
            "headline_ratio": worst["ratio"],
            "headline_band_low": worst["band_low"],
            "headline_band_high": worst["band_high"],
            "min_ratio_applied": worst["gate"],
            "dimensions": {v["dimension"]: {
                "observed": v["observed"], "expected": v["expected"],
                "ratio": v["ratio"], "band_low": v["band_low"],
                "band_high": v["band_high"]} for v in verdicts},
        },
        logic=(
            f"{worst['dimension'].replace('_', ' ').capitalize()} are "
            f"{worst['ratio']:.0%} of the portfolio-expected volume for "
            f"this alert stream ({worst['observed']:,.0f} observed vs "
            f"{worst['expected']:,.0f} expected; {t['band_z']:g}σ band "
            f"{worst['band_low']:,.0f}–{worst['band_high']:,.0f}) — "
            f"evidence thinner than the composition implies."
        ),
        confidence=combined_confidence(
            sample_confidence(len(alerts), 100), worst["margin"],
        ),
        actions=[
            "Ask why submitted evidence falls short of the volume the "
            "alert stream implies",
            "Reconcile investigation and escalation records against the "
            "flagged dimension",
            "Check whether records are held in a system this submission "
            "does not cover",
        ],
        caveats=[
            "Expectations are portfolio baselines conditioned on size band "
            "and severity mix, estimated without the CSE's own records; a "
            "legitimately quieter threat profile is possible.",
        ],
        quality_notes=list(ctx.profile(PERIOD_ALL).warnings)
        if ctx.profile(PERIOD_ALL) else [],
    )
    f.severity = severity_from(worst["margin"])
    return f


SIGNALS = [
    ("alert_volume_gap", detect_alert_volume_gap),
    ("missing_investigations", detect_missing_investigations),
    ("missing_alert_categories", detect_missing_alert_categories),
    ("telemetry_absence", detect_telemetry_absence),
    ("escalation_absence", detect_escalation_absence),
    ("evidence_deficit", detect_evidence_deficit),
]


def main(argv=None):
    from src.analytics.signal_engine import run_category_cli
    return run_category_cli(SIGNAL_CATEGORY, argv)


if __name__ == "__main__":
    raise SystemExit(main())
