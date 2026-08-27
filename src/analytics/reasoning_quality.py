"""Reasoning Quality analysis - the justification gap detector."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


REASONING_TYPES = ("technical", "evidence_based", "procedural", "temporal",
                   "comparative", "template", "absent")

DEPTH_SCORES = {
    "absent": 1, "template": 2, "procedural": 3,
    "evidence_based": 4, "technical": 5, "temporal": 4, "comparative": 4,
}

TECHNICAL_KEYWORDS = {
    "malware", "ransomware", "trojan", "payload", "exploit", "cve",
    "signature", "ioc", "indicator", "hash", "md5", "sha256",
    "sandbox", "disassembler", "reverse", "forensic", "memory",
    "registry", "packet", "wireshark", "tcp", "udp", "port",
    "injection", "privilege", "lateral", "persistence",
    "rootkit", "keylogger", "phishing", "spearphish",
}

EVIDENCE_KEYWORDS = {
    "log", "logs", "artifact", "artifacts", "pcap", "packet",
    "firewall", "edr", "siem", "proxy", "dns", "auth", "event",
    "correlation", "matched", "verified", "confirmed", "cross-reference",
    "witnessed", "observed", "detected", "found",
}

PROCEDURAL_KEYWORDS = {
    "runbook", "playbook", "procedure", "policy", "sop", "sla",
    "compliance", "framework", "nist", "iso", "standard",
    "checklist", "workflow", "process", "guideline",
}

TEMPORAL_KEYWORDS = {
    "waited", "duration", "hours", "days", "timeline", "window",
    "maintenance", "schedule", "frequency", "recurring", "pattern",
}

COMPARATIVE_KEYWORDS = {
    "compared", "comparison", "similar", "previous", "prior", "historical",
    "baseline", "peer", "benchmark", "trend", "usual", "normal",
}

SEVERITY_DEPTH_EXPECTED = {"LOW": 1.5, "MEDIUM": 2.5, "HIGH": 3.5, "CRITICAL": 4.0}


def parse_justification(notes: Any) -> Dict[str, Any]:
    if not notes or not isinstance(notes, str):
        return {"word_count": 0, "reasoning_types": {"absent"}, "depth_score": 1,
                "technical_terms": [], "has_references": False, "raw_notes": ""}
    text = notes.strip()
    words = text.split()
    word_count = len(words)
    lower = text.lower()
    reasoning_types = set()
    word_set = set(lower.split())
    if word_count < 5:
        reasoning_types.add("absent")
    else:
        if TECHNICAL_KEYWORDS & word_set:
            reasoning_types.add("technical")
        if EVIDENCE_KEYWORDS & word_set:
            reasoning_types.add("evidence_based")
        if PROCEDURAL_KEYWORDS & word_set:
            reasoning_types.add("procedural")
        if TEMPORAL_KEYWORDS & word_set:
            reasoning_types.add("temporal")
        if COMPARATIVE_KEYWORDS & word_set:
            reasoning_types.add("comparative")
    if not reasoning_types:
        reasoning_types.add("template")
    technical_terms = [kw for kw in TECHNICAL_KEYWORDS if kw in lower]
    has_references = bool(re.search(
        r"(ticket|incident)\s*[#\s]?\d+|"
        r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|"
        r"https?://|"
        r"[A-Z]{2,}-\d+", text))
    depth_score = max(DEPTH_SCORES.get(t, 1) for t in reasoning_types)
    return {"word_count": word_count, "reasoning_types": reasoning_types,
            "depth_score": depth_score, "technical_terms": technical_terms,
            "has_references": has_references, "raw_notes": text}


def coherence_score(justification: Dict[str, Any], severity: str) -> Tuple[float, List[str]]:
    expected = SEVERITY_DEPTH_EXPECTED.get(severity, 2.5)
    actual = justification["depth_score"]
    word_count = justification["word_count"]
    gaps = []
    if actual >= expected:
        coherence = min(1.0, 0.7 + 0.1 * (actual - expected))
    else:
        coherence = max(0.0, 1.0 - (expected - actual) * 0.25)
    if severity in ("HIGH", "CRITICAL") and word_count < 20:
        coherence *= 0.5
        gaps.append(f"Short notes ({word_count} words) for {severity} alert")
    if severity in ("HIGH", "CRITICAL") and not justification["technical_terms"]:
        coherence *= 0.7
        gaps.append(f"No technical terms in {severity} investigation")
    if justification["has_references"]:
        coherence = min(1.0, coherence + 0.1)
    return round(max(0.0, min(1.0, coherence)), 3), gaps


def detect_template_notes(investigations: List[Dict[str, Any]]) -> Dict[str, Any]:
    notes = [inv.get("notes", "") or "" for inv in investigations]
    notes = [n.strip() for n in notes if n.strip()]
    if not notes:
        return {"template_ratio": 0.0, "unique_notes": 0, "total_notes": 0, "most_common_pattern": ""}
    normalized = [re.sub(r"\s+", " ", n.lower()) for n in notes]
    unique = set(normalized)
    counts = Counter(normalized)
    most_common = counts.most_common(1)[0] if counts else ("", 0)
    repeated = sum(c for c in counts.values() if c > 1)
    template_ratio = repeated / len(notes) if notes else 0.0
    return {"template_ratio": round(template_ratio, 3), "unique_notes": len(unique),
            "total_notes": len(notes), "most_common_pattern": most_common[0][:80] if most_common else ""}


@dataclass
class ReasoningQualityResult:
    cse_id: str
    n_investigations: int
    mean_depth: float
    mean_coherence: float
    shallow_justification_count: int
    template_ratio: float
    missing_escalation_rationale_count: int
    gaps: List[str] = field(default_factory=list)


def analyze_reasoning_quality(cse_id: str, investigations: List[Dict[str, Any]],
                              alerts: List[Dict[str, Any]], escalations: List[Dict[str, Any]]) -> ReasoningQualityResult:
    alert_sev = {a["alert_id"]: a.get("severity", "MEDIUM") for a in alerts}
    depths, coherences, gaps = [], [], []
    shallow_count = 0
    for inv in investigations:
        alert_id = inv.get("alert_id", "")
        notes = inv.get("notes", "")
        sev = alert_sev.get(alert_id, "MEDIUM")
        justification = parse_justification(notes)
        coh, coh_gaps = coherence_score(justification, sev)
        depths.append(justification["depth_score"])
        coherences.append(coh)
        gaps.extend(coh_gaps)
        if coh < 0.4 and sev in ("HIGH", "CRITICAL"):
            shallow_count += 1
    tmpl = detect_template_notes(investigations)
    esc_inv_ids = {e.get("investigation_id") for e in escalations}
    missing_esc = sum(1 for inv in investigations
                      if inv.get("investigation_id") in esc_inv_ids and len((inv.get("notes") or "").split()) < 10)
    return ReasoningQualityResult(
        cse_id=cse_id, n_investigations=len(investigations),
        mean_depth=round(sum(depths) / len(depths), 2) if depths else 0.0,
        mean_coherence=round(sum(coherences) / len(coherences), 3) if coherences else 0.0,
        shallow_justification_count=shallow_count, template_ratio=tmpl["template_ratio"],
        missing_escalation_rationale_count=missing_esc, gaps=gaps[:10])
