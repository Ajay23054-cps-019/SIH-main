"""Validation-harness tests (Phase 13).

compute_metrics is exercised as a pure function against synthetic
finding-like objects (fast); one module-scoped integration test runs the
real harness end-to-end on the demo dataset and enforces the spec targets.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

DEMO_DIR = Path("data/samples/demo_dataset")


def _f(cse_id, signal_type, severity="HIGH", confidence=0.9):
    return SimpleNamespace(cse_id=cse_id, signal_type=signal_type,
                           severity=severity, confidence=confidence)


def _oracle():
    from scripts.design_test_cases import TEST_CASES

    return [dict(tc) for tc in TEST_CASES]


# ---------------------------------------------------------------------------
# Pure metric computation
# ---------------------------------------------------------------------------


class TestComputeMetrics:
    def test_perfect_detection_scores_full_marks(self):
        from scripts.run_validation import compute_metrics

        oracle = _oracle()
        # confidence 1.0 clears every case's min_confidence (up to 0.95)
        findings = [_f(tc["cse_id"], sig, confidence=1.0)
                    for tc in oracle for sig in tc["expected_signals"]]
        priorities = {tc["cse_id"]: 80.0 for tc in oracle}
        priorities.update({f"CSE-{i:03d}": 0.0 for i in (1, 2, 3)})

        m = compute_metrics(oracle, findings, priorities, n_cses_total=11)
        assert m["coverage"] == 1.0
        assert m["precision_signal_level"] == 1.0
        assert m["false_positive_rate"] == 0.0
        assert m["examiner_alignment"] == pytest.approx(1.0)

    def test_missed_signal_lowers_coverage(self):
        from scripts.run_validation import compute_metrics

        oracle = _oracle()
        # fire everything (at full confidence) except CSE-042's temporal_drift
        findings = [_f(tc["cse_id"], sig, confidence=1.0)
                    for tc in oracle for sig in tc["expected_signals"]
                    if not (tc["cse_id"] == "CSE-042"
                            and sig == "temporal_drift")]
        priorities = {tc["cse_id"]: 50.0 for tc in oracle}

        m = compute_metrics(oracle, findings, priorities,
                            n_cses_total=len(oracle))
        assert m["coverage"] == pytest.approx(7 / 8)
        case = m["by_case"]["CSE-042"]
        assert not case["passed"]
        assert case["missed"][0]["signal"] == "temporal_drift"
        assert "not fired" in case["missed"][0]["reason"]

    def test_low_confidence_counts_as_miss_with_reason(self):
        from scripts.run_validation import compute_metrics

        tc = _oracle()[2]          # CSE-089, min_confidence 0.50
        findings = [_f("CSE-089", "missing_alert_categories",
                       severity="MEDIUM", confidence=0.49)]
        m = compute_metrics([tc], findings, {"CSE-089": 10.0},
                            n_cses_total=1)
        assert m["coverage"] == 0.0
        assert "confidence" in m["by_case"]["CSE-089"]["missed"][0]["reason"]

    def test_high_on_clean_cse_is_false_positive(self):
        from scripts.run_validation import compute_metrics

        oracle = _oracle()
        findings = ([_f(tc["cse_id"], sig, confidence=1.0)
                     for tc in oracle for sig in tc["expected_signals"]]
                    + [_f("CSE-100", "superficial_closure")])   # clean!
        priorities = {tc["cse_id"]: 80.0 for tc in oracle}
        priorities["CSE-100"] = 40.0

        m = compute_metrics(oracle, findings, priorities,
                            n_cses_total=len(oracle) + 1)
        assert m["high_findings_on_clean"] == 1
        assert m["false_positive_rate"] > 0
        assert m["precision_signal_level"] < 1.0
        assert m["clean_flagged_high"] == ["CSE-100"]

    def test_informational_findings_on_clean_are_listed_not_counted(self):
        from scripts.run_validation import compute_metrics

        oracle = _oracle()
        findings = ([_f(tc["cse_id"], sig, confidence=1.0)
                     for tc in oracle for sig in tc["expected_signals"]]
                    + [_f("CSE-200", "unusual_quiet_period",
                          severity="LOW", confidence=0.4)])
        m = compute_metrics(oracle, findings,
                            {tc["cse_id"]: 80.0 for tc in oracle},
                            n_cses_total=len(oracle) + 1)
        # LOW on clean is disclosed but does not count as an FP by definition
        assert m["high_findings_on_clean"] == 0
        assert len(m["informational_on_clean"]) == 1


class TestTargets:
    def test_targets_met_requires_all_four(self):
        from scripts.run_validation import targets_met

        base = {"coverage": 1.0, "precision_signal_level": 1.0,
                "false_positive_rate": 0.0, "examiner_alignment": 0.95}
        assert targets_met(base)
        for key, bad in (("coverage", 0.5), ("precision_signal_level", 0.3),
                         ("false_positive_rate", 0.9),
                         ("examiner_alignment", 0.1)):
            broken = dict(base, **{key: bad})
            assert not targets_met(broken), key


# ---------------------------------------------------------------------------
# Full harness integration (demo dataset, one pipeline pass)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def validation(tmp_path_factory):
    from scripts.run_validation import run_validation

    out_path = tmp_path_factory.mktemp("val") / "validation_report.md"
    return run_validation(DEMO_DIR, out_path)


class TestHarnessEndToEnd:
    def test_all_spec_targets_met(self, validation):
        assert validation["targets_met"]
        assert validation["coverage"] >= 0.70
        assert validation["precision_signal_level"] >= 0.60
        assert validation["false_positive_rate"] < 0.40
        assert validation["examiner_alignment"] >= 0.70

    def test_all_eight_oracle_cases_pass(self, validation):
        assert validation["cases_total"] == 8
        assert validation["cases_passed"] == 8

    def test_report_file_written_and_complete(self, validation):
        text = Path(validation["report_path"]).read_text()
        for heading in ("# SAT-SA Validation Report", "Headline metrics",
                        "Case-by-case results", "Limitations"):
            assert heading in text
        assert "not determinations of non-compliance" in text
