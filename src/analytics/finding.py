"""Finding dataclass, threshold configuration, and shared scoring helpers.

Every signal returns an optional Finding. Findings are framed as *potential
supervisory concerns*, never compliance determinations — that framing is
baked into the standard caveat appended to every finding.

Thresholds live in ``data/config/thresholds.json`` (deep-merged over
DEFAULT_THRESHOLDS). No hardcoded regulatory values anywhere in the signal
code — everything tunable flows through this module.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_THRESHOLDS_PATH = Path("data/config/thresholds.json")

STANDARD_CAVEAT = (
    "Indicates a potential supervisory concern; not a determination of "
    "non-compliance."
)

# Sample-size reference points: below these, confidence ramps down linearly.
REFERENCE_N = {
    "alerts": 100,
    "investigations": 30,
    "escalations": 10,
}


@dataclass
class Finding:
    finding_id: str
    cse_id: str
    signal_type: str
    signal_category: str  # execution_gap, negative_space, behavioral_anomaly, peer_deviation
    period: str           # detection window, e.g. '2024-Q4' or 'ALL'
    severity: str         # HIGH, MEDIUM, LOW
    confidence: float     # 0.0–1.0
    evidence: Dict[str, Any]
    contributing_record_ids: List[str] = field(default_factory=list)
    detection_logic: str = ""
    caveats: List[str] = field(default_factory=list)
    recommended_actions: List[str] = field(default_factory=list)
    data_quality_notes: List[str] = field(default_factory=list)
    created_at: Optional[str] = None

    def __post_init__(self) -> None:
        if STANDARD_CAVEAT not in self.caveats:
            self.caveats.insert(0, STANDARD_CAVEAT)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "cse_id": self.cse_id,
            "signal_type": self.signal_type,
            "signal_category": self.signal_category,
            "period": self.period,
            "severity": self.severity,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "contributing_record_ids": self.contributing_record_ids,
            "detection_logic": self.detection_logic,
            "caveats": self.caveats,
            "recommended_actions": self.recommended_actions,
            "data_quality_notes": self.data_quality_notes,
            "created_at": self.created_at,
        }


def finding_id(cse_id: str, signal_type: str) -> str:
    """Deterministic ID — one finding per (CSE, signal); upsert-friendly."""
    return f"{cse_id}:{signal_type}"


# ---------------------------------------------------------------------------
# Scoring helpers shared by all signals
# ---------------------------------------------------------------------------


def sample_confidence(n: int, reference: int) -> float:
    """Sample-size adequacy 0..1: full credit at ``reference`` observations."""
    if reference <= 0:
        return 0.0
    return min(1.0, n / reference)


def margin_above(value: float, threshold: float, cap: float) -> float:
    """Excess past a 'higher is worse' threshold, saturating at ``cap``."""
    span = cap - threshold
    if span <= 0:
        return 1.0
    return float(min(1.0, max(0.0, (value - threshold) / span)))


def margin_below(value: float, threshold: float, floor: float = 0.0) -> float:
    """Deficit below a 'lower is worse' threshold, saturating at ``floor``."""
    span = threshold - floor
    if span <= 0:
        return 1.0
    return float(min(1.0, max(0.0, (threshold - value) / span)))


def severity_from(margin: float) -> str:
    if margin >= 0.6:
        return "HIGH"
    if margin >= 0.25:
        return "MEDIUM"
    return "LOW"


def combined_confidence(*components: float) -> float:
    """Mean of components, rounded for storage."""
    return round(sum(components) / len(components), 3)


# ---------------------------------------------------------------------------
# Threshold configuration
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "_global": {
        "quality_gate": 0.5,       # signals stay silent below this quality score
        "max_record_ids": 25,      # cap on contributing_record_ids per finding
    },
    "peer": {
        "min_group_size": 3,       # below this, peer deviation is meaningless
        "outlier_z": 2.5,          # |modified z| beyond this flags
    },
    "benchmarking": {
        "min_group_size": 3,       # group members (incl. self) needed to score
        "outlier_z": 2.5,          # plain z-score outlier threshold
    },
    "scoring": {
        "confidence_weight": 0.4,  # weight of mean finding confidence
        "severity_weight": 0.3,    # weight of mean severity points
        "breadth_weight": 0.3,     # weight of (count + diversity) blend
        "signal_count_target": 10, # findings at which count score saturates
        "max_diversity_categories": 4,
        "scale": 100,              # final priority scale (0-100)
    },
    "fusion": {
        "min_findings": 2,         # below this there is nothing to fuse
        "min_categories": 2,       # cross-category corroboration required
    },
    "feedback": {
        "min_feedback": 5,             # dispositions before a rate is advisory
        "low_worthwhile_rate": 0.30,   # below this, suggest tightening
        "high_worthwhile_rate": 0.85,  # above this, signal is earning its keep
    },
    "superficial_closure": {
        "max_closure_hours": 2.0,      # median alert->closure at/below this = fast
        "shallow_depth_max": 2.0,      # median evidence entries at/below this = shallow
        "min_alerts": 30,
        "velocity_bound": 0.25,        # hours; margin saturates here
        "depth_bound": 0.5,
    },
    "escalation_without_action": {
        "min_followthrough": 0.5,      # follow-through below this flags
        "min_escalations": 5,
    },
    "quality_degradation": {
        "min_quarters": 3,
        "min_decline_frac": 0.30,      # first->last depth drop fraction
        "decline_bound": 0.70,
    },
    "kpi_divergence": {
        "min_quarters": 3,
        "min_depth_decline": 0.30,     # depth entries lost per quarter
        "depth_decline_bound": 1.20,   # slope magnitude that saturates margin
        "min_velocity_improvement": 0.25,  # h/quarter of faster closures
        "velocity_bound": 0.45,
    },
    "severity_mismatch": {
        "max_triage_only_rate": 0.70,  # closed high-sev w/o investigation
        "min_high_sev_closed": 10,
        "rate_bound": 1.0,
    },
    "template_investigation": {
        "max_unique_ratio": 0.20,      # unique notes / total below this flags
        "min_investigations": 20,
    },
    "alert_volume_gap": {
        "min_volume_ratio": 0.30,      # observed/expected below this flags
        "ratio_bound": 0.10,
        "min_assets": 10,
    },
    "missing_investigations": {
        "max_missing_rate": 0.50,      # high-sev alerts w/o investigation record
        "min_high_sev_alerts": 20,
        "rate_bound": 0.90,
    },
    "missing_alert_categories": {
        "presence_frac": 0.90,         # category reported by >= this share of peers
        "min_alerts": 50,
    },
    "telemetry_absence": {
        "min_silent_share": 0.80,      # share of a group's assets w/ zero alerts
        "min_group_assets": 10,
        "share_bound": 1.0,
    },
    "escalation_absence": {
        "min_critical_alerts": 10,     # critical alerts w/ zero linked escalations
        "min_weekend_critical": 5,     # weekend variant
    },
    "evidence_deficit": {
        "min_alerts": 100,             # severity mix needs volume to be stable
        "min_expected": 20.0,          # dimensions with a smaller expectation
                                       # are skipped (band too wide to mean much)
        "band_z": 3.0,                 # σ widths for the uncertainty band
        "overdispersion": 0.001,       # variance inflation φ in the band
        "min_ratio_alerts": 0.75,      # observed/expected gates — each set
        "min_ratio_investigations": 0.90,   # ~2x below the measured clean
        "min_ratio_evidence_entries": 0.85, # minimum (clean portfolio sits
        "min_ratio_escalations": 0.80,      # at 0.90-1.01 across dimensions)
        "ratio_bound_alerts": 0.40,    # margin saturation floors
        "ratio_bound_investigations": 0.60,
        "ratio_bound_evidence_entries": 0.40,
        "ratio_bound_escalations": 0.50,
    },
    "temporal_drift": {
        "depth_drop_frac": 0.40,       # QoQ depth drop beyond this flags
        "velocity_jump_factor": 2.5,   # QoQ closure-velocity ratio beyond this flags
    },
    "changepoint_drift": {
        "min_points": 4,               # quarterly observations needed for a split
        "min_segment": 2,              # quarters required on EACH side of the split
        "min_drop": 0.90,              # entries lost across the change (2x clean max)
        "drop_bound": 3.00,            # drop magnitude saturating margin
        "min_drop_frac": 0.20,         # relative decline across the change
        "frac_bound": 0.70,
        "min_explained_share": 0.60,   # two-level model must explain the window
    },
    "unusual_quiet_period": {
        "min_quiet_periods": 18,       # gaps > quiet_gap_hours within the window
        "quiet_gap_hours": 48,
        "max_gap_hours": 120,          # single gap beyond this flags outright
        "gap_median_multiple": 75,     # ...or max gap vs own median cadence
    },
    "bulk_closure_pattern": {
        "burst_factor": 4.0,           # peak-day closures / median day
        "min_peak_closures": 50,
        "min_days": 10,
    },
    "shift_variance": {
        "max_shift_ratio": 1.8,        # max/min mean depth across shifts
        "min_per_shift": 20,
        "shift_hours": {"day": (7, 15), "evening": (15, 23), "night": (23, 24)},
    },
    "recurring_incident": {
        "min_repeats": 8,              # same (asset, category) occurrences
        "min_unclosed_share": 0.50,
    },
}


def load_thresholds(path: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Defaults deep-merged with ``data/config/thresholds.json`` (if present)."""
    config = json.loads(json.dumps(DEFAULT_THRESHOLDS))  # deep copy
    path = Path(path) if path else DEFAULT_THRESHOLDS_PATH
    if path.exists():
        overrides = json.loads(path.read_text())
        for section, values in overrides.items():
            if isinstance(values, dict) and isinstance(config.get(section), dict):
                config[section].update(values)
            else:
                config[section] = values
    return config


def thr(config: Dict[str, Any], signal: str, key: str) -> Any:
    return config[signal][key]


def cap_ids(ids: List[str], config: Dict[str, Any]) -> List[str]:
    limit = config["_global"]["max_record_ids"]
    return sorted(ids)[:limit]
