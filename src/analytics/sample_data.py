"""Synthetic SOC dataset generator with seeded supervisory weaknesses.

Generates a portfolio of CSEs producing realistic alert / investigation /
escalation / case / asset records over four quarters of 2024, with eight
CSEs seeded with specific weaknesses (depth degradation, superficial
closures, missing telemetry, ...).

Weaknesses are injected through *scenario parameters* (distributions), never
by special-casing CSE IDs in analytics — detection logic must find them from
the data alone.

Reproducible: a given seed always produces byte-identical output.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUARTER_STARTS = (
    datetime(2024, 1, 1),
    datetime(2024, 4, 1),
    datetime(2024, 7, 1),
    datetime(2024, 10, 1),
)
N_QUARTERS = 4

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
CATEGORIES = ("malware", "authentication", "network", "endpoint", "database", "web")
ASSET_TYPES = ("endpoint", "server", "network_device", "database")

# Baseline distributions -----------------------------------------------------
SEVERITY_PROBS = np.array([0.40, 0.35, 0.18, 0.07])
CATEGORY_PROBS = {
    "malware": 0.22,
    "authentication": 0.24,
    "network": 0.20,
    "endpoint": 0.18,
    "database": 0.10,
    "web": 0.06,
}
ASSET_TYPE_PROBS = {"endpoint": 0.55, "server": 0.20, "network_device": 0.15, "database": 0.10}

# Per-severity operational baselines (the "healthy SOC" behaviour model)
INVESTIGATION_RATE = {"LOW": 0.90, "MEDIUM": 0.88, "HIGH": 0.90, "CRITICAL": 0.95}
EVIDENCE_MEAN = {"LOW": 3.0, "MEDIUM": 5.0, "HIGH": 7.0, "CRITICAL": 9.0}
DURATION_MEDIAN_H = {"LOW": 1.0, "MEDIUM": 3.0, "HIGH": 8.0, "CRITICAL": 16.0}
ESCALATION_PROB = {"LOW": 0.02, "MEDIUM": 0.06, "HIGH": 0.25, "CRITICAL": 0.55}

FOLLOWUP_PROB = 0.90
TRIAGE_ONLY_MEDIAN_MIN = {"LOW": 10.0, "MEDIUM": 15.0, "HIGH": 30.0, "CRITICAL": 40.0}

# Volume by size band (alerts per quarter). Weighted across the size mix
# this yields ~470 alerts/CSE/quarter ≈ ~95K alerts portfolio-wide.
ALERTS_PER_QUARTER = {"Small": 250, "Medium": 450, "Large": 650}
ASSETS_BY_SIZE = {"Small": (150, 250), "Medium": (250, 400), "Large": (400, 550)}

# Sector / size composition (SIH26157 demo dataset spec)
SECTOR_TARGETS = (("Telecom", 20), ("Financial Services", 15), ("Power & Energy", 15))
SIZE_TARGETS = (("Small", 10), ("Medium", 25), ("Large", 15))

# The eight documented seeded weaknesses -> scenario name.
SEEDED_SCENARIOS = {
    "CSE-042": "degrading_depth",
    "CSE-017": "superficial_closures",
    "CSE-089": "missing_telemetry",
    "CSE-031": "missing_investigations",
    "CSE-055": "fast_closure_outlier",
    "CSE-073": "weekend_escalation_gap",
    "CSE-019": "templated_investigations",
    "CSE-061": "combined_weak",
}

# Fixed ID pool so the documented IDs (incl. CSE-089) exist within 50 CSEs.
_CSE_ID_POOL_HEAD = tuple(f"CSE-{i:03d}" for i in range(1, 43))
_CSE_ID_POOL_TAIL = tuple(
    f"CSE-{i:03d}" for i in (55, 61, 73, 89, 91, 94, 97, 99)
)

# Scenario -> signal types the engine must fire for the pipeline acceptance
# check ("all eight seeded weaknesses detected"). Kept next to SEEDED_SCENARIOS
# so scripts/run_pipeline.py and tests share one source of truth.
SCENARIO_SIGNALS = {
    "degrading_depth": {"quality_degradation", "temporal_drift"},
    "superficial_closures": {"superficial_closure"},
    "missing_telemetry": {"missing_alert_categories"},
    "missing_investigations": {"missing_investigations"},
    "fast_closure_outlier": {"closure_velocity_outlier"},
    "weekend_escalation_gap": {"escalation_absence"},
    "templated_investigations": {"template_investigation"},
    "combined_weak": {"investigation_depth_outlier"},
}


def expected_seed_signals() -> Dict[str, set]:
    """cse_id -> set of signal types that must fire for that seeded CSE."""
    return {cid: set(SCENARIO_SIGNALS[name])
            for cid, name in SEEDED_SCENARIOS.items()}

TEXT_BANKS = {
    "findings": [
        "no malicious activity identified after log correlation",
        "false positive confirmed against baseline behaviour",
        "IOC matched known-benign internal tooling",
        "host isolated and re-imaged as precaution",
        "signature tuned to reduce recurrence",
        "credentials rotated; no lateral movement observed",
    ],
    "sources": ["firewall", "EDR console", "auth logs", "proxy", "DNS", "SIEM"],
    "recipients": ["SOC Lead", "Incident Manager", "CISO Office", "Sector CERT Liaison"],
    "resolutions": [
        "remediated and closed",
        "monitoring continued for 30 days then closed",
        "risk accepted with compensating controls",
        "resolved via configuration change",
    ],
    "escalation_rationales": [
        "severity and asset criticality require management visibility",
        "potential cross-entity campaign indicator",
        "repeated occurrences suggest systemic issue",
        "regulatory notification threshold may apply",
    ],
}

TEMPLATED_NOTES = (
    "Investigated the alert. Checked the logs. Nothing suspicious found. Closed.",
    "Reviewed available telemetry. No action required at this time.",
    "Alert assessed as benign. No further investigation needed.",
    "Checked with relevant team. Confirmed expected behaviour.",
    "Analyzed event data. Determined to be non-issue. Closed as benign.",
)


# ---------------------------------------------------------------------------
# Scenario parameterisation
# ---------------------------------------------------------------------------


@dataclass
class ScenarioParams:
    """Knobs that shape one CSE's behaviour profile.

    All multipliers are applied to the healthy-SOC baselines above. Quarterly
    tuples are indexed Q1..Q4 so degradation can be expressed per quarter.
    """

    name: str = "baseline"
    volume_scale: float = 1.0
    # Depth (evidence entries) and investigation-duration factors per quarter.
    depth_factor_by_quarter: Tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    duration_factor_by_quarter: Tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    # Global closure-speed multiplier (alert + investigation durations).
    closure_speed_factor: float = 1.0
    # Optional severity-specific override: {"HIGH": 0.05, ...}
    investigation_rate_override: Optional[Dict[str, float]] = None
    critical_escalation_prob: Optional[float] = None
    followup_prob: Optional[float] = None
    zero_endpoint_alerts: bool = False
    weekend_escalations_allowed: bool = True
    templated_notes: bool = False


SCENARIOS: Dict[str, ScenarioParams] = {
    "baseline": ScenarioParams(),
    # CSE-042: 70% decline in investigation depth across 4 quarters.
    "degrading_depth": ScenarioParams(
        name="degrading_depth",
        depth_factor_by_quarter=(1.0, 0.95, 0.45, 0.29),
        duration_factor_by_quarter=(1.0, 0.92, 0.50, 0.35),
    ),
    # CSE-017: shallow fast closures; critical alerts never escalated.
    "superficial_closures": ScenarioParams(
        name="superficial_closures",
        depth_factor_by_quarter=(0.3, 0.3, 0.3, 0.3),
        closure_speed_factor=0.25,
        critical_escalation_prob=0.0,
    ),
    # CSE-089: zero endpoint-category alerts despite endpoint-heavy inventory.
    "missing_telemetry": ScenarioParams(name="missing_telemetry", zero_endpoint_alerts=True),
    # CSE-031: high/critical alerts almost never investigated.
    "missing_investigations": ScenarioParams(
        name="missing_investigations",
        investigation_rate_override={"LOW": 0.90, "MEDIUM": 0.85, "HIGH": 0.05, "CRITICAL": 0.05},
    ),
    # CSE-055: closure velocity ~3σ faster than peers.
    "fast_closure_outlier": ScenarioParams(name="fast_closure_outlier", closure_speed_factor=0.10),
    # CSE-073: escalations never recorded on weekends.
    "weekend_escalation_gap": ScenarioParams(
        name="weekend_escalation_gap", weekend_escalations_allowed=False
    ),
    # CSE-019: near-duplicate templated investigation notes.
    "templated_investigations": ScenarioParams(name="templated_investigations", templated_notes=True),
    # CSE-061: shallow + fast + weak escalation follow-through combined.
    "combined_weak": ScenarioParams(
        name="combined_weak",
        depth_factor_by_quarter=(0.4, 0.4, 0.4, 0.4),
        closure_speed_factor=0.30,
        critical_escalation_prob=0.05,
        followup_prob=0.40,
    ),
}


@dataclass
class EntitySpec:
    cse_id: str
    sector: str
    size_band: str
    scenario: ScenarioParams


# Joint sector x size quotas — identical marginals to SECTOR_TARGETS and
# SIZE_TARGETS, but every realised cell holds >= 3 members so each cell is a
# usable peer group for benchmarking (min peer group size: 3).
COMBO_TARGETS = {
    "Telecom": {"Small": 4, "Medium": 10, "Large": 6},
    "Financial Services": {"Small": 3, "Medium": 8, "Large": 4},
    "Power & Energy": {"Small": 3, "Medium": 7, "Large": 5},
}
assert {s: sum(bands.values()) for s, bands in COMBO_TARGETS.items()} \
    == dict(SECTOR_TARGETS), "sector marginals must match SECTOR_TARGETS"
assert {b: sum(bands[b] for bands in COMBO_TARGETS.values())
        for b, _ in SIZE_TARGETS} == dict(SIZE_TARGETS), \
    "size marginals must match SIZE_TARGETS"


def _assign_entities(rng: np.random.Generator) -> List[EntitySpec]:
    """Build 50 EntitySpecs honouring sector/size quotas and pinned scenarios."""
    ids = list(_CSE_ID_POOL_HEAD) + list(_CSE_ID_POOL_TAIL)
    assert len(set(ids)) == 50, "CSE ID pool must contain 50 unique IDs"

    pinned_sector = {
        "CSE-042": "Telecom",
        "CSE-089": "Power & Energy",
        "CSE-017": "Financial Services",
        "CSE-055": "Financial Services",
        "CSE-061": "Financial Services",
        "CSE-031": "Telecom",
        "CSE-073": "Power & Energy",
        "CSE-019": "Telecom",
    }
    pinned_size = {
        "CSE-042": "Large",
        "CSE-089": "Large",
        "CSE-055": "Large",
        "CSE-017": "Medium",
        "CSE-061": "Medium",
        "CSE-031": "Medium",
        "CSE-073": "Medium",
        "CSE-019": "Small",
    }
    assert all(pinned_sector[cid] in COMBO_TARGETS
               and pinned_size[cid] in COMBO_TARGETS[pinned_sector[cid]]
               for cid in pinned_sector), "pinned pair must fit quota table"

    slots = [(sector, band)
             for sector, bands in COMBO_TARGETS.items()
             for band, count in bands.items()
             for _ in range(count)]
    assert len(slots) == len(ids)

    assigned: Dict[str, tuple] = {}
    for cid in ids:
        if cid in pinned_sector:
            pair = (pinned_sector[cid], pinned_size[cid])
            slots.remove(pair)          # consume one slot of that exact pair
            assigned[cid] = pair

    unpinned = [cid for cid in ids if cid not in assigned]
    rng.shuffle(unpinned)
    rng.shuffle(slots)
    for cid, slot in zip(unpinned, slots):
        assigned[cid] = slot

    specs: List[EntitySpec] = []
    for cid in ids:
        sector, band = assigned[cid]
        scenario_name = SEEDED_SCENARIOS.get(cid, "baseline")
        specs.append(EntitySpec(cid, sector, band, SCENARIOS[scenario_name]))
    return specs


# ---------------------------------------------------------------------------
# Sampling helpers
# ---------------------------------------------------------------------------


def _weighted_choice(rng: np.random.Generator, options, probs, size: int) -> np.ndarray:
    return rng.choice(np.asarray(options), size=size, p=np.asarray(probs, dtype=float))


def _sample_hours_of_day(rng: np.random.Generator, n: int) -> np.ndarray:
    """Business-hours-weighted hour-of-day distribution."""
    weights = np.array(
        [2, 1, 1, 1, 1, 3, 6, 10, 16, 20, 22, 24, 24, 22, 20, 18, 14, 12, 10, 8, 6, 4, 3, 2],
        dtype=float,
    )
    weights /= weights.sum()
    return rng.choice(np.arange(24), size=n, p=weights)


def _sample_alert_timestamps(
    rng: np.random.Generator, q_start: datetime, n_days: int, n: int
) -> np.ndarray:
    """Weekday-weighted day offsets + business-hours-weighted times."""
    days = np.arange(n_days)
    weekday = np.array([(q_start + timedelta(days=int(d))).weekday() for d in days])
    day_w = np.where(weekday >= 5, 0.35, 1.0)  # quieter weekends
    day_w /= day_w.sum()
    offsets = rng.choice(days, size=n, p=day_w)
    hours = _sample_hours_of_day(rng, n)
    minutes = rng.integers(0, 60, size=n)
    seconds = rng.integers(0, 60, size=n)

    base_ts = pd.Timestamp(q_start) + pd.to_timedelta(offsets, unit="D")
    return (
        base_ts
        + pd.to_timedelta(hours, unit="h")
        + pd.to_timedelta(minutes, unit="m")
        + pd.to_timedelta(seconds, unit="s")
    )


def _lognormal_duration_hours(rng: np.random.Generator, medians_h: np.ndarray) -> np.ndarray:
    sigma = 0.60
    mu = np.log(medians_h)
    return rng.lognormal(mean=mu, sigma=sigma)


def _contextual_note(alert_id, category, asset_id, source, finding) -> str:
    return (
        f"[{alert_id}] {category} alert on {asset_id}: "
        f"reviewed {source} and correlated events; {finding}."
    )


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------


def generate_cse(spec: EntitySpec, master_rng: np.random.Generator) -> Dict[str, List[dict]]:
    """Generate all records for one CSE across four quarters."""
    rng = np.random.default_rng(master_rng.integers(0, 2**63 - 1))
    sc = spec.scenario
    cse_id = spec.cse_id

    # --- Assets ------------------------------------------------------------
    lo, hi = ASSETS_BY_SIZE[spec.size_band]
    n_assets = int(rng.integers(lo, hi + 1))
    asset_types = _weighted_choice(
        rng, ASSET_TYPES, [ASSET_TYPE_PROBS[t] for t in ASSET_TYPES], n_assets
    )
    crit_prob_by_type = {"endpoint": (0.10, 0.28), "server": (0.25, 0.38),
                         "network_device": (0.18, 0.34), "database": (0.22, 0.36)}
    assets: List[dict] = []
    asset_ids: List[str] = []
    endpoint_asset_ids: List[str] = []
    for i, atype in enumerate(asset_types):
        aid = f"{cse_id}-AS-{i:05d}"
        asset_ids.append(aid)
        if atype == "endpoint":
            endpoint_asset_ids.append(aid)
        p_crit, p_high = crit_prob_by_type[atype]
        r = rng.random()
        criticality = "CRITICAL" if r < p_crit else "HIGH" if r < p_crit + p_high else \
            "MEDIUM" if r < p_crit + p_high + 0.32 else "LOW"
        env_roll = rng.random()
        environment = "production" if env_roll < 0.72 else "staging" if env_roll < 0.92 else "development"
        mon_roll = rng.random()
        monitoring = "monitored" if mon_roll < 0.90 else "partially_monitored" if mon_roll < 0.97 else "unmonitored"
        assets.append({
            "asset_id": aid, "cse_id": cse_id, "asset_type": atype,
            "criticality": criticality, "environment": environment,
            "monitoring_status": monitoring,
        })

    # --- Alerts / investigations / escalations ------------------------------
    base_volume = ALERTS_PER_QUARTER[spec.size_band]
    n_analysts = {"Small": 4, "Medium": 8, "Large": 14}[spec.size_band]
    analyst_pool = [f"{cse_id}-AN-{i:02d}" for i in range(1, n_analysts + 1)]

    alerts: List[dict] = []
    investigations: List[dict] = []
    escalations: List[dict] = []

    inv_counter = esc_counter = 0
    cat_options = list(CATEGORIES)
    cat_probs = [CATEGORY_PROBS[c] for c in cat_options]

    quarter_bounds = list(QUARTER_STARTS) + [datetime(2025, 1, 1)]
    for qi, q_start in enumerate(QUARTER_STARTS):
        n_days = (quarter_bounds[qi + 1] - q_start).days
        n_alerts = max(1, int(rng.poisson(base_volume * sc.volume_scale)))
        ts = _sample_alert_timestamps(rng, q_start, n_days, n_alerts)

        sev_idx = _weighted_choice(rng, np.arange(4), SEVERITY_PROBS, n_alerts)
        categories = _weighted_choice(rng, cat_options, cat_probs, n_alerts)
        asset_idx = rng.integers(0, n_assets, size=n_alerts)
        asset_sel = [asset_ids[i] for i in asset_idx]

        # Criticality-aware severity boost
        sel_critical_assets = np.array(
            [assets[i]["criticality"] == "CRITICAL" for i in asset_idx], dtype=bool
        )
        boost = sel_critical_assets & (rng.random(n_alerts) < 0.25)
        sev_idx = np.minimum(sev_idx + boost.astype(int), 3)
        severities = [SEVERITIES[i] for i in sev_idx]

        if sc.zero_endpoint_alerts:
            categories = np.where(categories == "endpoint", "network", categories)

        depth_f = sc.depth_factor_by_quarter[qi]
        dur_f = sc.duration_factor_by_quarter[qi] * sc.closure_speed_factor
        triage_f = sc.closure_speed_factor

        for j in range(n_alerts):
            sev = severities[j]
            cat = str(categories[j])
            aid = f"{cse_id}-AL-{qi}-{j:05d}"
            a_ts = pd.Timestamp(ts[j]).to_pydatetime()

            inv_rate = INVESTIGATION_RATE[sev]
            if sc.investigation_rate_override:
                inv_rate = sc.investigation_rate_override.get(sev, inv_rate)
            investigated = rng.random() < inv_rate

            escalated = False
            if investigated:
                inv_counter += 1
                inv_id = f"{cse_id}-INV-{inv_counter:06d}"
                open_off = timedelta(minutes=float(rng.uniform(5, 60)))
                median_h = DURATION_MEDIAN_H[sev] * dur_f
                dur_h = float(_lognormal_duration_hours(rng, np.array([median_h]))[0])
                close_ts = a_ts + open_off + timedelta(hours=dur_h)
                lam = EVIDENCE_MEAN[sev] * depth_f
                evidence = int(rng.poisson(lam))

                investigations.append({
                    "investigation_id": inv_id,
                    "alert_id": aid,
                    "cse_id": cse_id,
                    "timestamp_open": a_ts + open_off,
                    "timestamp_close": close_ts,
                    "evidence_entries": evidence,
                    "assigned_to": analyst_pool[int(rng.integers(0, n_analysts))],
                    "notes": (
                        TEMPLATED_NOTES[inv_counter % len(TEMPLATED_NOTES)]
                        if sc.templated_notes
                        else _contextual_note(
                            aid, cat, asset_sel[j],
                            TEXT_BANKS["sources"][int(rng.integers(0, len(TEXT_BANKS["sources"])))],
                            TEXT_BANKS["findings"][int(rng.integers(0, len(TEXT_BANKS["findings"])))],
                        )
                    ),
                    "depth_score": None,
                })

                esc_p = ESCALATION_PROB[sev]
                if sev == "CRITICAL" and sc.critical_escalation_prob is not None:
                    esc_p = sc.critical_escalation_prob
                if rng.random() < esc_p:
                    escalated = True
                    esc_counter += 1
                    esc_ts = close_ts + timedelta(minutes=float(rng.uniform(10, 120)))
                    if not sc.weekend_escalations_allowed:
                        while esc_ts.weekday() >= 5:  # Sat/Sun -> next Monday 09:00
                            esc_ts = (esc_ts + timedelta(days=1)).replace(hour=9, minute=0, second=0)
                    has_followup = bool(
                        rng.random() < (FOLLOWUP_PROB if sc.followup_prob is None else sc.followup_prob)
                    )
                    decision = "escalated_with_action" if has_followup else "escalated"
                    escalations.append({
                        "escalation_id": f"{cse_id}-ESC-{esc_counter:06d}",
                        "investigation_id": inv_id,
                        "cse_id": cse_id,
                        "timestamp": esc_ts,
                        "decision": decision,
                        "has_followup": has_followup,
                        "recipient": TEXT_BANKS["recipients"][
                            int(rng.integers(0, len(TEXT_BANKS["recipients"])))
                        ],
                        "rationale": TEXT_BANKS["escalation_rationales"][
                            int(rng.integers(0, len(TEXT_BANKS["escalation_rationales"])))
                        ],
                    })

                # Most investigated alerts eventually close at investigation close.
                if escalated or rng.random() < 0.94:
                    status = "escalated" if escalated else "closed"
                    closure_ts = investigations[-1]["timestamp_close"]
                else:
                    status = "investigating"
                    closure_ts = None
            else:
                # Uninvestigated: either still open or closed via triage only.
                if rng.random() < 0.65:
                    status = "closed"
                    triage_med_min = TRIAGE_ONLY_MEDIAN_MIN[sev] * triage_f
                    triage_min = float(rng.lognormal(np.log(triage_med_min), 0.5))
                    closure_ts = a_ts + timedelta(minutes=triage_min)
                else:
                    status = "open"
                    closure_ts = None

            alert_row = {
                "alert_id": aid,
                "cse_id": cse_id,
                "timestamp": a_ts,
                "severity": sev,
                "category": cat,
                "asset_id": asset_sel[j],
                "status": status,
                "closure_timestamp": closure_ts,
                "description": f"{cat} detection on {asset_sel[j]} ({sev.lower()} severity)",
            }
            alerts.append(alert_row)

    # --- Cases ----------------------------------------------------------------
    cases = build_cases(rng, cse_id, alerts)

    claimed = {
        # CSE-089 claims endpoint monitoring while producing zero endpoint
        # alerts — the claim-vs-observation gap is what negative-space
        # detection keys on (asset inventory corroborates the claim).
        "endpoint_monitoring": True,
        "endpoint_count_claimed": len(endpoint_asset_ids),
        "siem_correlation": True,
        "soc_coverage": "24x7" if spec.size_band != "Small" else "business-hours",
        "staffing_level": {"Small": 4, "Medium": 8, "Large": 14}[spec.size_band],
    }

    metadata = [{
        "cse_id": cse_id,
        "name": f"{spec.sector.split()[0]} {spec.size_band} Operator {cse_id[-3:]}",
        "sector": spec.sector,
        "size_band": spec.size_band,
        "claimed_capabilities": json.dumps(claimed),
        "submitted_at": datetime(2025, 1, 15),
    }]

    return {
        "cse_metadata": metadata,
        "alerts": alerts,
        "investigations": investigations,
        "escalations": escalations,
        "cases": cases,
        "assets": assets,
    }


def build_cases(rng: np.random.Generator, cse_id: str, alerts: List[dict]) -> List[dict]:
    """Create incident cases linked to notable alerts."""
    candidates = [a for a in alerts if a["status"] != "open"]
    cases: List[dict] = []
    n = 0
    for a in candidates:
        p = {"CRITICAL": 1.0, "HIGH": 1.0, "MEDIUM": 0.40, "LOW": 0.08}[a["severity"]]
        if rng.random() >= p:
            continue
        n += 1
        related = [a["alert_id"]]
        # Occasionally group nearby alerts into one case.
        if a["severity"] in ("HIGH", "CRITICAL") and rng.random() < 0.30:
            pool = [x["alert_id"] for x in candidates
                    if x["cse_id"] == cse_id and x["alert_id"] != a["alert_id"]]
            extra = rng.choice(pool, size=min(2, len(pool)), replace=False) if pool else []
            related.extend(str(e) for e in extra)
        closure_base = a["closure_timestamp"] or a["timestamp"]
        cases.append({
            "case_id": f"{cse_id}-CK-{n:06d}",
            "related_alerts": json.dumps(related),
            "cse_id": cse_id,
            "case_type": "incident",
            "severity": a["severity"],
            "closure_time": closure_base + timedelta(hours=float(rng.uniform(1, 48))),
            "resolution": TEXT_BANKS["resolutions"][int(rng.integers(0, len(TEXT_BANKS["resolutions"])))],
        })
    return cases


def generate_dataset(
    seed: int = 42, n_cses: Optional[int] = None
) -> Dict[str, pd.DataFrame]:
    """Generate the full demo portfolio as DataFrames keyed by entity type.

    Args:
        seed: Master seed for reproducibility.
        n_cses: Truncate the portfolio for smoke tests (first N specs).
    """
    master = np.random.default_rng(seed)
    specs = _assign_entities(master)
    if n_cses is not None:
        specs = specs[:n_cses]

    buckets: Dict[str, List[dict]] = {
        "cse_metadata": [], "alerts": [], "investigations": [],
        "escalations": [], "cases": [], "assets": [],
    }
    for spec in specs:
        part = generate_cse(spec, master)
        for key, rows in part.items():
            buckets[key].extend(rows)

    return {k: pd.DataFrame(v) for k, v in buckets.items()}


if __name__ == "__main__":
    frames = generate_dataset(seed=42)
    for name, df in frames.items():
        print(f"{name:>16}: {len(df):>7,} records")
