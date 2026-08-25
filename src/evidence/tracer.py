"""Evidence tracer: Finding -> Signal -> Metric -> Calculation -> Records.

An examiner must be able to validate any finding by walking its chain:

    Finding
      -> Signal        (which detector fired)
      -> Metric        (named values behind the decision)
      -> Calculation   (how each metric was computed)
      -> Records       (the actual alert/investigation/asset rows)

Contributing record IDs stored on the finding are resolved against SQLite.
Any ID that cannot be found is reported in ``missing_records`` and surfaced
as a data-quality note — a referenced-but-absent record is itself evidence
of a submission problem, never silently dropped.

Usage:
    python -m src.evidence.tracer trace --finding-id CSE-042:quality_degradation \
        --db data/sat_sa.db
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.evidence.findings import get_finding

# ---------------------------------------------------------------------------
# Chain data structures
# ---------------------------------------------------------------------------


@dataclass
class MetricStep:
    """One level of the chain: a named value plus how it was computed."""

    metric_name: str
    value: Any
    calculation: str


@dataclass
class ContributingRecord:
    record_type: str               # alerts / investigations / escalations / assets
    record_id: str
    key_fields: Dict[str, Any]
    relevance: str


@dataclass
class MissingRecord:
    record_id: str
    searched_tables: List[str]
    note: str


@dataclass
class EvidenceChain:
    finding_id: str
    cse_id: str
    signal_type: str               # level 2: Signal
    signal_category: str
    period: str
    severity: str
    confidence: float
    detection_logic: str
    metrics: List[MetricStep] = field(default_factory=list)      # levels 3+4
    records: List[ContributingRecord] = field(default_factory=list)  # level 5
    missing_records: List[MissingRecord] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)  # thresholds etc.
    data_quality_notes: List[str] = field(default_factory=list)

    @property
    def depth(self) -> int:
        """Levels of traceability present (spec requires >= 3)."""
        depth = 1  # the finding itself
        if self.signal_type:
            depth += 1
        if self.metrics:
            depth += 1   # metric + calculation count as one further level each
        if self.records or self.missing_records:
            depth += 1
        return depth

    def summary(self, max_records: int = 10) -> str:
        lines = [
            f"Evidence Chain for {self.finding_id}:",
            f"  CSE: {self.cse_id}   Period: {self.period}   "
            f"Severity: {self.severity}   Confidence: {self.confidence:.2f}",
            f"  Signal: {self.signal_type} ({self.signal_category})",
            f"  Detection logic: {self.detection_logic}",
        ]
        for step in self.metrics:
            lines.append(f"  Metric: {step.metric_name} = {step.value}")
            lines.append(f"    Calculation: {step.calculation}")
        if self.records:
            lines.append("  Contributing Records:")
            for rec in self.records[:max_records]:
                keys = ", ".join(f"{k}={v}" for k, v in rec.key_fields.items())
                lines.append(f"    - {rec.record_type[:-1].title()} "
                             f"{rec.record_id}: {keys}")
                lines.append(f"      Relevance: {rec.relevance}")
            if len(self.records) > max_records:
                lines.append(f"    ... ({len(self.records) - max_records} more, "
                             f"{len(self.records)} total)")
        for miss in self.missing_records:
            lines.append(f"  MISSING RECORD: {miss.record_id} "
                         f"(searched: {', '.join(miss.searched_tables)})")
            lines.append(f"    Note: {miss.note}")
        for note in self.data_quality_notes:
            lines.append(f"  Data Quality Note: {note}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Metric calculation descriptions
# ---------------------------------------------------------------------------

# Profiler metrics -> how they are computed (period/cse bound at runtime).
METRIC_CALCULATIONS = {
    "closure_velocity_median_h":
        "median of (closure_timestamp − timestamp) over closed alerts, hours",
    "inv_depth_mean": "mean evidence_entries across investigations linked to alerts",
    "inv_depth_median": "median evidence_entries across linked investigations",
    "inv_duration_p50_h":
        "median of (timestamp_close − timestamp_open), hours",
    "investigation_rate": "linked investigations ÷ total alerts",
    "esc_rate": "escalations linked to investigations ÷ linked investigations",
    "esc_followthrough_rate":
        "escalations with has_followup=true ÷ linked escalations with known followup",
    "triage_only_high_sev_rate":
        "closed CRITICAL/HIGH alerts without an investigation ÷ closed CRITICAL/HIGH alerts",
    "evidence_completeness_score":
        "mean field-presence over key alert/investigation fields",
    "weekend_alert_share": "alerts with weekday ≥ 5 ÷ total alerts",
    "after_hours_alert_share": "alerts outside 07:00–18:59 ÷ total alerts",
    "alert_volume_total": "count of alert records in period",
    "alert_volume_per_day": "alert_volume_total ÷ days spanned by the period",
}

def _calc_decline(ev: Dict[str, Any]) -> str:
    series = ev.get("depth_by_quarter") or {}
    keys = list(series)
    if len(keys) >= 2:
        first, last = series[keys[0]], series[keys[-1]]
        return (f"({first} − {last}) ÷ {first} across quarterly depth means "
                f"{keys[0]} → {keys[-1]}")
    return "(first − last) ÷ first across quarterly depth means"


# Signal-specific evidence keys -> parameterised calculation text. ``ev`` is
# the finding's evidence dict.
SIGNAL_EVIDENCE_CALCULATIONS = {
    "missing_rate":
        lambda ev: ("CRITICAL/HIGH alerts with no investigation record ÷ "
                    f"all CRITICAL/HIGH alerts "
                    f"({ev.get('n_without_investigation_record')}÷"
                    f"{ev.get('n_high_sev_alerts')})"),
    "unique_ratio":
        lambda ev: (f"{ev.get('n_unique_notes')} distinct note texts ÷ "
                    f"{ev.get('n_investigations')} investigations"),
    "decline_frac_first_to_last": _calc_decline,
    "burst_ratio": lambda ev: (f"peak-day closures ({ev.get('peak_closures')}) ÷ "
                               f"median daily closures ({ev.get('median_daily_closures')})"),
    "max_min_ratio": lambda ev: "max shift mean depth ÷ min shift mean depth",
    "modified_z":
        lambda ev: ("0.6745 × (value − peer_median) ÷ peer_MAD; "
                    f"peer group n={ev.get('peer_group_size')}"),
    "followthrough_rate":
        lambda ev: ("escalations with follow-up ÷ linked escalations "
                    f"({ev.get('n_escalations_linked', '?')} linked)"),
    "worst_silent_share":
        lambda ev: (f"assets of '{ev.get('worst_group')}' with zero alerts ÷ "
                    f"total assets of that type"),
    "ratio_observed_over_expected":
        lambda ev: ("observed alerts/day ÷ (peer median per-asset-day rate × "
                    "own asset count)"),
    "observed_alerts_per_day":
        lambda ev: "own alerts in the period ÷ days spanned by the period",
    "expected_alerts_per_day":
        lambda ev: (f"peer median per-asset-day rate "
                    f"({ev.get('peer_median_density_per_asset')}) × own "
                    f"asset count ({ev.get('n_assets')})"),
    # --- temporal_drift ---
    "value_from":
        lambda ev: f"profiler metric '{ev.get('metric')}' in "
                   f"{ev.get('from_period')}",
    "value_to":
        lambda ev: f"profiler metric '{ev.get('metric')}' in "
                   f"{ev.get('to_period')}",
    # --- unusual_quiet_period ---
    "quiet_period_count":
        lambda ev: "count of inter-alert gaps exceeding quiet_gap_hours",
    "max_gap_hours":
        lambda ev: "longest gap between consecutive alerts in the window",
    "median_alert_gap_hours":
        lambda ev: "median gap between consecutive alerts in the window",
    # --- severity_mismatch ---
    "triage_only_rate":
        lambda ev: ("closed CRITICAL/HIGH alerts without an investigation ÷ "
                    f"closed CRITICAL/HIGH alerts "
                    f"({ev.get('n_without_investigation')}÷"
                    f"{ev.get('n_high_sev_closed')})"),
    # --- missing_alert_categories ---
    "categories_expected_but_absent":
        lambda ev: ("alert categories reported by ≥presence_frac of the "
                    "peer group but absent from this CSE's submissions"),
    # --- escalation_absence ---
    "n_critical_alerts":
        lambda ev: "count of CRITICAL-severity alerts in the window",
    "n_weekend_critical_alerts":
        lambda ev: "count of CRITICAL alerts opened on weekends (Sat/Sun)",
    # --- recurring_incident ---
    "occurrences":
        lambda ev: (f"alerts of category '{ev.get('category')}' on asset "
                    f"{ev.get('asset_id')} in the window"),
    "unclosed_share":
        "alerts of this (asset, category) still open ÷ all of them",
    # --- kpi_divergence ---
    "depth_slope_per_quarter":
        lambda ev: "least-squares slope of quarterly inv_depth_mean vs "
                   "quarter index",
    "velocity_slope_per_quarter":
        lambda ev: "least-squares slope of quarterly closure_velocity_median_h "
                   "vs quarter index",
    # --- changepoint_drift ---
    "mean_before":
        lambda ev: "mean quarterly inv_depth_mean over the quarters BEFORE "
                   "the change point",
    "mean_after":
        lambda ev: "mean quarterly inv_depth_mean from the change point ONWARD",
    "drop":
        lambda ev: f"mean_before − mean_after "
                   f"({ev.get('mean_before')} − {ev.get('mean_after')})",
    "drop_frac":
        lambda ev: f"drop ÷ mean_before "
                   f"({ev.get('drop')} ÷ {ev.get('mean_before')})",
    "explained_share":
        lambda ev: f"1 − SSE(two-segment model) ÷ SSE(flat mean) "
                   f"(SSEs {ev.get('sse_split')} vs {ev.get('sse_flat')})",
}


def _metric_steps(evidence: Dict[str, Any], cse_id: str, period: str) \
        -> tuple[List[MetricStep], Dict[str, Any]]:
    """Split evidence into (metric steps, leftover context)."""
    steps: List[MetricStep] = []
    context: Dict[str, Any] = {}
    for key, value in evidence.items():
        if key in METRIC_CALCULATIONS:
            calc = METRIC_CALCULATIONS[key] + f" — {cse_id}, {period}"
            steps.append(MetricStep(key, value, calc))
        elif key in SIGNAL_EVIDENCE_CALCULATIONS:
            try:
                calc = SIGNAL_EVIDENCE_CALCULATIONS[key](evidence)
            except Exception:
                calc = SIGNAL_EVIDENCE_CALCULATIONS[key]({})
            steps.append(MetricStep(key, value, f"{calc} — {cse_id}, {period}"))
        else:
            context[key] = value
    return steps, context


# ---------------------------------------------------------------------------
# Record resolution
# ---------------------------------------------------------------------------

_ID_COLUMNS = {
    "alerts": "alert_id",
    "investigations": "investigation_id",
    "escalations": "escalation_id",
    "cases": "case_id",
    "assets": "asset_id",
}

_KEY_FIELDS = {
    "alerts": ["timestamp", "severity", "category", "status", "closure_timestamp"],
    "investigations": ["alert_id", "timestamp_open", "timestamp_close",
                       "evidence_entries"],
    "escalations": ["investigation_id", "timestamp", "has_followup"],
    "cases": ["case_type", "severity", "closure_time"],
    "assets": ["asset_type", "criticality", "monitoring_status"],
}


def _load_record_index(db_path: Path) -> Dict[str, tuple]:
    """Map every record ID across entity tables -> (table_name, row dict)."""
    from src.storage.db import load_table

    index: Dict[str, tuple] = {}
    for table, id_col in _ID_COLUMNS.items():
        try:
            df = load_table(table, db_path)
        except Exception:
            continue
        if df is None or not len(df):
            continue
        for _, row in df.iterrows():
            rid = row.get(id_col)
            if rid is not None and not pd.isna(rid):
                index.setdefault(str(rid), (table, row.to_dict()))
    return index


def _coerce_field(value: Any) -> Any:
    """Numbers/bools stay typed; timestamps stringify; NaN becomes None."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass  # non-scalar (list/dict) — fall through
    if isinstance(value, (int, float, bool)):
        return value
    return str(value)


def _record_fields(record_type: str, row: Dict[str, Any]) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    for col in _KEY_FIELDS.get(record_type, []):
        fields[col] = _coerce_field(row.get(col))
    # Derived convenience field for alerts: closure duration in hours.
    if record_type == "alerts":
        try:
            opened = pd.to_datetime(row.get("timestamp"))
            closed = pd.to_datetime(row.get("closure_timestamp"))
            if pd.notna(opened) and pd.notna(closed):
                fields["open_to_close_hours"] = round(
                    (closed - opened).total_seconds() / 3600, 3)
        except (TypeError, ValueError):
            pass
    return {k: v for k, v in fields.items() if v is not None}


def _relevance(record_type: str, record_id: str, fields: Dict[str, Any],
               signal_type: str) -> str:
    if record_type == "alerts" and "open_to_close_hours" in fields:
        return (f"Flagged by {signal_type}: closed "
                f"in {fields['open_to_close_hours']}h "
                f"at severity={fields.get('severity')}")
    if record_type == "investigations":
        return (f"Investigation behind alert {fields.get('alert_id')}; "
                f"depth={fields.get('evidence_entries')} entries")
    if record_type == "escalations":
        followup = fields.get("has_followup")
        state = "with" if str(followup) in ("True", "true", "1") else "WITHOUT"
        return f"Escalation {state} recorded follow-up action"
    if record_type == "assets":
        return (f"Asset of type={fields.get('asset_type')}, "
                f"criticality={fields.get('criticality')} produced no alerts")
    return f"Contributing {record_type[:-1]} record for {signal_type}"


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------


class EvidenceTracer:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._record_index: Optional[Dict[str, tuple]] = None

    @property
    def record_index(self) -> Dict[str, tuple]:
        if self._record_index is None:
            self._record_index = _load_record_index(self.db_path)
        return self._record_index

    def trace(self, finding_id: str) -> Optional[EvidenceChain]:
        from src.evidence.findings import get_finding

        finding = get_finding(self.db_path, finding_id)
        if finding is None:
            return None

        steps, context = _metric_steps(finding.evidence,
                                       finding.cse_id, finding.period)

        records: List[ContributingRecord] = []
        missing: List[MissingRecord] = []
        for rid in finding.contributing_record_ids:
            hit = self.record_index.get(str(rid))
            if hit is None:
                missing.append(MissingRecord(
                    record_id=str(rid),
                    searched_tables=sorted(_ID_COLUMNS),
                    note=(f"{rid} is referenced by this finding but absent "
                          f"from every submitted table — possible deletion or "
                          f"cross-CSE reference error."),
                ))
                continue
            table, row = hit
            fields = _record_fields(table, row)
            records.append(ContributingRecord(
                record_type=table,
                record_id=str(rid),
                key_fields=fields,
                relevance=_relevance(table, str(rid), fields, finding.signal_type),
            ))

        notes = list(finding.data_quality_notes)
        if missing:
            notes.append(f"{len(missing)} contributing record(s) could not be "
                         f"resolved against stored submissions.")
        return EvidenceChain(
            finding_id=finding.finding_id,
            cse_id=finding.cse_id,
            signal_type=finding.signal_type,
            signal_category=finding.signal_category,
            period=finding.period,
            severity=finding.severity,
            confidence=finding.confidence,
            detection_logic=finding.detection_logic,
            metrics=steps,
            records=records,
            missing_records=missing,
            context=context,
            data_quality_notes=notes,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tracer", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    trace_cmd = sub.add_parser("trace", help="Print one finding's evidence chain")
    trace_cmd.add_argument("--finding-id", required=True)
    trace_cmd.add_argument("--db", type=Path, default=Path("data/sat_sa.db"))
    args = parser.parse_args(argv)

    chain = EvidenceTracer(args.db).trace(args.finding_id)
    if chain is None:
        print(f"No finding '{args.finding_id}' in {args.db}")
        return 1
    print(chain.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
