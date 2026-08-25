"""Expected-evidence model tests (post-MVP capability #4).

The model must be exact on hand-computable portfolios, strictly
leave-self-out (a thin CSE cannot drag its own baseline down), and
deterministic. Band math follows the negative-binomial approximation.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.analytics.expected_evidence import (
    DIMENSIONS,
    build_evidence_model,
    evidence_table_for,
)


def _alerts(rows):
    base = {"alert_id": None, "cse_id": None, "timestamp": None,
            "severity": "HIGH", "category": "malware", "asset_id": "A-1",
            "status": "closed", "closure_timestamp": None, "description": None}
    return pd.DataFrame([{**base, **r} for r in rows])


def _invs(rows):
    base = {"investigation_id": None, "alert_id": None, "cse_id": None,
            "timestamp_open": None, "timestamp_close": None,
            "evidence_entries": 5, "assigned_to": None, "notes": "n",
            "depth_score": None}
    return pd.DataFrame([{**base, **r} for r in rows])


def _escs(rows):
    base = {"escalation_id": None, "investigation_id": None, "cse_id": None,
            "timestamp": None, "decision": "escalated", "has_followup": True,
            "recipient": "CSO", "rationale": None}
    return pd.DataFrame([{**base, **r} for r in rows])


def _meta(rows):
    return pd.DataFrame(rows)


def _portfolio(target_entries=5, target_esc_share=0.0, target_id="CSE-T01"):
    """Reference CSE (healthy) + target CSE, hand-computable.

    Reference: 100 HIGH + 100 MEDIUM alerts, all investigated at 5 entries,
    50 escalations on the HIGH investigations (esc_rate HIGH = 0.5,
    MEDIUM = 0.0). Target: 60 HIGH + 60 MEDIUM alerts, all investigated.
    """
    ref_alerts = _alerts(
        [{"alert_id": f"R-AH{i}", "cse_id": "CSE-REF", "severity": "HIGH"}
         for i in range(100)]
        + [{"alert_id": f"R-AM{i}", "cse_id": "CSE-REF", "severity": "MEDIUM"}
           for i in range(100)])
    ref_invs = _invs(
        [{"investigation_id": f"R-IH{i}", "alert_id": f"R-AH{i}",
          "cse_id": "CSE-REF"} for i in range(100)]
        + [{"investigation_id": f"R-IM{i}", "alert_id": f"R-AM{i}",
            "cse_id": "CSE-REF"} for i in range(100)])
    ref_escs = _escs([{"escalation_id": f"R-E{i}",
                       "investigation_id": f"R-IH{i}",
                       "cse_id": "CSE-REF"} for i in range(50)])

    tgt_alerts = _alerts(
        [{"alert_id": f"T-AH{i}", "cse_id": target_id, "severity": "HIGH"}
         for i in range(60)]
        + [{"alert_id": f"T-AM{i}", "cse_id": target_id, "severity": "MEDIUM"}
           for i in range(60)])
    tgt_invs = _invs(
        [{"investigation_id": f"T-I{i}",
          "alert_id": f"T-AH{i}" if i < 60 else f"T-AM{i - 60}",
          "cse_id": target_id, "evidence_entries": target_entries}
         for i in range(120)])
    n_esc = int(60 * target_esc_share)
    tgt_escs = _escs([{"escalation_id": f"T-E{i}",
                       "investigation_id": f"T-I{i}", "cse_id": target_id}
                      for i in range(n_esc)])

    return {
        "cse_metadata": _meta([
            {"cse_id": "CSE-REF", "sector": "Telecom", "size_band": "Medium"},
            {"cse_id": target_id, "sector": "Telecom", "size_band": "Medium"},
        ]),
        "alerts": pd.concat([ref_alerts, tgt_alerts], ignore_index=True),
        "investigations": pd.concat([ref_invs, tgt_invs], ignore_index=True),
        "escalations": pd.concat([ref_escs, tgt_escs], ignore_index=True),
        "cases": pd.DataFrame(),
        "assets": pd.DataFrame(),
    }


class TestModelMath:
    def test_dimensions_present(self):
        table = evidence_table_for("CSE-T01", _portfolio())
        assert set(table) == set(DIMENSIONS)

    def test_leave_self_out_baseline_is_exact(self):
        # LOO investigation rate = reference rate (1.0); LOO depth = 5.0.
        table = evidence_table_for("CSE-T01", _portfolio())
        inv = table["investigations"]
        assert inv["observed"] == 120.0
        assert inv["expected"] == pytest.approx(120.0)   # 60*1.0 + 60*1.0
        assert inv["ratio"] == pytest.approx(1.0)
        entries = table["evidence_entries"]
        assert entries["expected"] == pytest.approx(600.0)  # 120 * 5.0

    def test_thin_target_does_not_drag_its_own_baseline(self):
        thin = evidence_table_for("CSE-T01", _portfolio(target_entries=1))
        healthy = evidence_table_for("CSE-T01",
                                     _portfolio(target_entries=5))
        # Identical composition -> identical expectation, regardless of how
        # thin the target's own submitted evidence is.
        assert thin["evidence_entries"]["expected"] == \
            healthy["evidence_entries"]["expected"]

    def test_escalation_expectation_severity_conditioned(self):
        table = evidence_table_for("CSE-T01", _portfolio(target_esc_share=0.5))
        esc = table["escalations"]
        # LOO esc rate: HIGH 50/100 = 0.5 (reference only), MEDIUM 0.0.
        assert esc["expected"] == pytest.approx(60 * 0.5)
        assert esc["observed"] == 30.0
        assert esc["ratio"] == pytest.approx(1.0)

    def test_alerts_dimension_size_band_loo_mean(self):
        frames = _portfolio()
        frames["alerts"] = pd.concat([
            frames["alerts"].iloc[0:0],   # keep schema
            _alerts([{"alert_id": f"R-A{i}", "cse_id": "CSE-REF"}
                     for i in range(200)]),
            _alerts([{"alert_id": f"T-A{i}", "cse_id": "CSE-T01"}
                     for i in range(100)]),
        ], ignore_index=True)
        table = evidence_table_for("CSE-T01", frames)
        # Only other Medium-band CSE is REF with 200 alerts.
        assert table["alerts"]["expected"] == pytest.approx(200.0)
        assert table["alerts"]["ratio"] == pytest.approx(0.5)

    def test_unknown_cse_and_empty_frames(self):
        assert evidence_table_for("CSE-GHOST", _portfolio()) is None
        assert build_evidence_model({}) == {}
        empty = {k: pd.DataFrame() for k in
                 ("cse_metadata", "alerts", "investigations",
                  "escalations", "cases", "assets")}
        assert build_evidence_model(empty) == {}


class TestBands:
    def test_band_brackets_expected(self):
        table = evidence_table_for("CSE-T01", _portfolio())
        for dim in DIMENSIONS:
            e = table[dim]
            if e["expected"] in (None, 0):
                continue
            assert 0 <= e["band_low"] <= e["expected"] <= e["band_high"]

    def test_band_widens_with_z_and_overdispersion(self):
        frames = _portfolio()
        tight = evidence_table_for("CSE-T01", frames, band_z=1.0)
        wide = evidence_table_for("CSE-T01", frames, band_z=3.0)
        assert wide["evidence_entries"]["band_low"] < \
            tight["evidence_entries"]["band_low"]
        assert wide["evidence_entries"]["band_high"] > \
            tight["evidence_entries"]["band_high"]
        inflated = evidence_table_for("CSE-T01", frames, overdispersion=0.01)
        assert inflated["evidence_entries"]["band_low"] < \
            tight["evidence_entries"]["band_low"]

    def test_band_floor_at_zero(self):
        frames = _portfolio()
        huge = evidence_table_for("CSE-T01", frames, band_z=50.0,
                                  overdispersion=1.0)
        assert huge["escalations"]["band_low"] == 0.0


class TestDeterminismAndShape:
    def test_build_model_covers_every_cse_with_alerts(self):
        model = build_evidence_model(_portfolio())
        assert set(model) == {"CSE-REF", "CSE-T01"}

    def test_repeated_builds_identical(self):
        frames = _portfolio()
        assert build_evidence_model(frames) == build_evidence_model(frames)

    def test_table_values_are_rounded_numbers(self):
        table = evidence_table_for("CSE-T01", _portfolio())
        for dim in DIMENSIONS:
            for key in ("observed", "expected", "ratio",
                        "band_low", "band_high"):
                v = table[dim][key]
                assert v is None or isinstance(v, (int, float))
