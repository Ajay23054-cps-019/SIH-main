"""Signal-fusion tests (post-MVP capability #2).

fuse_cases is a pure function over finding-like objects; storage round-trips
run against a temporary SQLite database.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.analytics.finding import load_thresholds
from src.analytics.fusion import (
    FRAMING_CAVEAT,
    INDEPENDENCE_CAVEAT,
    SupervisoryCase,
    clear_cases,
    fuse_cases,
    load_cases,
    noisy_or,
    store_cases,
)


def _f(cse_id="CSE-T01", signal_type="quality_degradation",
       category="execution_gap", severity="HIGH", confidence=0.9,
       finding_id=None):
    return SimpleNamespace(
        finding_id=finding_id or f"{cse_id}:{signal_type}",
        cse_id=cse_id, signal_type=signal_type,
        signal_category=category, severity=severity,
        confidence=confidence)


def _thr(**overrides):
    cfg = load_thresholds()
    cfg["fusion"].update(overrides)
    return cfg


# ---------------------------------------------------------------------------
# noisy-OR math
# ---------------------------------------------------------------------------


class TestNoisyOr:
    def test_two_half_confidences(self):
        assert noisy_or([0.5, 0.5]) == pytest.approx(0.75)

    def test_confident_member_saturates(self):
        assert noisy_or([1.0, 0.3]) == 1.0

    def test_empty_and_clamping(self):
        assert noisy_or([]) == 0.0
        assert noisy_or([-0.5, 1.7]) == 1.0   # clamped into [0, 1]

    def test_monotonic_in_members(self):
        base = noisy_or([0.4, 0.4])
        assert noisy_or([0.4, 0.4, 0.4]) > base


# ---------------------------------------------------------------------------
# Fusion gating and case construction
# ---------------------------------------------------------------------------


class TestFuseCases:
    def test_cross_category_findings_form_a_case(self):
        findings = [_f(signal_type="quality_degradation",
                       category="execution_gap"),
                    _f(signal_type="closure_velocity_outlier",
                       category="peer_deviation", confidence=1.0)]
        cases = fuse_cases(findings, load_thresholds())
        assert len(cases) == 1
        c = cases[0]
        assert c.case_id == "CASE-CSE-T01"
        assert c.severity == "HIGH"
        assert c.n_findings == 2
        assert sorted(c.categories) == ["execution_gap", "peer_deviation"]
        assert c.joint_confidence == 1.0   # noisy-OR saturates via conf-1.0 member

    def test_single_finding_never_fuses(self):
        assert fuse_cases([_f()], load_thresholds()) == []

    def test_same_category_findings_do_not_fuse(self):
        # two lenses of the same kind are repeats, not corroboration
        findings = [_f(signal_type="quality_degradation"),
                    _f(signal_type="temporal_drift")]
        assert fuse_cases(findings, load_thresholds()) == []

    def test_per_cse_grouping(self):
        findings = [_f(cse_id="CSE-A", category="execution_gap"),
                    _f(cse_id="CSE-B", category="peer_deviation")]
        assert fuse_cases(findings, load_thresholds()) == []

    def test_min_categories_override_raises_the_bar(self):
        findings = [_f(category="execution_gap"),
                    _f(signal_type="closure_velocity_outlier",
                       category="peer_deviation")]
        cfg = _thr(min_categories=3)
        assert fuse_cases(findings, cfg) == []

    def test_narrative_and_caveats(self):
        findings = [_f(signal_type="quality_degradation",
                       category="execution_gap"),
                    _f(signal_type="missing_alert_categories",
                       category="negative_space", severity="MEDIUM",
                       confidence=0.7)]
        c = fuse_cases(findings, load_thresholds())[0]
        assert "2 findings" in c.narrative
        assert "execution_gap" in c.narrative
        assert "quality_degradation" in c.narrative   # strongest member named
        assert INDEPENDENCE_CAVEAT in c.caveats
        assert FRAMING_CAVEAT in c.caveats

    def test_members_sorted_strongest_first(self):
        findings = [_f(signal_type="weak_one", severity="LOW",
                       confidence=0.4),
                    _f(signal_type="strong_one", severity="HIGH",
                       confidence=0.95, category="peer_deviation")]
        c = fuse_cases(findings, load_thresholds())[0]
        assert c.finding_ids[0].endswith(":strong_one")

    def test_deterministic_and_empty_safe(self):
        assert fuse_cases([], load_thresholds()) == []
        mk = lambda: fuse_cases(  # noqa: E731
            [_f(category="execution_gap"),
             _f(signal_type="x", category="negative_space")],
            load_thresholds())
        assert mk()[0].to_dict() == mk()[0].to_dict()

    def test_to_dict_shape(self):
        findings = [_f(category="execution_gap"),
                    _f(signal_type="x", category="negative_space")]
        d = fuse_cases(findings, load_thresholds())[0].to_dict()
        assert set(d) == {"case_id", "cse_id", "finding_ids", "signal_types",
                          "categories", "n_findings", "joint_confidence",
                          "severity", "narrative", "caveats", "created_at"}
        assert isinstance(d["finding_ids"], list)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _two_findings():
    return [_f(signal_type="quality_degradation", category="execution_gap"),
            _f(signal_type="missing_alert_categories",
               category="negative_space", confidence=0.7)]


class TestCaseStorage:
    def test_store_load_roundtrip(self, tmp_path):
        db = tmp_path / "t.db"
        cases = fuse_cases(_two_findings(), load_thresholds())
        assert store_cases(cases, db) == 1
        rows = load_cases(db)
        assert len(rows) == 1
        r = rows[0]
        assert r["case_id"] == "CASE-CSE-T01"
        assert r["n_findings"] == 2
        assert r["categories"] == ["execution_gap", "negative_space"]
        assert r["created_at"]

    def test_cse_filter_and_missing_table(self, tmp_path):
        db = tmp_path / "t.db"
        assert load_cases(db) == []            # table not created yet
        store_cases(fuse_cases(_two_findings(), load_thresholds()), db)
        assert load_cases(db, cse_id="CSE-OTHER") == []
        assert len(load_cases(db, cse_id="CSE-T01")) == 1

    def test_clear_and_replace(self, tmp_path):
        db = tmp_path / "t.db"
        store_cases(fuse_cases(_two_findings(), load_thresholds()), db)
        assert clear_cases(db) == 1
        assert load_cases(db) == []
        # re-run replaces rather than duplicates
        store_cases(fuse_cases(_two_findings(), load_thresholds()), db)
        store_cases(fuse_cases(_two_findings(), load_thresholds()), db)
        assert len(load_cases(db)) == 1
