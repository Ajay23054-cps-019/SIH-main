"""Tests for the evidence tracing layer.

A tiny deterministic portfolio is stored to SQLite (frames + profiles +
one engine-produced finding), then traced. The chain must expose signal,
metric, calculation and resolved records — and must *explicitly* flag any
referenced record that cannot be found.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.analytics.finding import Finding, STANDARD_CAVEAT
from src.analytics.signal_engine import (
    build_contexts,
    run_context,
    store_findings,
)
from src.evidence.findings import (
    finding_from_row,
    get_finding,
    load_findings_as_objects,
)
from src.evidence.tracer import EvidenceTracer

# ---------------------------------------------------------------------------
# Fixtures: a small DB with real frames + one finding with known record IDs
# ---------------------------------------------------------------------------

CSE = "CSE-T01"


def _alerts():
    base = {"cse_id": CSE, "severity": "HIGH", "category": "malware",
            "status": "closed"}
    rows = []
    for i in range(40):
        opened = pd.Timestamp("2024-01-15 08:00") + pd.Timedelta(minutes=i)
        closed = opened + pd.Timedelta(minutes=30)  # fast closures
        rows.append({**base, "alert_id": f"AL-{i:03d}", "timestamp": opened,
                     "asset_id": f"A-{i}", "closure_timestamp": closed})
    return pd.DataFrame(rows)


def _investigations():
    rows = []
    for i in range(40):
        rows.append({
            "investigation_id": f"INV-{i:03d}", "alert_id": f"AL-{i:03d}",
            "cse_id": CSE,
            "timestamp_open": pd.Timestamp("2024-01-15 09:00"),
            "timestamp_close": pd.Timestamp("2024-01-15 10:00"),
            "evidence_entries": 1, "notes": "Routine check, no issue",
        })
    return pd.DataFrame(rows)


def _assets():
    return pd.DataFrame([
        {"asset_id": f"A-{i}", "cse_id": CSE, "asset_type": "endpoint",
         "criticality": "HIGH", "environment": "production",
         "monitoring_status": "monitored"}
        for i in range(40)
    ])


def _escalations():
    rows = []
    for i in range(5):
        rows.append({
            "escalation_id": f"ES-{i}", "investigation_id": f"INV-{i:03d}",
            "cse_id": CSE,
            "timestamp": pd.Timestamp("2024-01-15 11:00"),
            "decision": "escalated",
            "has_followup": bool(i % 2),   # mix of followed-up / not
        })
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    """SQLite DB holding frames + profiles + superficial_closure finding."""
    from src.analytics.profiles import BehavioralProfile
    from src.analytics.signal_common import SignalContext
    from src.storage.db import save_frames

    tmp = tmp_path_factory.mktemp("evidence")
    db_path = tmp / "evidence.db"

    frames = {"alerts": _alerts(), "investigations": _investigations(),
              "assets": _assets(), "escalations": _escalations()}
    save_frames(frames, db_path)

    profiles = [
        BehavioralProfile(
            cse_id=CSE, period="2024-Q4",
            metrics={"closure_velocity_median_h": 0.5, "inv_depth_median": 1.0,
                     "inv_depth_mean": 1.0, "alert_volume_total": 40},
            warnings=[], n_alerts=40,
        ),
    ]
    ctx = SignalContext(
        cse_id=CSE, profiles=profiles, cse_frames=frames, frames=frames,
        peer_stats={}, quality_score=1.0,
        thresholds={
            "_global": {"quality_gate": 0.5, "max_record_ids": 25},
            "peer": {"min_group_size": 3, "outlier_z": 2.5},
            "superficial_closure": {
                "max_closure_hours": 2.0, "shallow_depth_max": 2.0,
                "min_alerts": 30, "velocity_bound": 0.25, "depth_bound": 0.5,
            },
            "template_investigation": {
                "max_unique_ratio": 0.20, "min_investigations": 20,
            },
        },
    )
    findings = run_context(ctx, only=["superficial_closure",
                                      "template_investigation"])
    assert len(findings) == 2
    store_findings(findings, db_path)
    return db_path


# ---------------------------------------------------------------------------
# Findings rehydration
# ---------------------------------------------------------------------------


class TestFindingsModule:
    def test_roundtrip_preserves_fields(self, db):
        loaded = load_findings_as_objects(db)
        assert len(loaded) == 2
        by_type = {f.signal_type: f for f in loaded}
        assert set(by_type) == {"superficial_closure", "template_investigation"}

        sup = by_type["superficial_closure"]
        assert STANDARD_CAVEAT in sup.caveats
        assert isinstance(sup.evidence, dict)
        assert sup.evidence["closure_velocity_median_h"] == 0.5
        assert sup.created_at is not None        # stamped at store time

        tpl = by_type["template_investigation"]
        assert tpl.evidence["n_unique_notes"] == 1

    def test_get_finding_hit_and_miss(self, db):
        assert get_finding(db, f"{CSE}:superficial_closure") is not None
        assert get_finding(db, "NOPE:nothing") is None

    def test_finding_from_row_handles_null_json(self):
        row = {"finding_id": "X:y", "cse_id": "X", "signal_type": "y",
               "signal_category": "execution_gap", "period": "ALL",
               "severity": "LOW", "confidence": None, "evidence_json": None,
               "contributing_record_ids_json": None, "detection_logic": None,
               "caveats_json": None, "recommended_actions_json": None,
               "data_quality_notes_json": None, "created_at": None}
        f = finding_from_row(row)
        assert f.evidence == {}
        assert f.confidence == 0.0
        assert f.contributing_record_ids == []
        assert STANDARD_CAVEAT in f.caveats      # re-added by __post_init__


# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------


class TestEvidenceTracer:
    def test_chain_exists_for_every_finding(self, db):
        for f in load_findings_as_objects(db):
            chain = EvidenceTracer(db).trace(f.finding_id)
            assert chain is not None
            assert chain.depth >= 3              # spec minimum traceability

    def test_chain_levels(self, db):
        chain = EvidenceTracer(db).trace(f"{CSE}:superficial_closure")
        assert chain.signal_type == "superficial_closure"
        assert chain.metrics, "no metric steps built"
        names = {m.metric_name for m in chain.metrics}
        assert {"closure_velocity_median_h", "inv_depth_median"} <= names
        for step in chain.metrics:
            assert step.calculation              # level 4: calculation text
            assert CSE in step.calculation

    def test_records_resolved_with_key_fields_and_relevance(self, db):
        chain = EvidenceTracer(db).trace(f"{CSE}:template_investigation")
        assert chain.records, "no contributing records resolved"
        inv_recs = [r for r in chain.records
                    if r.record_type == "investigations"]
        assert inv_recs
        sample = inv_recs[0]
        assert sample.record_id.startswith("INV-")
        assert sample.key_fields["evidence_entries"] == 1
        for rec in inv_recs[:3]:
            assert "depth=" in rec.relevance
        # Cap respected (max_record_ids = 25)
        assert len(chain.records) <= 25

    def test_alert_record_derived_fields(self, db):
        # superficial_closure carries no record IDs; verify alert resolution
        # via a directly stored finding instead.
        from src.analytics.signal_engine import store_findings

        probe = Finding(
            finding_id=f"{CSE}:probe_alerts", cse_id=CSE,
            signal_type="probe_alerts", signal_category="execution_gap",
            period="2024-Q4", severity="LOW", confidence=0.8,
            evidence={}, contributing_record_ids=["AL-000", "AL-001"],
            detection_logic="test fixture", created_at=None,
        )
        store_findings([probe], db)
        chain = EvidenceTracer(db).trace(f"{CSE}:probe_alerts")
        rec = chain.records[0]
        assert rec.record_type == "alerts"
        assert rec.key_fields["severity"] == "HIGH"
        assert rec.key_fields["open_to_close_hours"] == pytest.approx(0.5)
        assert "closed" in rec.relevance.lower()

    def test_missing_records_flagged_explicitly(self, db):
        # Inject a finding referencing records that do not exist anywhere.
        ghost = Finding(
            finding_id=f"{CSE}:ghost_signal", cse_id=CSE,
            signal_type="ghost_signal", signal_category="execution_gap",
            period="ALL", severity="LOW", confidence=0.9,
            evidence={}, contributing_record_ids=["AL-GHOST-1", "INV-NONE"],
            detection_logic="test fixture", created_at=None,
        )
        store_findings([ghost], db)
        chain = EvidenceTracer(db).trace(f"{CSE}:ghost_signal")
        assert chain is not None
        assert [m.record_id for m in chain.missing_records] == \
            ["AL-GHOST-1", "INV-NONE"]
        assert any("could not be resolved" in n
                   for n in chain.data_quality_notes)

    def test_unknown_finding_returns_none(self, db):
        assert EvidenceTracer(db).trace("does:not_exist") is None

    def test_summary_format_matches_spec(self, db):
        chain = EvidenceTracer(db).trace(f"{CSE}:template_investigation")
        text = chain.summary()
        assert text.startswith(f"Evidence Chain for {CSE}:template_investigation:")
        assert "Signal: template_investigation" in text
        assert "Metric: unique_ratio" in text
        assert "Calculation:" in text
        assert "Contributing Records:" in text

    def test_summary_paginates_long_chains(self, db):
        chain = EvidenceTracer(db).trace(f"{CSE}:template_investigation")
        short = chain.summary(max_records=3)
        assert "... (" in short and "more," in short

    def test_context_holds_non_metric_evidence(self, db):
        chain = EvidenceTracer(db).trace(f"{CSE}:superficial_closure")
        assert "thresholds" in chain.context or chain.metrics

    def test_escalation_and_asset_relevance_branches(self, db):
        from src.analytics.signal_engine import store_findings

        probe = Finding(
            finding_id=f"{CSE}:probe_mixed", cse_id=CSE,
            signal_type="probe_mixed", signal_category="negative_space",
            period="ALL", severity="LOW", confidence=0.7,
            evidence={},
            contributing_record_ids=["ES-0", "ES-1", "A-0", "CASE-X"],
            detection_logic="test fixture", created_at=None,
        )
        store_findings([probe], db)
        chain = EvidenceTracer(db).trace(f"{CSE}:probe_mixed")
        by_id = {r.record_id: r for r in chain.records}
        # ES-0 has_followup=False -> WITHOUT; ES-1 True -> with
        assert "WITHOUT" in by_id["ES-0"].relevance
        assert "with" in by_id["ES-1"].relevance.lower()
        assert "produced no alerts" in by_id["A-0"].relevance
        assert by_id["A-0"].key_fields["asset_type"] == "endpoint"
        # CASE-X does not exist -> explicit missing record
        assert [m.record_id for m in chain.missing_records] == ["CASE-X"]

    def test_cli_trace_hit_and_miss(self, db, capsys):
        from src.evidence.tracer import main as tracer_main

        rc = tracer_main(["trace", "--finding-id",
                          f"{CSE}:template_investigation", "--db", str(db)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Evidence Chain for" in out

        rc_missing = tracer_main(["trace", "--finding-id", "no:such",
                                  "--db", str(db)])
        assert rc_missing == 1
        assert "No finding" in capsys.readouterr().out

    def test_finding_from_row_attribute_style(self):
        from types import SimpleNamespace

        row = SimpleNamespace(finding_id="X:y", cse_id="X",
                              signal_type="y", signal_category="execution_gap",
                              period="ALL", severity="LOW", confidence=0.5,
                              evidence_json='{"a": 1}',
                              contributing_record_ids_json=None,
                              detection_logic="d", caveats_json=None,
                              recommended_actions_json=None,
                              data_quality_notes_json=None, created_at=None)
        f = finding_from_row(row)   # no .get attribute -> getattr path
        assert f.evidence == {"a": 1}
