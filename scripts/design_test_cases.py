#!/usr/bin/env python
"""Ground-truth oracle for SAT-SA validation (Phase 13).

One TEST_CASES entry per seeded weakness: the signals the engine MUST fire,
the minimum confidence each must carry, and the human-readable description.
``min_confidence`` reflects per-signal evidence strength by design —
negative-space (absence) signals cap out lower than record-backed
execution-gap signals — rather than one blanket cutoff.

Usage:
    python scripts/design_test_cases.py     # print the oracle table
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analytics.sample_data import SEEDED_SCENARIOS, SCENARIO_SIGNALS  # noqa: E402

TEST_CASES = [
    {
        "cse_id": "CSE-042",
        "scenario": SEEDED_SCENARIOS["CSE-042"],
        "expected_signals": sorted(SCENARIO_SIGNALS["degrading_depth"]),
        "min_confidence": 0.90,
        "description": "Investigation depth declines quarter over quarter "
                       "(quality degradation with temporal drift)",
    },
    {
        "cse_id": "CSE-017",
        "scenario": SEEDED_SCENARIOS["CSE-017"],
        "expected_signals": sorted(SCENARIO_SIGNALS["superficial_closures"]),
        "min_confidence": 0.70,
        "description": "Alerts closed fast and shallow — superficial "
                       "closure pattern",
    },
    {
        "cse_id": "CSE-089",
        "scenario": SEEDED_SCENARIOS["CSE-089"],
        "expected_signals": sorted(SCENARIO_SIGNALS["missing_telemetry"]),
        "min_confidence": 0.50,
        "description": "Entire alert category absent while peers report it "
                       "(telemetry gap)",
    },
    {
        "cse_id": "CSE-031",
        "scenario": SEEDED_SCENARIOS["CSE-031"],
        "expected_signals": sorted(SCENARIO_SIGNALS["missing_investigations"]),
        "min_confidence": 0.90,
        "description": "Most critical alerts never receive an investigation",
    },
    {
        "cse_id": "CSE-055",
        "scenario": SEEDED_SCENARIOS["CSE-055"],
        "expected_signals": sorted(SCENARIO_SIGNALS["fast_closure_outlier"]),
        "min_confidence": 0.95,
        "description": "Closure velocity far outside the peer group",
    },
    {
        "cse_id": "CSE-073",
        "scenario": SEEDED_SCENARIOS["CSE-073"],
        "expected_signals": sorted(SCENARIO_SIGNALS["weekend_escalation_gap"]),
        "min_confidence": 0.80,
        "description": "Weekend critical alerts but zero weekend "
                       "escalations",
    },
    {
        "cse_id": "CSE-019",
        "scenario": SEEDED_SCENARIOS["CSE-019"],
        "expected_signals": sorted(SCENARIO_SIGNALS["templated_investigations"]),
        "min_confidence": 0.90,
        "description": "Investigation notes drawn from boilerplate templates",
    },
    {
        "cse_id": "CSE-061",
        "scenario": SEEDED_SCENARIOS["CSE-061"],
        "expected_signals": sorted(SCENARIO_SIGNALS["combined_weak"]),
        "min_confidence": 0.95,
        "description": "Combined weak SOC: shallow depth far below peers",
    },
]


def main() -> int:
    print(f"{'CSE':<9} {'scenario':<24} {'expected signals':<34} "
          f"{'min conf':>8}")
    for tc in TEST_CASES:
        print(f"{tc['cse_id']:<9} {tc['scenario']:<24} "
              f"{', '.join(tc['expected_signals']):<34} "
              f"{tc['min_confidence']:>8.2f}")
    print(f"\n{len(TEST_CASES)} oracle cases; "
          f"{sum(len(t['expected_signals']) for t in TEST_CASES)} required "
          f"(cse, signal) detections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
