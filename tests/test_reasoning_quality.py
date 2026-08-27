"""Tests for Reasoning Quality analysis."""
import pytest
from src.analytics.reasoning_quality import (
    REASONING_TYPES,
    SEVERITY_DEPTH_EXPECTED,
    ReasoningQualityResult,
    analyze_reasoning_quality,
    coherence_score,
    detect_template_notes,
    parse_justification,
)


class TestParseJustification:
    def test_none_notes(self):
        result = parse_justification(None)
        assert result["word_count"] == 0
        assert "absent" in result["reasoning_types"]
        assert result["depth_score"] == 1

    def test_empty_notes(self):
        result = parse_justification("")
        assert result["word_count"] == 0
        assert "absent" in result["reasoning_types"]

    def test_short_notes(self):
        result = parse_justification("Checked.")
        assert result["word_count"] == 1
        assert "absent" in result["reasoning_types"]

    def test_template_notes(self):
        result = parse_justification("Investigated the alert. Checked the logs. Nothing suspicious found. Closed.")
        assert result["word_count"] > 5
        assert "template" in result["reasoning_types"]
        assert result["depth_score"] == 2

    def test_technical_notes(self):
        notes = (
            "Analyzed malware signature against threat intelligence feeds. "
            "Verified IOC hash against sandbox results. No lateral movement detected."
        )
        result = parse_justification(notes)
        assert "technical" in result["reasoning_types"]
        assert result["depth_score"] >= 4
        assert len(result["technical_terms"]) > 0

    def test_evidence_notes(self):
        notes = "Checked firewall logs and correlated with EDR events. Verified against DNS records."
        result = parse_justification(notes)
        assert "evidence_based" in result["reasoning_types"]

    def test_procedural_notes(self):
        notes = "Followed runbook procedure per policy SOP-001. Escalated per compliance framework."
        result = parse_justification(notes)
        assert "procedural" in result["reasoning_types"]

    def test_references_detected(self):
        notes = "Verified against ticket #4521 and incident INC-2024-001."
        result = parse_justification(notes)
        assert result["has_references"] is True

    def test_no_references(self):
        notes = "Checked the system and confirmed it was working as expected with no issues found."
        result = parse_justification(notes)
        assert result["has_references"] is False


class TestCoherenceScore:
    def test_high_severity_deep_notes(self):
        justification = parse_justification(
            "Analyzed malware signature against threat intelligence feeds. "
            "Verified IOC hash against sandbox results. Checked logs and correlated "
            "events across multiple systems. Cross-referenced with historical incidents "
            "and verified against known baseline behavior patterns."
        )
        score, gaps = coherence_score(justification, "CRITICAL")
        assert score > 0.6
        assert len(gaps) == 0

    def test_high_severity_shallow_notes(self):
        justification = parse_justification("Checked. Benign.")
        score, gaps = coherence_score(justification, "CRITICAL")
        assert score < 0.4
        assert len(gaps) > 0

    def test_low_severity_shallow_ok(self):
        justification = parse_justification("Checked. Benign.")
        score, gaps = coherence_score(justification, "LOW")
        assert score > 0.5

    def test_references_bonus(self):
        justification = parse_justification(
            "Verified against ticket #1234 and checked logs."
        )
        score, _ = coherence_score(justification, "MEDIUM")
        assert score > 0.5


class TestDetectTemplateNotes:
    def test_no_templates(self):
        investigations = [
            {"investigation_id": f"INV-{i}", "notes": f"Detailed analysis of incident {i} with specific findings."}
            for i in range(10)
        ]
        result = detect_template_notes(investigations)
        assert result["template_ratio"] < 0.3

    def test_all_templates(self):
        investigations = [
            {"investigation_id": f"INV-{i}", "notes": "Checked. Benign."}
            for i in range(10)
        ]
        result = detect_template_notes(investigations)
        assert result["template_ratio"] > 0.8

    def test_empty_investigations(self):
        result = detect_template_notes([])
        assert result["template_ratio"] == 0.0
        assert result["total_notes"] == 0


class TestAnalyzeReasoningQuality:
    def test_basic_analysis(self):
        alerts = [
            {"alert_id": f"AL-{i}", "severity": "HIGH"}
            for i in range(10)
        ]
        investigations = [
            {"investigation_id": f"INV-{i}", "alert_id": f"AL-{i}", "notes": "Checked. Benign."}
            for i in range(10)
        ]
        result = analyze_reasoning_quality("CSE-TEST", investigations, alerts, [])
        assert result.cse_id == "CSE-TEST"
        assert result.n_investigations == 10
        assert result.shallow_justification_count > 0
        assert result.mean_coherence < 0.5

    def test_deep_reasoning(self):
        alerts = [
            {"alert_id": f"AL-{i}", "severity": "CRITICAL"}
            for i in range(10)
        ]
        investigations = [
            {
                "investigation_id": f"INV-{i}",
                "alert_id": f"AL-{i}",
                "notes": (
                    f"Analyzed malware signature against threat intelligence. "
                    f"Verified IOC hash against sandbox. Checked logs and correlated events. "
                    f"Cross-referenced with ticket #{1000 + i}."
                ),
            }
            for i in range(10)
        ]
        result = analyze_reasoning_quality("CSE-TEST", investigations, alerts, [])
        assert result.mean_coherence > 0.5
        assert result.shallow_justification_count == 0

    def test_no_investigations(self):
        result = analyze_reasoning_quality("CSE-test", [], [], [])
        assert result.n_investigations == 0
        assert result.mean_depth == 0.0


class TestSeverityDepthExpected:
    def test_monotonic(self):
        assert SEVERITY_DEPTH_EXPECTED["LOW"] < SEVERITY_DEPTH_EXPECTED["MEDIUM"]
        assert SEVERITY_DEPTH_EXPECTED["MEDIUM"] < SEVERITY_DEPTH_EXPECTED["HIGH"]
        assert SEVERITY_DEPTH_EXPECTED["HIGH"] < SEVERITY_DEPTH_EXPECTED["CRITICAL"]
