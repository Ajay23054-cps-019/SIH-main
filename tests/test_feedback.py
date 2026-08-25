"""Examiner feedback loop tests (post-MVP capability #7).

calibration_summary is a pure function; storage round-trips and the API
contract run against temporary SQLite databases.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.analytics.finding import STANDARD_CAVEAT, Finding, load_thresholds
from src.api.main import create_app
from src.feedback import (
    DISPOSITIONS,
    calibration_summary,
    load_feedback,
    store_feedback,
)
from src.analytics.signal_engine import store_findings


def _f(finding_id, signal_type, cse_id="CSE-T01"):
    return SimpleNamespace(finding_id=finding_id, signal_type=signal_type,
                           cse_id=cse_id)


def _thr(**overrides):
    cfg = load_thresholds()
    cfg["feedback"].update(overrides)
    return cfg


# ---------------------------------------------------------------------------
# calibration summary (pure)
# ---------------------------------------------------------------------------


class TestCalibrationSummary:
    def _feedback(self, *pairs):
        return [{"finding_id": fid, "disposition": d}
                for fid, d in pairs]

    def test_empty_inputs(self):
        assert calibration_summary([], [], load_thresholds()) == []

    def test_tallies_and_rate(self):
        findings = [_f(f"F-{i}", "quality_degradation") for i in range(4)]
        fb = self._feedback(("F-0", "worthwhile"), ("F-1", "worthwhile"),
                            ("F-2", "not_worthwhile"), ("F-3", "uncertain"))
        rows = calibration_summary(findings, fb, load_thresholds())
        assert len(rows) == 1
        r = rows[0]
        assert r["signal_type"] == "quality_degradation"
        assert r["n_feedback"] == 4
        assert r["worthwhile"] == 2 and r["not_worthwhile"] == 1
        assert r["uncertain"] == 1
        assert r["worthwhile_rate"] == pytest.approx(0.5)
        assert r["advisory"] is None          # below min_feedback

    def test_low_rate_advisory_after_min_feedback(self):
        findings = [_f(f"F-{i}", "template_investigation") for i in range(5)]
        fb = self._feedback(*[("F-0", "worthwhile")]
                            + [("F-%d" % i, "not_worthwhile")
                               for i in range(1, 5)])
        cfg = _thr(min_feedback=5, low_worthwhile_rate=0.30)
        r = calibration_summary(findings, fb, cfg)[0]
        assert r["worthwhile_rate"] == pytest.approx(0.2)
        assert r["advisory"] and "tightening" in r["advisory"]
        assert "not applied automatically" in r["advisory"]

    def test_high_rate_advisory(self):
        findings = [_f(f"F-{i}", "missing_investigations") for i in range(5)]
        fb = self._feedback(*[("F-%d" % i, "worthwhile") for i in range(5)])
        cfg = _thr(min_feedback=5, high_worthwhile_rate=0.85)
        r = calibration_summary(findings, fb, cfg)[0]
        assert r["advisory"] and "earning its keep" in r["advisory"]

    def test_feedback_for_unknown_findings_is_ignored(self):
        findings = [_f("F-0", "quality_degradation")]
        fb = self._feedback(("GHOST", "worthwhile"))
        assert calibration_summary(findings, fb, load_thresholds()) == []

    def test_grouping_by_signal_type(self):
        findings = [_f("A-0", "sig_x"), _f("A-1", "sig_x"),
                    _f("B-0", "sig_y")]
        fb = self._feedback(("A-0", "worthwhile"), ("A-1", "not_worthwhile"),
                            ("B-0", "worthwhile"))
        rows = calibration_summary(findings, fb, load_thresholds())
        assert {r["signal_type"] for r in rows} == {"sig_x", "sig_y"}


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------


class TestFeedbackStorage:
    def test_upsert_keeps_latest(self, tmp_path):
        db = tmp_path / "t.db"
        store_feedback(db, "F-1", "worthwhile", examiner="EX-1")
        store_feedback(db, "F-1", "not_worthwhile", note="re-reviewed")
        rows = load_feedback(db, finding_id="F-1")
        assert len(rows) == 1
        assert rows[0]["disposition"] == "not_worthwhile"
        assert rows[0]["note"] == "re-reviewed"
        assert rows[0]["updated_at"]

    def test_invalid_disposition_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            store_feedback(tmp_path / "t.db", "F-1", "excellent")

    def test_missing_table_reads_empty(self, tmp_path):
        assert load_feedback(tmp_path / "t.db") == []


# ---------------------------------------------------------------------------
# API contract
# ---------------------------------------------------------------------------


def _client_with_finding(tmp_path):
    db = tmp_path / "api.db"
    store_findings([Finding(
        finding_id="CSE-001:probe", cse_id="CSE-001",
        signal_type="probe", signal_category="execution_gap",
        period="ALL", severity="LOW", confidence=0.5, evidence={},
        detection_logic="fixture", caveats=[STANDARD_CAVEAT],
    )], db)
    return TestClient(create_app(db))


class TestFeedbackApi:
    def test_post_get_roundtrip(self, tmp_path):
        client = _client_with_finding(tmp_path)
        resp = client.post("/api/findings/CSE-001:probe/feedback",
                           json={"disposition": "worthwhile",
                                 "examiner": "EX-7"})
        assert resp.status_code == 200
        assert resp.json()["data"]["disposition"] == "worthwhile"
        got = client.get("/api/findings/CSE-001:probe/feedback")
        assert got.json()["data"]["disposition"] == "worthwhile"

    def test_unknown_finding_404(self, tmp_path):
        client = _client_with_finding(tmp_path)
        resp = client.post("/api/findings/GHOST:probe/feedback",
                           json={"disposition": "worthwhile"})
        assert resp.status_code == 404

    def test_bad_disposition_422(self, tmp_path):
        client = _client_with_finding(tmp_path)
        resp = client.post("/api/findings/CSE-001:probe/feedback",
                           json={"disposition": "excellent"})
        assert resp.status_code == 422

    def test_summary_endpoint(self, tmp_path):
        client = _client_with_finding(tmp_path)
        client.post("/api/findings/CSE-001:probe/feedback",
                    json={"disposition": "not_worthwhile"})
        rows = client.get("/api/feedback/summary").json()["data"]
        assert len(rows) == 1
        assert rows[0]["signal_type"] == "probe"
        assert rows[0]["not_worthwhile"] == 1
        assert "never automatically" in \
            client.get("/api/feedback/summary").json()["meta"]["note"]


def test_dispositions_constant():
    assert DISPOSITIONS == ("worthwhile", "not_worthwhile", "uncertain")
