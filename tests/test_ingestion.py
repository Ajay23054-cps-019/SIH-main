"""Tests for the format-agnostic ingestion layer."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.ingestion.adapters import (
    CsvAdapter,
    JsonAdapter,
    JsonlAdapter,
    ParseError,
    get_adapter,
)
from src.ingestion.mapper import ColumnMapper, normalize_key
from src.ingestion.normalizer import normalize_records
from src.ingestion.pipeline import ingest_path
from src.ingestion.quality import assess_quality
from src.storage.db import load_table, save_frames


# ---------------------------------------------------------------------------
# Fixtures: a tiny heterogeneous submission set
# ---------------------------------------------------------------------------

CSV_ALERTS = """EventID,CSE,created_time,priority,type,host,state,closed_at
AL-1,CSE-001,2024-01-05 08:30:00,HIGH,malware,HOST-A,closed,2024-01-05 10:00:00
AL-2,CSE-001,2024-01-05 09:15:00,LOW,network,HOST-B,open,
"""

JSON_INVESTIGATIONS = {
    "investigations": [
        {"inv_id": "INV-1", "alert_id": "AL-1", "cse_id": "CSE-001",
         "opened_at": "2024-01-05T08:35:00", "end_time": "2024-01-05T09:30:00",
         "evidence_count": 7, "assignee": "AN-01", "notes": "looked at stuff"},
        {"inv_id": "INV-BAD", "alert_id": "AL-X",
         "timestamp_open": "2024-01-05T10:00:00",
         "timestamp_close": "2024-01-05T09:00:00"},  # close before open -> rejected
    ]
}

JSONL_ESCALATIONS = (
    '{"esc_id": "ESC-1", "investigation_id": "INV-1", "cse_id": "CSE-001", '
    '"timestamp": "2024-01-05T09:40:00", "decision": "escalated_with_action", '
    '"followup": true, "sent_to": "SOC Lead"}\n'
    '{"escalation_id": "ESC-2", "investigation_id": "INV-1"}\n'  # canonical names
)

ASSETS_ROWS = [
    {"asset_id": "HOST-A", "cse_id": "CSE-001", "device_type": "server",
     "criticality_level": "CRIT"},
    {"asset_id": "HOST-B", "cse_id": "CSE-001", "asset_type": "endpoint"},
]


@pytest.fixture(scope="module")
def submission_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("submission")
    (d / "alerts.csv").write_text(CSV_ALERTS)
    (d / "investigations.json").write_text(json.dumps(JSON_INVESTIGATIONS))
    (d / "escalations.jsonl").write_text(JSONL_ESCALATIONS)
    (d / "assets.json").write_text(json.dumps(ASSETS_ROWS))
    return d


@pytest.fixture(scope="module")
def result(submission_dir):
    return ingest_path(submission_dir)


# ---------------------------------------------------------------------------
# Mapper
# ---------------------------------------------------------------------------


class TestMapper:
    def test_normalize_key(self):
        assert normalize_key(" EventID ") == "eventid"
        assert normalize_key("closure-timestamp") == "closure_timestamp"

    def test_generic_and_entity_variants(self):
        mapper = ColumnMapper()
        # generic variant
        rec = mapper.map_record({"created_time": "..."}, entity=None)
        assert rec["timestamp"] == "..."
        # risky 'type' alias resolves per entity: category for alerts, asset_type for assets
        assert mapper.map_record({"type": "malware"}, entity="alerts")["category"] == "malware"
        assert mapper.map_record({"type": "server"}, entity="assets")["asset_type"] == "server"

    def test_infer_entity_from_primary_keys(self):
        mapper = ColumnMapper()
        assert mapper.infer_entity({"EventID": "A1"}) == "alerts"
        assert mapper.infer_entity({"inv_id": "I1"}) == "investigations"
        assert mapper.infer_entity({"esc_id": "E1"}) == "escalations"
        assert mapper.infer_entity({"case_id": "K1"}) == "cases"
        assert mapper.infer_entity({"asset": "S1"}) == "assets"
        assert mapper.infer_entity({"industry": "Telecom"}) is None
        assert mapper.infer_entity({"cse": "CSE-001"}) == "cse_metadata"
        # escalation rows also carry investigation ids — escalation wins
        assert mapper.infer_entity(
            {"esc_id": "E1", "investigation_id": "I1"}
        ) == "escalations"

    def test_unknown_columns_tracked_not_dropped(self):
        mapper = ColumnMapper()
        rec = mapper.map_record({"weird_col": 1}, entity="alerts")
        assert rec["weird_col"] == 1
        assert "weird_col" in mapper.unknown_columns


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


class TestAdapters:
    def test_csv(self, tmp_path):
        p = tmp_path / "a.csv"
        p.write_text("a,b\n1,2\n")
        rows = CsvAdapter().load_rows(p)
        assert rows == [{"a": 1, "b": 2}]

    def test_json_shapes(self, tmp_path):
        flat = tmp_path / "flat.json"
        flat.write_text(json.dumps([{"x": 1}, {"x": 2}]))
        assert len(JsonAdapter().load_rows(flat)) == 2

        envelope = tmp_path / "env.json"
        envelope.write_text(json.dumps({"data": [{"x": 3}]}))
        assert JsonAdapter().load_rows(envelope) == [{"x": 3}]

        single = tmp_path / "one.json"
        single.write_text(json.dumps({"y": 9}))
        assert JsonAdapter().load_rows(single) == [{"y": 9}]

    def test_jsonl_tolerates_bad_lines(self, tmp_path):
        p = tmp_path / "s.jsonl"
        p.write_text('{"ok": 1}\nnot-json\n{"ok": 2}\n')
        rows = JsonlAdapter().load_rows(p)
        assert len(rows) == 3 and "__parse_error__" in rows[1]

    def test_unsupported_suffix(self, tmp_path):
        p = tmp_path / "x.parquet"
        p.write_bytes(b"...")
        with pytest.raises(ParseError):
            get_adapter(p)


# ---------------------------------------------------------------------------
# Normalizer + quality
# ---------------------------------------------------------------------------


class TestNormalizerAndQuality:
    def test_alias_record_becomes_canonical_alert(self):
        models, rej = normalize_records("alerts", [
            {"alert_id": "AL-1", "cse_id": "CSE-001", "severity": "crit",
             "status": "closed"},
        ])
        assert rej == []
        assert models[0].severity == "CRITICAL"

    def test_impossible_timestamps_rejected_not_raised(self):
        _, rej = normalize_records("investigations", [
            {"investigation_id": "I1",
             "timestamp_open": "2024-02-02T10:00:00",
             "timestamp_close": "2024-02-02T09:00:00"},
            {"investigation_id": "I2"},  # fine
        ])
        assert len(rej) == 1
        assert rej[0]["index"] == 0

    def test_json_string_fields_decoded(self):
        models, rej = normalize_records("cases", [
            {"case_id": "K1", "related_alerts": '["AL-1","AL-2"]'},
        ])
        assert rej == [] and models[0].related_alerts == ["AL-1", "AL-2"]

    def test_quality_flags_orphans_and_missing(self):
        alerts = pd.DataFrame([
            {"alert_id": "AL-1", "cse_id": "C", "timestamp": None, "severity": None,
             "asset_id": "GHOST", "status": "closed", "closure_timestamp": None},
        ])
        invs = pd.DataFrame([{"investigation_id": "I9", "alert_id": "NOPE"}])
        escs = pd.DataFrame([{"escalation_id": "E9", "investigation_id": "NOPE"}])
        report = assess_quality(
            {"alerts": alerts, "investigations": invs, "escalations": escs},
            rejections=[{"entity": "alerts", "index": 0, "error": [{"msg": "bad"}]}],
        )
        assert 0.0 <= report.overall_score() < 0.5
        text = " ".join(report.warnings())
        for fragment in ("missing timestamp", "unknown alerts",
                         "unknown investigations", "rejected"):
            assert fragment in text

    def test_quality_clean_data_scores_high(self, result):
        assert result.quality_score >= 0.90


# ---------------------------------------------------------------------------
# Pipeline end-to-end
# ---------------------------------------------------------------------------


class TestPipeline:
    def test_mixed_format_directory_ingested(self, result):
        assert result.files_processed == 4
        assert result.records_rejected >= 1  # INV-BAD close-before-open
        frames = result.frames
        assert set(frames["alerts"].alert_id) == {"AL-1", "AL-2"}
        assert set(frames["assets"].asset_type) == {"server", "endpoint"}
        esc = frames["escalations"]
        assert set(esc.has_followup) == {True, False}
        assert esc.loc[esc.escalation_id == "ESC-1", "recipient"].iloc[0] == "SOC Lead"
        # Dataset container mirrors frames
        assert len(result.dataset.alerts) == 2

    def test_demo_dataset_ingest_and_sqlite_roundtrip(self, tmp_path):
        res = ingest_path(Path("data/samples/demo_dataset"))
        assert res.quality_score >= 0.90
        assert len(res.frames.get("alerts", pd.DataFrame())) > 90_000

        db = tmp_path / "roundtrip.db"
        save_frames(res.frames, db)
        alerts_back = load_table("alerts", db)
        assert len(alerts_back) == len(res.frames["alerts"])
        counts = load_table("assets", db).cse_id.nunique()
        assert counts == 50

    def test_missing_path_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ingest_path(tmp_path / "nope")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
