"""Optional local-LLM narrative layer (Phase 9).

The analytical engine and every command run fully without this module ever
being called — an LLM is never required to produce or validate findings.
When enabled (``data/config/llm_config.json`` → ``enabled: true``), it turns
an *existing* evidence chain into examiner-friendly prose plus suggested
review questions.

Hard boundaries (enforced by prompts and by this module):
- The LLM sees only the finding JSON + evidence chain we hand it, and the
  prompt forbids inventing records, metrics, or certainty.
- Its output is wrapped in a GENERATED NARRATIVE label so it can never be
  mistaken for analytical evidence downstream.
- The client talks to a local runtime (Ollama by default) over localhost —
  no cloud calls, no telemetry.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from src.analytics.finding import Finding

PROMPTS_DIR = Path(__file__).parent / "prompts"
DEFAULT_CONFIG_PATH = Path("data/config/llm_config.json")

DEFAULT_LLM_CONFIG = {
    "enabled": False,
    "provider": "ollama",
    "model": "llama3:8b",
    "endpoint": "http://localhost:11434/api/generate",
    "timeout_seconds": 30,
    "max_tokens": 500,
}

NARRATIVE_LABEL = (
    "GENERATED NARRATIVE — produced by a local LLM from the evidence above. "
    "Commentary for the examiner, not analytical evidence."
)


class LLMDisabled(RuntimeError):
    """The config explicitly turns the narrative layer off."""


class LLMUnavailable(RuntimeError):
    """Enabled, but the local runtime could not be reached or failed."""


def load_llm_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Defaults deep-overridden by the JSON config file (if present)."""
    cfg = dict(DEFAULT_LLM_CONFIG)
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    if path.exists():
        try:
            cfg.update(json.loads(path.read_text()) or {})
        except (json.JSONDecodeError, OSError):
            pass  # unreadable config == disabled defaults
    return cfg


# ---------------------------------------------------------------------------
# Static explanations (no LLM needed)
# ---------------------------------------------------------------------------

# Some statistical concepts recur so often that they deserve deterministic
# wording rather than an LLM paraphrase — examiners can quote these directly.
STAT_GLOSSARY = {
    "z_score": (
        "z-score: how many standard deviations a value sits from the peer "
        "mean. |z| > 2.5 is treated as unusual for a group of this size."),
    "modified_z": (
        "modified z-score: like a z-score but built on the median and median "
        "absolute deviation, so one extreme CSE cannot stretch the scale and "
        "hide its own outlier status."),
    "percentile": (
        "percentile: the share of the comparison group at or below this "
        "value. 5th percentile means only 5% of peers are lower."),
    "closure_velocity": (
        "closure velocity: the typical hours between an alert opening and "
        "being closed. Unusually fast can mean rubber-stamping; unusually "
        "slow can mean backlog."),
    "inv_depth": (
        "investigation depth: evidence entries recorded per investigation. "
        "Shallow depth suggests alerts are closed without real analysis."),
}


def explain_statistic(term: str) -> str:
    term = term.strip().lower()
    if term in STAT_GLOSSARY:
        return STAT_GLOSSARY[term]
    for key, text in STAT_GLOSSARY.items():
        if key in term or term in key:
            return text
    return f"No plain-language note available for '{term}'."


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _load_template(name: str) -> str:
    return (PROMPTS_DIR / name).read_text()


def render_records_block(chain: Any) -> str:
    """Human-readable record list from an EvidenceChain (or a placeholder)."""
    if chain is None:
        return "(evidence chain not traced for this request)"
    lines: List[str] = []
    for rec in chain.records[:25]:
        keys = ", ".join(f"{k}={v}" for k, v in rec.key_fields.items())
        lines.append(f"- [{rec.record_type}] {rec.record_id}: {keys} — "
                     f"{rec.relevance}")
    if len(chain.records) > 25:
        lines.append(f"... ({len(chain.records) - 25} more)")
    for miss in chain.missing_records:
        lines.append(f"- MISSING: {miss.record_id}")
    return "\n".join(lines) if lines else "(no individual records cited)"


def build_finding_prompt(finding: Finding, chain: Any = None) -> str:
    return _load_template("finding_explanation.txt").format(
        finding_json=json.dumps(finding.to_dict(), indent=2, default=str),
        chain_summary=chain.summary() if chain is not None
        else "(chain not traced)",
        records_block=render_records_block(chain),
    )


def build_report_prompt(score_line: str,
                        findings: List[tuple]) -> str:
    """``findings`` is a list of ``(Finding, EvidenceChain-or-None)`` pairs."""
    blocks = []
    for f, chain in findings:
        block = [f"- {f.finding_id} [{f.severity}, confidence "
                 f"{f.confidence:.2f}] {f.detection_logic}",
                 f"  period={f.period} category={f.signal_category}"]
        if chain is not None and chain.metrics:
            mets = "; ".join(f"{m.metric_name}={m.value}"
                             for m in chain.metrics[:6])
            block.append(f"  metrics: {mets}")
        blocks.append("\n".join(block))
    return _load_template("portfolio_report.txt").format(
        score_line=score_line, findings_block="\n".join(blocks))


# ---------------------------------------------------------------------------
# Local-runtime client
# ---------------------------------------------------------------------------


def call_ollama(prompt: str, config: Mapping[str, Any]) -> str:
    """POST one generation request to the local Ollama endpoint."""
    payload = json.dumps({
        "model": config["model"],
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": int(config["max_tokens"])},
    }).encode()
    request = urllib.request.Request(
        config["endpoint"], data=payload, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(   # noqa: S310 (localhost-only by config)
                request, timeout=float(config["timeout_seconds"])) as resp:
            body = json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            OSError, ValueError) as exc:
        raise LLMUnavailable(
            f"local LLM at {config['endpoint']} failed: {exc}") from exc
    text = body.get("response")
    if not isinstance(text, str):
        raise LLMUnavailable("local LLM returned an unexpected payload")
    return text


def _parse_narrative(raw: str) -> tuple:
    """Prefer the requested JSON shape; fall back to raw prose."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip(), []
    if isinstance(parsed, dict):
        text = str(parsed.get("explanation", "")).strip() or raw.strip()
        questions = [str(q) for q in parsed.get("questions", [])][:3]
        return text, questions
    return raw.strip(), []


@dataclass
class GeneratedNarrative:
    subject_id: str
    explanation: str
    questions: List[str] = field(default_factory=list)
    model: str = ""
    label: str = NARRATIVE_LABEL

    @property
    def labeled_text(self) -> str:
        lines = [self.label, self.explanation]
        if self.questions:
            lines.append("Suggested examiner questions:")
            lines.extend(f"  {i}. {q}"
                         for i, q in enumerate(self.questions, start=1))
        return "\n".join(lines)


def explain_finding(
    finding: Finding,
    chain: Any = None,
    *,
    config: Optional[Mapping[str, Any]] = None,
    client: Optional[Callable[[str], str]] = None,
) -> GeneratedNarrative:
    """Generate a labeled narrative for one finding.

    ``client`` swaps the transport for testing; default is the local Ollama
    call. Raises :class:`LLMDisabled` / :class:`LLMUnavailable`.
    """
    cfg = dict(config) if config is not None else load_llm_config()
    if not cfg.get("enabled"):
        raise LLMDisabled(
            "narrative layer disabled (data/config/llm_config.json)")

    prompt = build_finding_prompt(finding, chain)
    runner = client if client is not None else \
        lambda p: call_ollama(p, cfg)
    explanation, questions = _parse_narrative(runner(prompt))
    return GeneratedNarrative(
        subject_id=finding.finding_id, explanation=explanation,
        questions=questions, model=str(cfg.get("model", "")),
    )


def explain_portfolio(
    score_line: str,
    findings: List[tuple],
    *,
    config: Optional[Mapping[str, Any]] = None,
    client: Optional[Callable[[str], str]] = None,
) -> GeneratedNarrative:
    """One narrative combining several findings (subject = portfolio)."""
    cfg = dict(config) if config is not None else load_llm_config()
    if not cfg.get("enabled"):
        raise LLMDisabled(
            "narrative layer disabled (data/config/llm_config.json)")

    prompt = build_report_prompt(score_line, findings)
    runner = client if client is not None else \
        lambda p: call_ollama(p, cfg)
    explanation, questions = _parse_narrative(runner(prompt))
    return GeneratedNarrative(
        subject_id="PORTFOLIO", explanation=explanation,
        questions=questions, model=str(cfg.get("model", "")),
    )


def maybe_explain(*args, **kwargs) -> tuple:
    """Like :func:`explain_finding` but returns ``(narrative|None, reason)``.

    Lets callers honour 'the system functions fully without the LLM' without
    try/except ceremony.
    """
    try:
        return explain_finding(*args, **kwargs), ""
    except (LLMDisabled, LLMUnavailable) as exc:
        return None, str(exc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="llm_explainer",
                                     description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    explain = sub.add_parser("explain", help="Narrate one finding's evidence")
    explain.add_argument("--finding-id", required=True)
    explain.add_argument("--db", type=Path, default=Path("data/sat_sa.db"))
    explain.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)

    report = sub.add_parser("report", help="Narrate one CSE's full review")
    report.add_argument("--cse-id", required=True)
    report.add_argument("--db", type=Path, default=Path("data/sat_sa.db"))
    report.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args(argv)

    from src.evidence.findings import (
        get_finding,
        load_findings_as_objects,
    )
    from src.evidence.tracer import EvidenceTracer

    config = load_llm_config(args.config)
    tracer = EvidenceTracer(args.db)

    def append_narrative(narrative, reason):
        if narrative is None:
            print(f"\n[narrative unavailable: {reason}]")
        else:
            print("\n" + narrative.labeled_text)

    if args.command == "explain":
        finding = get_finding(args.db, args.finding_id)
        if finding is None:
            print(f"No finding '{args.finding_id}' in {args.db}")
            return 1
        chain = tracer.trace(args.finding_id)
        print(chain.summary())
        narrative, reason = maybe_explain(finding, chain, config=config)
        append_narrative(narrative, reason)
        return 0

    # report
    findings = load_findings_as_objects(args.db, cse_id=args.cse_id)
    if not findings:
        print(f"No findings for {args.cse_id} in {args.db}")
        return 1
    pairs = [(f, tracer.trace(f.finding_id)) for f in findings]
    score_line = attention_score_line(args.db, args.cse_id)
    narrative, reason = None, ""
    try:
        narrative = explain_portfolio(score_line, pairs, config=config)
    except (LLMDisabled, LLMUnavailable) as exc:
        reason = str(exc)
    for _, chain in pairs:
        print(chain.summary())
        print()
    append_narrative(narrative, reason)
    return 0


def attention_score_line(db_path: Path, cse_id: str) -> str:
    """Stored priority line; graceful when scoring hasn't run yet."""
    import pandas as pd
    from sqlalchemy import text

    from src.storage.db import get_engine

    try:
        rows = pd.read_sql(text(
            "SELECT priority FROM attention_scores WHERE cse_id = :cid"),
            get_engine(db_path), params={"cid": cse_id})
    except Exception:
        return "Supervisory Attention Priority: (run scoring to populate)"
    priority = float(rows["priority"].iloc[0]) if len(rows) else 0.0
    return f"Supervisory Attention Priority: {priority:.1f} of 100"


def pd_read_scores(db_path: Path, cse_id: str) -> str:
    import pandas as pd
    from sqlalchemy import text

    from src.storage.db import get_engine

    rows = pd.read_sql(text(
        "SELECT priority FROM attention_scores WHERE cse_id = :cid"),
        get_engine(db_path), params={"cid": cse_id})
    priority = float(rows["priority"].iloc[0]) if len(rows) else 0.0
    return f"Supervisory Attention Priority: {priority:.1f} of 100"


if __name__ == "__main__":
    raise SystemExit(main())
