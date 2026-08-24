"""Data-quality assessment for ingested submissions.

Produces a transparent 0.0–1.0 score plus human-readable warnings. Findings
later attach these notes so examiners can see *what data was missing* behind
any signal — low quality must degrade confidence, never silently become a
security finding.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import pandas as pd

# Transparent scoring weights (documented in docs/canonical_schema.md):
WEIGHTS = {
    "missing_alert_timestamp": 0.15,
    "missing_alert_severity": 0.10,
    "unresolved_alert_asset": 0.10,
    "closed_without_closure_ts": 0.10,
    "orphan_investigations": 0.15,
    "orphan_escalations": 0.15,
    "rejected_records": 0.20,
    "schema_mismatch": 0.05,
}


@dataclass
class DataQualityReport:
    total_alerts: int = 0
    total_investigations: int = 0
    total_escalations: int = 0
    total_cases: int = 0
    total_assets: int = 0

    missing_timestamps: int = 0
    missing_severity: int = 0
    unresolved_asset_ids: int = 0          # missing or not in asset inventory
    closed_without_closure_ts: int = 0
    orphan_investigations: int = 0         # investigation.alert_id not in alerts
    orphan_escalations: int = 0            # escalation.investigation_id not in investigations

    rejected_records: int = 0              # failed normalization
    records_considered: int = 1            # avoid div-by-zero; set by caller
    unknown_columns: List[str] = field(default_factory=list)

    _warnings: List[str] = field(default_factory=list)

    # -- scoring ------------------------------------------------------------

    def overall_score(self) -> float:
        if self.total_alerts == 0 and self.total_investigations == 0:
            return 0.0
        n_alerts = max(self.total_alerts, 1)
        penalty = (
            WEIGHTS["missing_alert_timestamp"] * self.missing_timestamps / n_alerts
            + WEIGHTS["missing_alert_severity"] * self.missing_severity / n_alerts
            + WEIGHTS["unresolved_alert_asset"] * self.unresolved_asset_ids / n_alerts
            + WEIGHTS["closed_without_closure_ts"]
            * self.closed_without_closure_ts / max(self._closed_alerts, 1)
            + WEIGHTS["orphan_investigations"]
            * self.orphan_investigations / max(self.total_investigations, 1)
            + WEIGHTS["orphan_escalations"]
            * self.orphan_escalations / max(self.total_escalations, 1)
            + WEIGHTS["rejected_records"]
            * self.rejected_records / max(self.records_considered, 1)
            + WEIGHTS["schema_mismatch"]
            * min(len(self.unknown_columns) / 40.0, 1.0)
        )
        return round(max(0.0, 1.0 - penalty), 4)

    def warnings(self) -> List[str]:
        return list(self._warnings)

    # -- internal -----------------------------------------------------------

    _closed_alerts: int = 0


def assess_quality(
    frames: Dict[str, pd.DataFrame],
    rejections: List[dict],
    unknown_columns: Optional[Set[str]] = None,
) -> DataQualityReport:
    """Compute the quality report from normalized per-entity DataFrames."""
    alerts = frames.get("alerts", pd.DataFrame())
    invs = frames.get("investigations", pd.DataFrame())
    escs = frames.get("escalations", pd.DataFrame())
    assets = frames.get("assets", pd.DataFrame())

    report = DataQualityReport(
        total_alerts=len(alerts),
        total_investigations=len(invs),
        total_escalations=len(escs),
        total_cases=len(frames.get("cases", pd.DataFrame())),
        total_assets=len(assets),
        rejected_records=len(rejections),
        records_considered=max(
            len(rejections) + sum(len(f) for f in frames.values()), 1
        ),
        unknown_columns=sorted(unknown_columns or set()),
    )

    warnings: List[str] = []

    if len(alerts):
        report.missing_timestamps = int(alerts["timestamp"].isna().sum())
        report.missing_severity = int(alerts["severity"].isna().sum())
        closed = alerts[alerts.get("status") == "closed"]
        report._closed_alerts = len(closed)
        if "closure_timestamp" in closed.columns:
            report.closed_without_closure_ts = int(closed["closure_timestamp"].isna().sum())

        known_assets: Set[str] = set(assets["asset_id"]) if len(assets) else set()
        with_assets = alerts["asset_id"]
        report.unresolved_asset_ids = int(
            (with_assets.isna() | ~with_assets.isin(known_assets)).sum()
        ) if known_assets else int(with_assets.isna().sum())

        if report.missing_timestamps:
            warnings.append(
                f"{report.missing_timestamps} alerts missing timestamp"
            )
        if report.missing_severity:
            warnings.append(f"{report.missing_severity} alerts missing severity")
        if report.closed_without_closure_ts:
            warnings.append(
                f"{report.closed_without_closure_ts} closed alerts lack closure_timestamp"
            )
        if known_assets and report.unresolved_asset_ids:
            warnings.append(
                f"{report.unresolved_asset_ids} alert asset_ids not found in inventory"
            )
        elif not known_assets and len(alerts):
            warnings.append("no asset inventory submitted")

    if len(invs) and len(alerts):
        orphan_mask = ~invs["alert_id"].isin(set(alerts["alert_id"]))
        report.orphan_investigations = int(invs["alert_id"].notna().mul(orphan_mask).sum())
        if report.orphan_investigations:
            warnings.append(
                f"{report.orphan_investigations} investigations reference unknown alerts"
            )
    elif len(alerts) and not len(invs):
        warnings.append("no investigation records submitted")

    if len(escs) and len(invs):
        orphan_mask = ~escs["investigation_id"].isin(set(invs["investigation_id"]))
        report.orphan_escalations = int(
            escs["investigation_id"].notna().mul(orphan_mask).sum()
        )
        if report.orphan_escalations:
            warnings.append(
                f"{report.orphan_escalations} escalations reference unknown investigations"
            )

    for rej in rejections[:5]:
        first_error = rej["error"][0]["msg"] if isinstance(rej["error"], list) and rej["error"] \
            else str(rej["error"])
        warnings.append(f"rejected {rej['entity']}[{rej['index']}]: {first_error}")
    if len(rejections) > 5:
        warnings.append(f"...and {len(rejections) - 5} more rejected records")

    if report.unknown_columns:
        warnings.append(
            f"{len(report.unknown_columns)} unrecognized columns "
            f"(ignored): {', '.join(report.unknown_columns[:8])}"
        )

    report._warnings = warnings
    return report
