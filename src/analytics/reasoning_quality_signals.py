"""Reasoning Quality signals for supervisory assessment.

Detects execution gaps hidden in the justification content of SOC
investigation notes. Statistical analysis cannot see the difference between
"checked" and a detailed technical investigation. These signals can.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.analytics.finding import Finding
from src.analytics.reasoning_quality import (
    SEVERITY_DEPTH_EXPECTED,
    analyze_reasoning_quality,
    coherence_score,
    detect_template_notes,
    parse_justification,
)
from src.analytics.signal_common import SignalContext


def _get_investigations(ctx: SignalContext) -> List[Dict[str, Any]]:
    """Extract investigation records from context, handling DataFrames."""
    inv = ctx.cse_frames.get("investigations", [])
    if hasattr(inv, "to_dict"):
        return inv.to_dict(orient="records")
    return list(inv) if inv else []


def _get_alerts(ctx: SignalContext) -> List[Dict[str, Any]]:
    """Extract alert records from context, handling DataFrames."""
    alerts = ctx.cse_frames.get("alerts", [])
    if hasattr(alerts, "to_dict"):
        return alerts.to_dict(orient="records")
    return list(alerts) if alerts else []


def _get_escalations(ctx: SignalContext) -> List[Dict[str, Any]]:
    """Extract escalation records from context, handling DataFrames."""
    esc = ctx.cse_frames.get("escalations", [])
    if hasattr(esc, "to_dict"):
        return esc.to_dict(orient="records")
    return list(esc) if esc else []


def _shallow_justification(ctx: SignalContext) -> Optional[Finding]:
    alerts = _get_alerts(ctx)
    investigations = _get_investigations(ctx)
    escalations = _get_escalations(ctx)
    if not investigations or not alerts:
        return None
    result = analyze_reasoning_quality(ctx.cse_id, investigations, alerts, escalations)
    if result.shallow_justification_count == 0:
        return None
    high_inv = [inv for inv in investigations if inv.get("alert_id", "") in
                {a["alert_id"]: a for a in alerts if a.get("severity") in ("HIGH", "CRITICAL")}]
    if not high_inv:
        return None
    sample_alerts = []
    for inv in investigations[:50]:
        if len(sample_alerts) >= 3:
            break
        just = parse_justification(inv.get("notes", ""))
        sev = {a["alert_id"]: a.get("severity", "MEDIUM") for a in alerts}.get(inv.get("alert_id", ""), "MEDIUM")
        if sev in ("HIGH", "CRITICAL") and just["depth_score"] <= 2:
            sample_alerts.append(inv.get("alert_id", ""))
    confidence = min(0.95, 0.5 + 0.1 * result.shallow_justification_count)
    return Finding(
        finding_id=f"{ctx.cse_id}:shallow_justification",
        cse_id=ctx.cse_id,
        signal_type="shallow_justification",
        signal_category="reasoning_quality",
        period="ALL",
        severity="HIGH" if result.shallow_justification_count > 5 else "MEDIUM",
        confidence=round(confidence, 2),
        evidence={
            "shallow_count": result.shallow_justification_count,
            "total_high_critical": len(high_inv),
            "mean_depth": result.mean_depth,
            "mean_coherence": result.mean_coherence,
            "sample_alert_ids": sample_alerts,
        },
        contributing_record_ids=sample_alerts,
        detection_logic=(
            f"{result.shallow_justification_count} HIGH/CRITICAL alerts were closed with "
            "shallow justification (depth score <= 2). Expected depth for HIGH/CRITICAL: "
            f"{SEVERITY_DEPTH_EXPECTED['HIGH']}+. Entity mean coherence: {result.mean_coherence}."
        ),
        caveats=["Short notes may be legitimate for well-understood alert types."],
        recommended_actions=[
            "Review sample alerts to confirm investigation quality",
            "Compare investigation depth to peer entities",
        ],
        data_quality_notes=["Requires investigation notes field in case data."],
    )


def _template_notes(ctx: SignalContext) -> Optional[Finding]:
    investigations = _get_investigations(ctx)
    if len(investigations) < 10:
        return None
    tmpl = detect_template_notes(investigations)
    if tmpl["template_ratio"] < 0.5:
        return None
    confidence = min(0.95, 0.5 + 0.2 * tmpl["template_ratio"])
    return Finding(
        finding_id=f"{ctx.cse_id}:template_notes",
        cse_id=ctx.cse_id,
        signal_type="template_notes",
        signal_category="reasoning_quality",
        period="ALL",
        severity="HIGH" if tmpl["template_ratio"] > 0.8 else "MEDIUM",
        confidence=round(confidence, 2),
        evidence={
            "template_ratio": tmpl["template_ratio"],
            "unique_notes": tmpl["unique_notes"],
            "total_notes": tmpl["total_notes"],
            "most_common_pattern": tmpl["most_common_pattern"],
        },
        contributing_record_ids=[],
        detection_logic=(
            f"{tmpl['template_ratio']:.0%} of investigation notes are near-duplicates "
            f"({tmpl['unique_notes']} unique out of {tmpl['total_notes']} total). "
            "Template-driven investigations suggest superficial review."
        ),
        caveats=["Some repetition is normal for known alert types with validated playbooks."],
        recommended_actions=[
            "Review the most common note pattern",
            "Compare note diversity to peer entities",
        ],
        data_quality_notes=["Requires investigation notes field in case data."],
    )


def _missing_escalation_rationale(ctx: SignalContext) -> Optional[Finding]:
    investigations = _get_investigations(ctx)
    escalations = _get_escalations(ctx)
    if not escalations or not investigations:
        return None
    result = analyze_reasoning_quality(ctx.cse_id, investigations, [], escalations)
    if result.missing_escalation_rationale_count == 0:
        return None
    confidence = min(0.9, 0.5 + 0.15 * result.missing_escalation_rationale_count)
    return Finding(
        finding_id=f"{ctx.cse_id}:missing_escalation_rationale",
        cse_id=ctx.cse_id,
        signal_type="missing_escalation_rationale",
        signal_category="reasoning_quality",
        period="ALL",
        severity="MEDIUM",
        confidence=round(confidence, 2),
        evidence={
            "missing_count": result.missing_escalation_rationale_count,
            "total_escalations": len(escalations),
        },
        contributing_record_ids=[],
        detection_logic=(
            f"{result.missing_escalation_rationale_count} of {len(escalations)} escalated cases "
            "have minimal investigation notes (<10 words). Escalated cases should have "
            "documented rationale."
        ),
        caveats=["Escalation rationale may be documented outside investigation notes."],
        recommended_actions=[
            "Review escalated cases with minimal notes",
            "Verify escalation procedures are followed",
        ],
        data_quality_notes=["Requires investigation notes and escalation records."],
    )


def _reasoning_inflation(ctx: SignalContext) -> Optional[Finding]:
    alerts = _get_alerts(ctx)
    investigations = _get_investigations(ctx)
    if not investigations or not alerts:
        return None
    alert_sev = {a["alert_id"]: a.get("severity", "MEDIUM") for a in alerts}
    inflated = 0
    for inv in investigations:
        just = parse_justification(inv.get("notes", ""))
        sev = alert_sev.get(inv.get("alert_id", ""), "MEDIUM")
        coh, _ = coherence_score(just, sev)
        if just["depth_score"] >= 4 and coh < 0.4:
            inflated += 1
    if inflated < 3:
        return None
    confidence = min(0.85, 0.4 + 0.1 * inflated)
    return Finding(
        finding_id=f"{ctx.cse_id}:reasoning_inflation",
        cse_id=ctx.cse_id,
        signal_type="reasoning_inflation",
        signal_category="reasoning_quality",
        period="ALL",
        severity="MEDIUM",
        confidence=round(confidence, 2),
        evidence={"inflation_count": inflated, "total_investigations": len(investigations)},
        contributing_record_ids=[],
        detection_logic=(
            f"{inflated} investigations claim technical depth but lack supporting evidence "
            "in their notes (high keyword count, low coherence). Possible reasoning inflation."
        ),
        caveats=["Keyword matching may misclassify technical shorthand as depth."],
        recommended_actions=[
            "Review cases with high keyword count but low coherence",
            "Verify claimed actions were actually performed",
        ],
        data_quality_notes=["Requires investigation notes field in case data."],
    )


SIGNALS: List[Tuple[str, Callable[[SignalContext], Optional[Finding]]]] = [
    ("shallow_justification", _shallow_justification),
    ("template_notes", _template_notes),
    ("missing_escalation_rationale", _missing_escalation_rationale),
    ("reasoning_inflation", _reasoning_inflation),
]
