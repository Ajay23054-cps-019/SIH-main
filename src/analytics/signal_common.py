"""Shared context passed to every signal function.

Signals are pure functions of (context) -> Optional[Finding]: no I/O, no
global state. The engine assembles one SignalContext per CSE — including
peer statistics computed once for the whole portfolio — so each detection
function stays cheap and deterministic.

The spec sketch described the signature as
``detect_<signal>(cse_id, profiles, dataset, config)``; those four inputs map
onto this context's fields (cse_id, profiles, frames/cse_frames, thresholds)
with peer_stats and quality_score added for the signals that need them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from src.analytics.profiles import PERIOD_ALL


@dataclass
class SignalContext:
    cse_id: str
    profiles: List[Any]                  # BehavioralProfile list for this CSE
    cse_frames: Dict[str, pd.DataFrame]  # raw records belonging to this CSE
    frames: Dict[str, pd.DataFrame]      # portfolio-wide frames (peer reference)
    peer_stats: Dict[str, Dict[str, float]]
    quality_score: float
    thresholds: Dict[str, Dict[str, Any]]

    def profile(self, period: Optional[str] = None) -> Optional[Any]:
        """Profile for ``period`` (default: latest quarter, falling back to ALL)."""
        by_period = {p.period: p for p in self.profiles}
        if period is not None:
            return by_period.get(period)
        quarters = self.quarter_periods()
        if quarters:
            return by_period[quarters[-1]]
        return by_period.get(PERIOD_ALL)

    def quarter_periods(self) -> List[str]:
        return sorted(p.period for p in self.profiles if p.period != PERIOD_ALL)

    def metric(self, name: str, period: Optional[str] = None) -> Any:
        prof = self.profile(period)
        return prof.metrics.get(name) if prof else None

    def t(self, signal: str, key: str) -> Any:
        return self.thresholds[signal][key]


# ---------------------------------------------------------------------------
# Frame helpers reused across signal modules
# ---------------------------------------------------------------------------


def inv_with_alerts(cse_frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Investigations joined to their alert's timestamp and severity."""
    inv = cse_frames.get("investigations")
    alerts = cse_frames.get("alerts")
    if inv is None or not len(inv):
        return inv if inv is not None else pd.DataFrame()
    if alerts is None or not len(alerts):
        out = inv.copy()
        out["alert_timestamp"] = pd.NaT
        out["severity"] = None
        return out
    return inv.merge(
        alerts[["alert_id", "timestamp", "severity"]]
        .rename(columns={"timestamp": "alert_timestamp"}),
        on="alert_id", how="left",
    )


def esc_with_severity(cse_frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Escalations joined to the severity of their investigation's alert."""
    esc = cse_frames.get("escalations")
    if esc is None or not len(esc):
        return esc if esc is not None else pd.DataFrame()
    joined = inv_with_alerts(cse_frames)
    if not len(joined) or "severity" not in joined.columns:
        out = esc.copy()
        out["severity"] = None
        return out
    sev_map = joined[["investigation_id", "severity"]]
    return esc.merge(sev_map, on="investigation_id", how="left")


def silent_assets(alerts: pd.DataFrame, assets: pd.DataFrame,
                  group_col: str = "asset_type") -> pd.DataFrame:
    """Per-group counts of assets never referenced by any alert.

    Returns a frame with columns [group_col, n_assets, n_silent, silent_share].
    """
    if assets is None or not len(assets):
        return pd.DataFrame(columns=[group_col, "n_assets", "n_silent", "silent_share"])
    alerted_ids = set(alerts["asset_id"].dropna()) if len(alerts) else set()

    rows = []
    for group, g in assets.groupby(group_col, dropna=False):
        n = len(g)
        n_silent = int((~g["asset_id"].isin(alerted_ids)).sum())
        rows.append({group_col: group, "n_assets": n, "n_silent": n_silent,
                     "silent_share": round(n_silent / n, 4)})
    return pd.DataFrame(rows)


def quarter_of(timestamps: pd.Series) -> pd.Series:
    """Timestamps -> 'YYYY-Qn' labels ('' where null)."""
    ts = pd.to_datetime(timestamps, errors="coerce")
    labels = ts.dt.to_period("Q").astype(str)
    return labels.where(ts.notna(), "")
