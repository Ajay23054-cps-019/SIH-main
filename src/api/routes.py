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
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, Request, UploadFile

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
                        db_path: Path = Depends(get_db_path)):
    """Upload one entity CSV (e.g. alerts.csv); appended to the SQLite DB."""
    from src.storage.db import TABLE_NAMES, save_frames

    filename = (file.filename or "").lower()
    entity = Path(filename).stem
    if entity not in TABLE_NAMES:
        raise NotFound(
            f"cannot infer entity type from '{file.filename}'; rename the "
            f"file to one of {', '.join(TABLE_NAMES)}",
            status_code=422, code="unknown_entity")
    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise NotFound(f"unreadable CSV: {exc}", status_code=422,
                       code="bad_csv")
    written = save_frames({entity: df}, db_path, if_exists="append")
    return envelope({"entity": entity, "rows_written": written.get(entity, 0),
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
