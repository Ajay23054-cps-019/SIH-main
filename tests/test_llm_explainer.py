"""Tests for Phase 9 optional local-LLM narrative layer (client mocked)."""
from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pandas as pd
import pytest

import src.evidence.llm_explainer as llm_mod
from src.evidence.llm_explainer import (
    DEFAULT_LLM_CONFIG,
    NARRATIVE_LABEL,
    LLMDisabled,
    LLMUnavailable,
    GeneratedNarrative,
    _parse_narrative,
    attention_score_line,
    build_finding_prompt,
    build_report_prompt,
    call_ollama,
    explain_finding,
    explain_portfolio,
    explain_statistic,
    load_llm_config,
    main,
    maybe_explain,
    render_records_block,
)
from src.analytics.finding import Finding
from src.evidence.tracer import (
    ContributingRecord,
    EvidenceChain,
    MetricStep,
    MissingRecord,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

CSE = "CSE-L01"


def _finding(cse_id=CSE, signal_type="template_investigation"):
    return Finding(
        finding_id=f"{cse_id}:{signal_type}", cse_id=cse_id,
        signal_type=signal_type, signal_category="execution_gap",
        period="ALL", severity="HIGH", confidence=0.93,
        evidence={"unique_ratio": 0.05}, detection_logic="identical notes",
    )


def _chain():
    chain = EvidenceChain(
        finding_id=f"{CSE}:template_investigation", cse_id=CSE,
        signal_type="template_investigation", signal_category="execution_gap",
        period="ALL", severity="HIGH", confidence=0.93,
        detection_logic="identical note texts across investigations",
        metrics=[MetricStep("unique_ratio", 0.05, "1 distinct ÷ 20")],
    )
    chain.records.append(ContributingRecord(
        record_type="investigations", record_id="INV-001",
        key_fields={"evidence_entries": 1}, relevance="depth=1 entries"))
    chain.missing_records.append(MissingRecord(
        record_id="INV-GHOST", searched_tables=["investigations"],
        note="absent"))
    return chain


@pytest.fixture()
def enabled_cfg(tmp_path):
    path = tmp_path / "llm_on.json"
    path.write_text(json.dumps({**DEFAULT_LLM_CONFIG, "enabled": True,
                                "model": "test-model"}))
    return path


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class TestConfig:
    def test_defaults_are_disabled(self, tmp_path):
        cfg = load_llm_config(tmp_path / "does_not_exist.json")
        assert cfg["enabled"] is False
        assert cfg["provider"] == "ollama"
        assert cfg["endpoint"].startswith("http://localhost")

    def test_file_overrides_defaults(self, enabled_cfg):
        cfg = load_llm_config(enabled_cfg)
        assert cfg["enabled"] is True
        assert cfg["model"] == "test-model"

    def test_corrupt_config_falls_back_to_disabled(self, tmp_path):
        bad = tmp_path / "broken.json"
        bad.write_text("{not json")
        assert load_llm_config(bad)["enabled"] is False


# ---------------------------------------------------------------------------
# Static glossary
# ---------------------------------------------------------------------------


class TestGlossary:
    def test_core_terms_documented(self):
        for term in ("z_score", "percentile", "modified_z"):
            assert len(explain_statistic(term)) > 30

    def test_fuzzy_and_unknown_terms(self):
        assert "median absolute deviation" in \
            explain_statistic("robust modified_z score")
        assert "No plain-language note" in explain_statistic("quantum_flux")


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


class TestPrompts:
    def test_prompt_enforces_evidence_only(self):
        prompt = build_finding_prompt(_finding(), _chain())
        assert "Base your explanation ONLY on the following evidence" in prompt
        assert "Do not invent" in prompt
        assert "compliant or non-compliant" in prompt

    def test_prompt_carries_evidence_content(self):
        prompt = build_finding_prompt(_finding(), _chain())
        assert CSE in prompt and "unique_ratio" in prompt
        assert "INV-001" in prompt          # real contributing record
        assert "MISSING: INV-GHOST" in prompt
        assert '"confidence": 0.93' in prompt

    def test_render_records_block_placeholders(self):
        assert "not traced" in render_records_block(None)
        assert "no individual records" in render_records_block(
            EvidenceChain(finding_id="x", cse_id="c", signal_type="s",
                          signal_category="c", period="ALL", severity="LOW",
                          confidence=0.5, detection_logic="d"))

    def test_report_prompt_lists_findings_and_score(self):
        prompt = build_report_prompt(
            "Supervisory Attention Priority: 77.3 of 100",
            [(_finding(), _chain()),
             (_finding(signal_type="superficial_closure"), None)])
        assert "77.3" in prompt
        assert "template_investigation" in prompt
        assert "superficial_closure" in prompt
        assert "does not mean the CSE is safe" in prompt


# ---------------------------------------------------------------------------
# Response parsing and labeling
# ---------------------------------------------------------------------------


class TestParsingAndLabels:
    def test_json_response_parsed(self):
        raw = json.dumps({"explanation": "Depth is unusually shallow.",
                          "questions": ["Q1?", "Q2?", "Q3?", "Q4?"]})
        text, questions = _parse_narrative(raw)
        assert text.startswith("Depth is unusually")
        assert questions == ["Q1?", "Q2?", "Q3?"]      # capped at 3

    def test_non_json_response_becomes_prose(self):
        text, questions = _parse_narrative("Looks templated to me.")
        assert text == "Looks templated to me."
        assert questions == []

    def test_labeled_text_marks_narrative_as_non_evidence(self):
        n = GeneratedNarrative(subject_id="X", explanation="Because.",
                               questions=["Ask this?"], model="m")
        out = n.labeled_text
        assert out.startswith(NARRATIVE_LABEL)
        assert "not analytical evidence" in out
        assert "1. Ask this?" in out


# ---------------------------------------------------------------------------
# Explain flow (mocked client)
# ---------------------------------------------------------------------------


class TestExplainFlow:
    def test_disabled_raises_and_maybe_explain_softens(self):
        with pytest.raises(LLMDisabled):
            explain_finding(_finding(), None, config={"enabled": False})
        narrative, reason = maybe_explain(_finding(), config={"enabled": False})
        assert narrative is None
        assert "disabled" in reason

    def test_mock_client_returns_narrative(self, enabled_cfg):
        cfg = load_llm_config(enabled_cfg)

        def client(prompt):
            assert "ONLY on the following evidence" in prompt
            return json.dumps({"explanation": "Notes repeat verbatim.",
                               "questions": ["Who reviewed these?"]})

        n = explain_finding(_finding(), _chain(), config=cfg, client=client)
        assert n.explanation == "Notes repeat verbatim."
        assert n.questions == ["Who reviewed these?"]
        assert n.model == "test-model"

    def test_unavailable_client_raises_llm_unavailable(self, enabled_cfg):
        def client(prompt):
            raise LLMUnavailable("runtime down")

        with pytest.raises(LLMUnavailable):
            explain_finding(_finding(), _chain(),
                            config=load_llm_config(enabled_cfg),
                            client=client)

    def test_portfolio_explain_flow(self, enabled_cfg):
        cfg = load_llm_config(enabled_cfg)
        n = explain_portfolio("priority line",
                              [(_finding(), None)],
                              config=cfg,
                              client=lambda p: json.dumps(
                                  {"explanation": "One theme dominates.",
                                   "questions": []}))
        assert n.subject_id == "PORTFOLIO"
        assert n.questions == []


# ---------------------------------------------------------------------------
# Local transport
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestOllamaTransport:
    def test_request_shape_and_parsing(self, monkeypatch, enabled_cfg):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["payload"] = json.loads(request.data.decode())
            captured["timeout"] = timeout
            return _FakeResponse({"response": "narrative text"})

        monkeypatch.setattr(llm_mod.urllib.request, "urlopen", fake_urlopen)
        cfg = load_llm_config(enabled_cfg)
        out = call_ollama("the prompt", cfg)
        assert out == "narrative text"
        assert captured["url"] == cfg["endpoint"]
        assert captured["payload"]["model"] == "test-model"
        assert captured["payload"]["prompt"] == "the prompt"
        assert captured["payload"]["stream"] is False
        assert captured["payload"]["options"]["num_predict"] == \
            int(cfg["max_tokens"])
        assert captured["timeout"] == pytest.approx(cfg["timeout_seconds"])

    def test_connection_error_maps_to_unavailable(self, monkeypatch,
                                                  enabled_cfg):
        def boom(request, timeout=None):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(llm_mod.urllib.request, "urlopen", boom)
        with pytest.raises(LLMUnavailable, match="connection refused"):
            call_ollama("p", load_llm_config(enabled_cfg))

    def test_bad_payload_maps_to_unavailable(self, monkeypatch, enabled_cfg):
        monkeypatch.setattr(llm_mod.urllib.request, "urlopen",
                            lambda req, timeout=None:
                            _FakeResponse({"unexpected": 1}))
        with pytest.raises(LLMUnavailable):
            call_ollama("p", load_llm_config(enabled_cfg))


# ---------------------------------------------------------------------------
# CLI (evidence always printed; narrative only when enabled)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    """Small DB holding frames + two engine-produced findings."""
    from src.analytics.profiles import BehavioralProfile
    from src.analytics.signal_common import SignalContext
    from src.analytics.signal_engine import (
        run_context,
        store_findings,
    )
    from src.storage.db import save_frames

    base = {"severity": "HIGH", "category": "malware", "status": "closed"}
    alerts = pd.DataFrame([{
        **base, "alert_id": f"AL-{i:03d}", "cse_id": CSE,
        "timestamp": pd.Timestamp("2024-02-01 08:00") + pd.Timedelta(minutes=i),
        "asset_id": f"A-{i}",
        "closure_timestamp": pd.Timestamp("2024-02-01 08:30"),
    } for i in range(12)])
    investigations = pd.DataFrame([{
        "investigation_id": f"INV-{i:03d}", "alert_id": f"AL-{i:03d}",
        "cse_id": CSE,
        "timestamp_open": pd.Timestamp("2024-02-01 09:00"),
        "timestamp_close": pd.Timestamp("2024-02-01 09:10"),
        "evidence_entries": 1, "notes": "Routine check, closed",
    } for i in range(12)])
    assets = pd.DataFrame([
        {"asset_id": f"A-{i}", "cse_id": CSE, "asset_type": "endpoint",
         "criticality": "HIGH", "environment": "production",
         "monitoring_status": "monitored"} for i in range(12)])
    escalations = pd.DataFrame(columns=[
        "escalation_id", "investigation_id", "cse_id", "timestamp",
        "decision", "has_followup", "recipient", "rationale"])

    tmp = tmp_path_factory.mktemp("llm")
    db_path = tmp / "llm.db"
    frames = {"alerts": alerts, "investigations": investigations,
              "assets": assets, "escalations": escalations}
    save_frames(frames, db_path)
    ctx = SignalContext(
        cse_id=CSE,
        profiles=[BehavioralProfile(cse_id=CSE, period="2024-Q4",
                                    metrics={"closure_velocity_median_h": 0.5,
                                             "inv_depth_median": 1.0,
                                             "alert_volume_total": 12},
                                    warnings=[], n_alerts=12)],
        cse_frames=frames, frames=frames, peer_stats={}, quality_score=1.0,
        thresholds={
            "_global": {"quality_gate": 0.5, "max_record_ids": 25},
            "superficial_closure": {
                "max_closure_hours": 2.0, "shallow_depth_max": 2.0,
                "min_alerts": 5, "velocity_bound": 0.25, "depth_bound": 0.5},
            "template_investigation": {"max_unique_ratio": 0.20,
                                       "min_investigations": 5},
        },
    )
    store_findings(run_context(ctx, only=["superficial_closure",
                                          "template_investigation"]), db_path)
    return db_path


@pytest.fixture()
def disabled_cfg(tmp_path):
    path = tmp_path / "off.json"
    path.write_text(json.dumps({"enabled": False}))
    return path


class TestCLI:
    def test_explain_without_llm_still_prints_chain(self, db, disabled_cfg,
                                                    capsys):
        rc = main(["explain", "--finding-id", f"{CSE}:template_investigation",
                   "--db", str(db), "--config", str(disabled_cfg)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Evidence Chain for" in out
        assert "[narrative unavailable:" in out

    def test_explain_with_enabled_mock_adds_labelled_narrative(
            self, db, enabled_cfg, monkeypatch, capsys):
        monkeypatch.setattr(
            llm_mod, "call_ollama",
            lambda prompt, cfg: json.dumps(
                {"explanation": "Every investigation repeats one note.",
                 "questions": ["Who approved closures?",
                               "Where are the case notes?"]}))
        rc = main(["explain", "--finding-id", f"{CSE}:template_investigation",
                   "--db", str(db), "--config", str(enabled_cfg)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "GENERATED NARRATIVE" in out
        assert "1. Who approved closures?" in out

    def test_report_without_llm_prints_chains_only(self, db, disabled_cfg,
                                                   capsys):
        rc = main(["report", "--cse-id", CSE, "--db", str(db),
                   "--config", str(disabled_cfg)])
        out = capsys.readouterr().out
        assert rc == 0
        assert out.count("Evidence Chain for") == 2
        assert "[narrative unavailable:" in out

    def test_report_missing_cse_returns_one(self, db, disabled_cfg, capsys):
        rc = main(["report", "--cse-id", "NOPE", "--db", str(db),
                   "--config", str(disabled_cfg)])
        assert rc == 1

    def test_attention_score_line_without_table_is_graceful(self, db):
        # No attention_scores table yet -> explicit note, never a crash.
        assert "run scoring" in attention_score_line(db, CSE)
