"""All SAT-SA API endpoints.

Analytics answers come straight from the SQLite store the pipeline writes
(profiler → signal engine → benchmarking → scoring). Nothing here
recalculates or reinterprets a metric; the API is a faithful window over
stored results, plus an on-demand trigger for the pipeline itself.
"""
from __future__ import annotations

import io
import threading
import uuid
from datetime import datetime
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, Form, Request, UploadFile

from src.analytics.benchmarking import (
    benchmark_cse,
    load_benchmarks,
)
from src.analytics.finding import Finding, load_thresholds
from src.analytics.profiles import PERIOD_ALL, BehavioralProfile
from src.api.errors import NotFound
from src.api.models import (
    CATEGORY_SLUGS,
    METRIC_ALIASES,
    AnalyticsRunRequest,
    FeedbackRequest,
    envelope,
    utc_now,
)

router = APIRouter(prefix="/api")

VERSION = "0.1.0"


def get_db_path(request: Request) -> Path:
    return Path(request.app.state.db_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_frames(db_path: Path, cse_id: Optional[str] = None) \
        -> Dict[str, pd.DataFrame]:
    from src.storage.db import TABLE_NAMES, load_table

    frames: Dict[str, pd.DataFrame] = {}
    for name in TABLE_NAMES:
        try:
            frames[name] = load_table(name, db_path, cse_id=cse_id)
        except Exception:
            frames[name] = pd.DataFrame()
    return frames


def _profiles(db_path: Path, cse_id: Optional[str] = None) \
        -> List[BehavioralProfile]:
    from src.analytics.profiler import load_profiles, rows_to_profiles

    return rows_to_profiles(load_profiles(db_path, cse_id=cse_id))


def _findings(db_path: Path, **filters) -> List[Finding]:
    from src.evidence.findings import load_findings_as_objects

    return load_findings_as_objects(db_path, **filters)


def _finding_dict(f: Finding) -> Dict[str, Any]:
    d = f.to_dict()
    d.pop("evidence", None)          # bulky; served on the detail endpoint
    return d


def _profile_to_dict(p: BehavioralProfile, period: Optional[str] = None) \
        -> Dict[str, Any]:
    if period is not None and p.period != period:
        return {}
    return {"cse_id": p.cse_id, "period": p.period, "n_alerts": p.n_alerts,
            "metrics": p.metrics, "warnings": p.warnings}


def _ensure_cse_metadata(db_path: Path, cse_id: str) -> None:
    """Create a minimal ``cse_metadata`` row for ``cse_id`` if none exists.

    Log-only uploads carry no entity metadata; a stub row lets the CSE appear
    in portfolio rankings with sensible Unknown/Medium defaults. Only columns
    already present in the (possibly pre-existing) ``cse_metadata`` table are
    written, so this is safe regardless of the table's current schema.
    """
    from sqlalchemy import text

    from src.analytics.schemas import CSEMetadata
    from src.storage.db import get_engine, save_frames

    meta = CSEMetadata(cse_id=cse_id, name=cse_id, sector="Unknown",
                       size_band="Medium")
    df = pd.DataFrame([meta.model_dump(mode="python")])

    engine = get_engine(db_path)
    with engine.connect() as conn:
        try:
            cols = [r[1] for r in
                    conn.execute(text("PRAGMA table_info(cse_metadata)")).fetchall()]
        except Exception:
            cols = []
    if cols:
        df = df[[c for c in df.columns if c in cols]]
    save_frames({"cse_metadata": df}, db_path, if_exists="append")


async def _ingest_logs(file: UploadFile, cse_id: Optional[str],
                     db_path: Path) -> Dict[str, Any]:
    """Parse plain-text syslog, classify into alerts, and append to the DB."""
    from src.analytics.log_classifier import logs_to_alerts
    from src.ingestion.log_parser import parse_syslog
    from src.storage.db import save_frames

    text = (await file.read()).decode("utf-8", errors="replace")
    parsed = parse_syslog(text)
    if not cse_id:
        cse_id = "CSE-LOGS-" + datetime.now().strftime("%Y%m%d%H%M%S")
    alerts, rejected = logs_to_alerts(parsed, cse_id)
    if not alerts:
        return {"entity": "logs", "rows_written": 0,
                "rows_rejected": len(rejected), "n_logs": len(parsed),
                "cse_id": cse_id}
    df = pd.DataFrame([a.model_dump(mode="python") for a in alerts])
    written = save_frames({"alerts": df}, db_path, if_exists="append")
    _ensure_cse_metadata(db_path, cse_id)
    return {"entity": "logs", "rows_written": written.get("alerts", 0),
            "rows_rejected": len(rejected), "n_logs": len(parsed),
            "cse_id": cse_id, "columns": list(df.columns)}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/health")
def health(db_path: Path = Depends(get_db_path)):
    from src.storage.db import table_counts

    counts = table_counts(db_path)
    return envelope({"status": "ok", "version": VERSION,
                     "database": str(db_path), "table_counts": counts})


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


@router.post("/ingest/upload")
async def ingest_upload(request: Request, file: UploadFile,
                        cse_id: Optional[str] = Form(None),
                        db_path: Path = Depends(get_db_path)):
    """Upload one entity file and append it to the SQLite DB.

    Two ingestion paths:

    * **Structured entities** (``alerts.csv``, ``investigations.json``, …): run
      through the same mapper + normalizer pipeline as batch ingestion, so
      heterogeneous column names (``EventID``, ``priority``, ``type`` …) are
      translated to the canonical schema before storage.
    * **Plain-text logs** (``logs.txt`` / ``*.log`` / a file named ``logs``):
      parsed as syslog, classified into alerts (severity, category, recommended
      solution) via deterministic rules, then stored as alerts.

    ``cse_id`` is an optional form field. When supplied it is stamped onto
    records that lack one (and, for logs, identifies the source CSE).
    """
    import tempfile
    from src.ingestion.pipeline import ingest_path
    from src.storage.db import TABLE_NAMES, save_frames

    filename = (file.filename or "").lower()
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    is_logs = (stem == "logs") or (stem == "log") or suffix in (".log", ".txt")

    if is_logs:
        body = await _ingest_logs(file, cse_id, db_path)
        return envelope(body)

    entity = stem
    if entity not in TABLE_NAMES:
        raise NotFound(
            f"cannot infer entity type from '{file.filename}'; rename the "
            f"file to one of {', '.join(TABLE_NAMES)} or upload logs as "
            f"logs.txt / *.log",
            status_code=422, code="unknown_entity")
    content = await file.read()
    try:
        pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise NotFound(f"unreadable CSV: {exc}", status_code=422,
                        code="bad_csv")

    with tempfile.NamedTemporaryFile(suffix=suffix or ".csv", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        result = ingest_path(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    if cse_id:
        for name, frame in result.frames.items():
            if frame is not None and len(frame) and "cse_id" in frame.columns:
                frame["cse_id"] = frame["cse_id"].fillna(cse_id)

    df = result.frames.get(entity)
    if df is None or len(df) == 0:
        return envelope({"entity": entity, "rows_written": 0,
                         "rows_rejected": result.records_rejected,
                         "columns": list(df.columns) if df is not None else []})
    written = save_frames({entity: df}, db_path, if_exists="append")
    return envelope({"entity": entity, "rows_written": written.get(entity, 0),
                     "rows_rejected": result.records_rejected,
                     "columns": list(df.columns)})


@router.get("/ingest/status/{cse_id}")
def ingest_status(cse_id: str, db_path: Path = Depends(get_db_path)):
    from src.storage.db import TABLE_NAMES, load_table

    counts = {}
    for name in TABLE_NAMES:
        try:
            counts[name] = int(len(load_table(name, db_path,
                                              cse_id=cse_id)))
        except Exception:
            counts[name] = 0
    if sum(counts.values()) == 0:
        raise NotFound(f"no submitted records for {cse_id}")
    return envelope({"cse_id": cse_id, "counts": counts})


@router.get("/ingest/quality/{cse_id}")
def ingest_quality(cse_id: str, db_path: Path = Depends(get_db_path)):
    from dataclasses import asdict

    from src.ingestion.quality import assess_quality

    frames = _load_frames(db_path, cse_id=cse_id)
    total = sum(len(f) for f in frames.values())
    if total == 0:
        raise NotFound(f"no submitted records for {cse_id}")
    report = assess_quality(frames, rejections=[], unknown_columns=set())
    data = {k: v for k, v in asdict(report).items() if not k.startswith("_")}
    data["overall_score"] = report.overall_score()
    data["warnings"] = report.warnings()
    return envelope({"cse_id": cse_id, "quality": data})


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


@router.get("/profiles/compare")
def profiles_compare(cse_ids: str, period: Optional[str] = None,
                     db_path: Path = Depends(get_db_path)):
    wanted = [c.strip() for c in cse_ids.split(",") if c.strip()]
    all_profs = _profiles(db_path)
    out = []
    for cse_id in wanted:
        profs = [p for p in all_profs if p.cse_id == cse_id
                 and (period is None or p.period == period)]
        out.extend(_profile_to_dict(p) for p in profs)
    missing = [c for c in wanted
               if not any(p["cse_id"] == c for p in out)]
    meta = {"period": period or "all", "missing_cse_ids": missing}
    return envelope(out, meta=meta)


@router.get("/profiles/{cse_id}")
def profile_detail(cse_id: str, period: Optional[str] = None,
                   db_path: Path = Depends(get_db_path)):
    profiles = [p for p in _profiles(db_path, cse_id=cse_id)
                if period is None or p.period == period]
    if not profiles:
        raise NotFound(f"no profile for {cse_id}"
                       + (f" at {period}" if period else ""))
    return envelope([_profile_to_dict(p) for p in profiles])


@router.get("/profiles/{cse_id}/trends")
def profile_trends(cse_id: str, metric: str, periods: int = 4,
                   db_path: Path = Depends(get_db_path)):
    key = METRIC_ALIASES.get(metric.lower(), metric)
    quarterly = sorted(
        (p for p in _profiles(db_path, cse_id=cse_id) if p.period != PERIOD_ALL),
        key=lambda p: p.period,
    )
    series = [{"period": p.period, "value": p.metrics.get(key)}
              for p in quarterly[-max(int(periods), 0):]]
    known = any(v is not None for _, v in series) if series else False
    if not known and not quarterly:
        raise NotFound(f"no quarterly profiles for {cse_id}")
    return envelope({"cse_id": cse_id, "metric": key,
                     "requested_as": metric, "series": series,
                     "note": None if known else
                     f"metric '{key}' absent from these profiles"})


@router.get("/evidence-model/{cse_id}")
def evidence_model(cse_id: str, db_path: Path = Depends(get_db_path)):
    """Expected-vs-observed evidence table for one CSE.

    The expected-evidence model states how many alerts, investigations,
    evidence entries and escalations a portfolio-typical SOC would have
    produced given this CSE's size band and severity mix — every baseline
    estimated leave-self-out. Explanatory view; the ``evidence_deficit``
    signal is the gated detector built on it.
    """
    from src.analytics.expected_evidence import evidence_table_for

    frames = _load_frames(db_path)
    table = evidence_table_for(cse_id, frames)
    if table is None:
        raise NotFound(f"no submitted records for {cse_id}")
    return envelope({"cse_id": cse_id, "dimensions": table},
                    meta={"note": "Baselines are portfolio expectations "
                          "conditioned on composition, estimated "
                          "leave-self-out (without this CSE's own records); "
                          "bands are 3σ negative-binomial approximations."})


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

@router.get("/findings")
def findings_list(cse_id: Optional[str] = None,
                  severity: Optional[str] = None,
                  category: Optional[str] = None,
                  db_path: Path = Depends(get_db_path)):
    rows = _findings(db_path, cse_id=cse_id, category=category)
    if severity:
        rows = [f for f in rows
                if f.severity.upper() == severity.upper()]
    rows.sort(key=lambda f: (-{"HIGH": 3, "MEDIUM": 2, "LOW": 1}
                             .get(f.severity, 0), -f.confidence))
    return envelope([_finding_dict(f) for f in rows],
                    meta={"count": len(rows)})


# NOTE: literal paths (category slugs) are registered *before* the
# parametric /findings/{finding_id} routes — FastAPI matches in order.
@router.get("/findings/{slug}")
def findings_by_category(slug: str, db_path: Path = Depends(get_db_path)):
    if slug not in CATEGORY_SLUGS:
        # Not a slug — treat as a finding ID and delegate (finding IDs like
        # "CSE-042:superficial_closure" arrive through this same route).
        if not _findings(db_path, finding_id=slug):
            raise NotFound(
                f"'{slug}' is neither a category slug "
                f"({', '.join(sorted(CATEGORY_SLUGS))}) nor a finding ID")
        return finding_detail(finding_id=slug, db_path=db_path)
    category = CATEGORY_SLUGS[slug]
    rows = _findings(db_path, category=category)
    return envelope([_finding_dict(f) for f in rows],
                    meta={"category": category, "count": len(rows)})


def _chain_to_dict(chain) -> Dict[str, Any]:
    return {
        "depth": chain.depth,
        "detection_logic": chain.detection_logic,
        "metrics": [{"metric_name": m.metric_name, "value": m.value,
                     "calculation": m.calculation} for m in chain.metrics],
        "records": [{"record_type": r.record_type, "record_id": r.record_id,
                     "key_fields": r.key_fields, "relevance": r.relevance}
                    for r in chain.records],
        "missing_records": [{"record_id": m.record_id,
                             "note": m.note}
                            for m in chain.missing_records],
        "summary": chain.summary(),
    }


@router.get("/findings/{finding_id}/explain")
def finding_explain(finding_id: str,
                    db_path: Path = Depends(get_db_path)):
    from src.evidence.tracer import EvidenceTracer

    matches = _findings(db_path, finding_id=finding_id)
    if not matches:
        raise NotFound(f"no finding '{finding_id}'")
    chain = EvidenceTracer(db_path).trace(finding_id)
    data = {"finding": matches[0].to_dict(),
            "chain": _chain_to_dict(chain) if chain else None}
    narrative = _maybe_llm_narrative(matches[0], chain)
    if narrative is not None:
        data["narrative"] = narrative
    else:
        data["narrative"] = None
    return envelope(data)


def _maybe_llm_narrative(finding: Finding, chain) -> Optional[Dict[str, Any]]:
    """Attach the labeled LLM narrative only when explicitly enabled."""
    from src.evidence.llm_explainer import maybe_explain

    narrative, reason = maybe_explain(finding, chain)
    if narrative is None:
        return None
    return {"label": narrative.label, "model": narrative.model,
            "explanation": narrative.explanation,
            "questions": narrative.questions}


@router.get("/findings/{finding_id}")
def finding_detail(finding_id: str, db_path: Path = Depends(get_db_path)):
    from src.evidence.tracer import EvidenceTracer

    matches = _findings(db_path, finding_id=finding_id)
    if not matches:
        raise NotFound(f"no finding '{finding_id}'")
    chain = EvidenceTracer(db_path).trace(finding_id)
    return envelope({"finding": matches[0].to_dict(),
                     "chain": _chain_to_dict(chain) if chain else None})


# ---------------------------------------------------------------------------
# Examiner feedback loop
# ---------------------------------------------------------------------------


@router.get("/feedback/summary")
def feedback_summary(db_path: Path = Depends(get_db_path)):
    """Per-signal-type disposition tallies + advisory calibration text."""
    from src.feedback import calibration_summary, load_feedback

    rows = calibration_summary(_findings(db_path), load_feedback(db_path),
                               load_thresholds())
    return envelope(rows, meta={
        "count": len(rows),
        "note": ("Advisory only — recommendations are applied by a human "
                 "via data/config/thresholds.json, never automatically.")})


@router.get("/findings/{finding_id}/feedback")
def feedback_get(finding_id: str, db_path: Path = Depends(get_db_path)):
    from src.feedback import load_feedback

    rows = load_feedback(db_path, finding_id=finding_id)
    return envelope(rows[0] if rows else None)


@router.post("/findings/{finding_id}/feedback")
def feedback_post(finding_id: str, body: FeedbackRequest,
                  db_path: Path = Depends(get_db_path)):
    """Record an examiner disposition (worthwhile / not_worthwhile / uncertain)."""
    from src.feedback import DISPOSITIONS, load_feedback, store_feedback

    if body.disposition not in DISPOSITIONS:
        raise NotFound(
            f"disposition must be one of {', '.join(DISPOSITIONS)}",
            status_code=422, code="bad_disposition")
    if not _findings(db_path, finding_id=finding_id):
        raise NotFound(f"no finding '{finding_id}'")
    row = store_feedback(db_path, finding_id, body.disposition,
                         examiner=body.examiner, note=body.note)
    return envelope(row)


# ---------------------------------------------------------------------------
# Supervisory cases (signal fusion)
# ---------------------------------------------------------------------------


@router.get("/cases")
def cases_list(cse_id: Optional[str] = None,
               db_path: Path = Depends(get_db_path)):
    from src.analytics.fusion import load_cases

    rows = load_cases(db_path, cse_id=cse_id)
    return envelope(rows, meta={
        "count": len(rows),
        "disclaimer": ("Supervisory cases aggregate potential concerns for "
                       "review ordering; not a compliance determination.")})


@router.get("/cases/{case_id}")
def case_detail(case_id: str, db_path: Path = Depends(get_db_path)):
    from src.analytics.fusion import load_cases

    matches = [c for c in load_cases(db_path) if c["case_id"] == case_id]
    if not matches:
        raise NotFound(f"no supervisory case '{case_id}'")
    case = matches[0]
    member_ids = set(case["finding_ids"])
    members = sorted(
        (_finding_dict(f) for f in _findings(db_path, cse_id=case["cse_id"])
         if f.finding_id in member_ids),
        key=lambda d: (-{"HIGH": 3, "MEDIUM": 2, "LOW": 1}
                       .get(d["severity"], 0), -d["confidence"]))
    return envelope({"case": case, "member_findings": members})


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


def _ranked_scores(db_path: Path):
    from src.analytics.scoring import compute_attention_scores, rank_scores

    metadata = _load_frames(db_path)["cse_metadata"]
    all_ids = metadata["cse_id"].astype(str).tolist() if len(metadata) else []
    scores = compute_attention_scores(_findings(db_path),
                                      all_cse_ids=all_ids,
                                      thresholds=load_thresholds())
    return rank_scores(scores)


@router.get("/portfolio/rankings")
def portfolio_rankings(db_path: Path = Depends(get_db_path)):
    ranked = _ranked_scores(db_path)

    # Dashboard context: sector/size and each CSE's most serious signal.
    frames = _load_frames(db_path)
    metadata = frames.get("cse_metadata")
    attrs: Dict[str, Dict[str, Any]] = {}
    if metadata is not None and len(metadata):
        for _, row in metadata.iterrows():
            attrs[str(row["cse_id"])] = {
                "sector": row.get("sector"), "size_band": row.get("size_band"),
            }
    rank_sev = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    top_signal: Dict[str, Finding] = {}
    for f in _findings(db_path):
        cur = top_signal.get(f.cse_id)
        if cur is None or (rank_sev.get(f.severity, 0),
                           f.confidence) > (rank_sev.get(cur.severity, 0),
                                            cur.confidence):
            top_signal[f.cse_id] = f

    data = [{
        "cse_id": s.cse_id, "priority": s.priority,
        "n_findings": s.n_findings, "n_signal_types": s.n_signal_types,
        "avg_confidence": s.avg_confidence, "components": s.components,
        "explanation": s.explanation(),
        "sector": attrs.get(s.cse_id, {}).get("sector"),
        "size_band": attrs.get(s.cse_id, {}).get("size_band"),
        "top_signal": (top_signal[s.cse_id].signal_type
                       if s.cse_id in top_signal else None),
        "top_signal_severity": (top_signal[s.cse_id].severity
                                if s.cse_id in top_signal else None),
    } for s in ranked]
    return envelope(data, meta={
        "disclaimer": ("Supervisory Attention Priority — review "
                       "prioritization only; NOT a risk or compliance "
                       "score. Low priority does not mean safe.")})


@router.get("/portfolio/summary")
def portfolio_summary(db_path: Path = Depends(get_db_path)):
    from src.storage.db import table_counts

    findings = _findings(db_path)
    by_severity: Dict[str, int] = {}
    by_category: Dict[str, int] = {}
    for f in findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
        by_category[f.signal_category] = \
            by_category.get(f.signal_category, 0) + 1
    ranked = _ranked_scores(db_path)[:5]
    return envelope({
        "tables": table_counts(db_path),
        "n_findings": len(findings),
        "findings_by_severity": by_severity,
        "findings_by_category": by_category,
        "flagged_cses": len({f.cse_id for f in findings}),
        "top5": [{"cse_id": s.cse_id, "priority": s.priority}
                 for s in ranked],
    })


# ---------------------------------------------------------------------------
# Peers
# ---------------------------------------------------------------------------


def _benchmark_dict(bench) -> Dict[str, Any]:
    return {
        "cse_id": bench.cse_id, "period": bench.period,
        "sector": bench.sector, "size_band": bench.size_band,
        "group_label": bench.group_label, "peer_ids": bench.peer_ids,
        "group_definition": bench.group_definition,
        "benchmarks": [asdict(mb) for mb in bench.benchmarks],
        "skipped": bench.skipped,
    }


@router.get("/peers/compare")
def peers_compare(cse_ids: str, period: str = PERIOD_ALL,
                  db_path: Path = Depends(get_db_path)):
    wanted = [c.strip() for c in cse_ids.split(",") if c.strip()]
    profiles = _profiles(db_path)
    metadata = _load_frames(db_path)["cse_metadata"]
    out = [benchmark_cse(cid, profiles, metadata, period=period,
                         thresholds=load_thresholds())
           for cid in wanted]
    return envelope([_benchmark_dict(b) for b in out],
                    meta={"period": period})


@router.get("/peers/{cse_id}")
def peers_for_cse(cse_id: str, period: str = PERIOD_ALL,
                  db_path: Path = Depends(get_db_path)):
    profiles = _profiles(db_path)
    if not any(p.cse_id == cse_id and p.period == period for p in profiles):
        raise NotFound(f"no profile for {cse_id} at {period}")
    metadata = _load_frames(db_path)["cse_metadata"]
    bench = benchmark_cse(cse_id, profiles, metadata, period=period,
                          thresholds=load_thresholds())
    return envelope(_benchmark_dict(bench))


# ---------------------------------------------------------------------------
# On-demand analytics
# ---------------------------------------------------------------------------

_JOBS: Dict[str, Dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


def _run_pipeline_job(job_id: str, db_path: Path, req: AnalyticsRunRequest):
    from src.analytics.benchmarking import (
        build_all_benchmarks,
        store_benchmarks,
    )
    from src.analytics.profiler import (
        compute_all_profiles,
        load_profiles,
        rows_to_profiles,
        store_profiles,
    )
    from src.analytics.scoring import (
        compute_attention_scores,
        rank_scores,
        store_scores,
    )
    from src.analytics.signal_engine import run_signals

    job = _JOBS[job_id]

    def step(message):
        job["steps"].append(message)

    try:
        step("loading submissions")
        frames = _load_frames(db_path)
        metadata = frames.get("cse_metadata")
        all_ids = (metadata["cse_id"].tolist()
                   if metadata is not None and len(metadata) else [])

        step("profiling")
        store_profiles(compute_all_profiles(frames), db_path)

        step("signals")
        findings = run_signals(db_path)
        result: Dict[str, Any] = {"findings": len(findings)}

        if req.include_benchmarks:
            step("benchmarks")
            profiles = rows_to_profiles(load_profiles(db_path))
            benches = build_all_benchmarks(profiles, metadata,
                                           thresholds=load_thresholds())
            result["benchmark_rows"] = store_benchmarks(benches, db_path)

        if req.include_scores:
            step("attention ranking")
            ranked = rank_scores(compute_attention_scores(
                findings, all_cse_ids=all_ids, thresholds=load_thresholds()))
            result["scores_stored"] = store_scores(ranked, db_path)

        job["result"] = result
        job["state"] = "done"
    except Exception as exc:  # noqa: BLE001 — surfaced to the client
        job["state"] = "failed"
        job["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        job["finished_at"] = utc_now()


@router.post("/analytics/run")
def analytics_run(request: Request, body: Optional[AnalyticsRunRequest] = None,
                  db_path: Path = Depends(get_db_path)):
    body = body or AnalyticsRunRequest()
    job_id = uuid.uuid4().hex[:12]
    with _JOBS_LOCK:
        _JOBS[job_id] = {"job_id": job_id, "state": "running", "steps": [],
                         "started_at": envelope()["meta"]["generated_at"],
                         "finished_at": None, "result": None, "error": None}
    thread = threading.Thread(target=_run_pipeline_job,
                              args=(job_id, db_path, body), daemon=True)
    thread.start()
    return envelope({"job_id": job_id, "state": "running"},
                    meta={"poll": f"/api/analytics/status/{job_id}"})


@router.get("/analytics/status/{job_id}")
def analytics_status(job_id: str):
    job = _JOBS.get(job_id)
    if job is None:
        raise NotFound(f"unknown job '{job_id}'")
    return envelope(job)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


@router.get("/report/{cse_id}")
def report_html(cse_id: str, db_path: Path = Depends(get_db_path)):
    """Render a printable HTML supervisory report for one CSE."""
    from fastapi.responses import HTMLResponse

    from src.analytics.benchmarking import load_benchmarks
    from src.analytics.finding import load_thresholds
    from src.analytics.profiles import BehavioralProfile
    from src.dashboard.routes import templates as _jinja_templates
    from src.evidence.findings import load_findings_as_objects
    from src.storage.db import load_table

    from src.analytics.profiler import load_profiles, rows_to_profiles

    findings = [f for f in load_findings_as_objects(db_path) if f.cse_id == cse_id]
    thresholds = load_thresholds()

    meta_df = load_table("cse_metadata", db_path, cse_id=cse_id)
    sector = str(meta_df["sector"].iloc[0]) if len(meta_df) and "sector" in meta_df else "Unknown"
    size = str(meta_df["size_band"].iloc[0]) if len(meta_df) and "size_band" in meta_df else "Unknown"

    prof_df = load_profiles(db_path, cse_id=cse_id)
    profiles = rows_to_profiles(prof_df)

    benches_loaded = load_benchmarks(db_path, cse_id=cse_id)
    benches = []
    total_outliers = 0
    for _, row in benches_loaded.iterrows():
        outs = json.loads(row["outliers_json"]) if row.get("outliers_json") else []
        total_outliers += len(outs)
        benches.append({
            "period": row["period"],
            "group_label": row.get("group_label", ""),
            "outliers": outs,
        })

    template = _jinja_templates.get_template("report.html")
    html = template.render(
        cse_id=cse_id,
        sector=sector,
        size_band=size,
        generated_at=envelope()["meta"]["generated_at"],
        findings=findings,
        profiles=profiles,
        benchmarks=benches,
        total_outliers=total_outliers,
        disclaimer=(
            "Potential supervisory concerns only — not determinations of "
            "non-compliance. Attention Priority is a review-ordering heuristic, "
            "not a risk or compliance score."
        ),
    )
    filename = f"sat_sa_report_{cse_id.replace('-', '_')}.html"
    return HTMLResponse(
        content=html,
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )
