"""Tests for the canonical data schema."""
import pandas as pd
import pytest
from pydantic import ValidationError

from src.analytics.schemas import (
    Alert,
    Asset,
    Case,
    CSEMetadata,
    Dataset,
    Escalation,
    Investigation,
)


class TestAlert:
    def test_minimal_alert_only_ids(self):
        a = Alert(alert_id="A1", cse_id="CSE-001")
        assert a.severity is None
        assert a.timestamp is None
        assert a.status is None

    def test_full_alert(self):
        a = Alert(
            alert_id="A2",
            cse_id="CSE-001",
            timestamp="2024-01-15T08:30:00",
            severity="high",
            category="malware",
            asset_id="AS-10",
            status="closed",
            closure_timestamp="2024-01-15T09:45:00",
            description="Suspicious process",
        )
        assert a.severity == "HIGH"  # normalized to uppercase
        assert a.timestamp.year == 2024
        assert a.status == "closed"

    def test_severity_alias_normalization(self):
        assert Alert(alert_id="A", cse_id="C", severity="crit").severity == "CRITICAL"
        assert Alert(alert_id="A", cse_id="C", severity=" Med ").severity == "MEDIUM"
        assert Alert(alert_id="A", cse_id="C", severity=None).severity is None

    def test_closure_before_creation_rejected(self):
        with pytest.raises(ValidationError):
            Alert(
                alert_id="A3",
                cse_id="CSE-001",
                timestamp="2024-01-15T10:00:00",
                closure_timestamp="2024-01-15T09:00:00",
            )

    def test_unknown_severity_passes_through_uppercased(self):
        # Data-quality concern, not a crash: ingestion logs it, analytics decides.
        assert Alert(alert_id="A", cse_id="C", severity="weird").severity == "WEIRD"


class TestInvestigation:
    def test_defaults(self):
        inv = Investigation(investigation_id="I1")
        assert inv.evidence_entries == 0
        assert inv.alert_id is None

    def test_close_before_open_rejected(self):
        with pytest.raises(ValidationError):
            Investigation(
                investigation_id="I2",
                timestamp_open="2024-02-01T12:00:00",
                timestamp_close="2024-02-01T11:00:00",
            )

    def test_negative_evidence_entries_rejected(self):
        with pytest.raises(ValidationError):
            Investigation(investigation_id="I3", evidence_entries=-1)


class TestEscalationCaseAsset:
    def test_escalation_defaults(self):
        e = Escalation(escalation_id="E1")
        assert e.has_followup is False
        assert e.decision is None

    def test_decision_normalized_lowercase(self):
        e = Escalation(escalation_id="E2", decision="ESCALATED")
        assert e.decision == "escalated"

    def test_case_related_alerts_default_empty(self):
        c = Case(case_id="K1")
        assert c.related_alerts == []
        assert Case(case_id="K2", related_alerts=["A1", "A2"]).related_alerts == ["A1", "A2"]

    def test_asset_criticality_normalized(self):
        a = Asset(asset_id="S1", cse_id="CSE-001", criticality="critical")
        assert a.criticality == "CRITICAL"


class TestDataset:
    def test_empty_dataset_has_all_frames(self):
        d = Dataset()
        frames = d.to_pandas()
        expected = {
            "cse_metadata",
            "alerts",
            "investigations",
            "escalations",
            "cases",
            "assets",
        }
        assert set(frames.keys()) == expected
        for frame in frames.values():
            assert isinstance(frame, pd.DataFrame)
            assert len(frame) == 0

    def test_summary_counts(self):
        d = Dataset(
            alerts=[Alert(alert_id="A1", cse_id="C")],
            investigations=[Investigation(investigation_id="I1")],
        )
        s = d.summary()
        assert s["alerts"] == 1
        assert s["investigations"] == 1
        assert s["cases"] == 0

    def test_to_pandas_rows_and_columns(self):
        d = Dataset(
            alerts=[
                Alert(alert_id="A1", cse_id="C", severity="HIGH"),
                Alert(alert_id="A2", cse_id="C"),
            ]
        )
        df = d.to_pandas()["alerts"]
        assert len(df) == 2
        assert set(["alert_id", "cse_id", "severity"]).issubset(df.columns)
        assert sorted(df["alert_id"]) == ["A1", "A2"]

    def test_cse_metadata_model(self):
        m = CSEMetadata(cse_id="CSE-042", sector="Telecom", size_band="Large")
        assert m.claimed_capabilities is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
