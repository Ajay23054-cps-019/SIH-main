"""Full expected-evidence model: what SHOULD this CSE have produced?

For every CSE the model answers: given its observable composition — the
size band that scales its alert stream and the severity mix of its own
alerts and investigations — how much supervisory evidence would the
portfolio-typical SOC have submitted? Four dimensions:

    alerts             expected from the leave-self-out size-band mean
    investigations     own alerts per severity x leave-self-out investigation rate
    evidence_entries   own investigations per severity x leave-self-out mean depth
    escalations        own investigations per severity x leave-self-out escalation rate

Every baseline rate is estimated **leave-self-out**: the CSE under scrutiny
never contributes to its own expectation, so a portfolio-wide deficit cannot
hide by dragging the baseline down with it. Rates condition on severity mix
(the direct driver of investigation/depth/escalation behaviour) rather than
sector — once composition is conditioned on, sector adds no further
information about expected evidence volume. Asset-mix conditioning for
telemetry expectations lives where it belongs, in ``alert_volume_gap`` and
the peer benchmarks.

Uncertainty bands use a negative-binomial-style normal approximation,
``expected ± z·sqrt(expected + overdispersion·expected²)``: pure Poisson
noise plus a small variance-inflation term, so small-count dimensions get
proportionally wider bands and a deficit must clear BOTH the calibrated
ratio gate and the band's lower edge before it is called thin.

Pure functions of frames -> tables: no I/O, deterministic.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
DIMENSIONS = ("alerts", "investigations", "evidence_entries", "escalations")

# Table keys per dimension
_OBSERVED = "observed"
_EXPECTED = "expected"
_RATIO = "ratio"
_BAND_LOW = "band_low"
_BAND_HIGH = "band_high"


def _round(v: float, digits: int = 4) -> Optional[float]:
    return None if v is None else round(float(v), digits)


def _band(expected: float, z: float, overdispersion: float) -> tuple:
    """Normal-approximation band half-width around an expected count."""
    sd = (expected + overdispersion * expected * expected) ** 0.5
    return z * sd


def _severity_counts(df: pd.DataFrame, extra: Optional[str] = None) -> Dict[str, Any]:
    """Per-severity totals; ``extra`` names an optional value column to sum."""
    if df is None or not len(df) or (extra and extra not in df.columns):
        return {s: (0.0 if extra else 0) for s in SEVERITIES}
    out: Dict[str, Any] = {}
    for s in SEVERITIES:
        sel = df["severity"] == s
        if extra:
            out[s] = float(df.loc[sel, extra].fillna(0).sum())
        else:
            out[s] = int(sel.sum())
    return out


def _joined_investigations(frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Investigations carrying their alert's severity (severity drives depth)."""
    inv = frames.get("investigations")
    alerts = frames.get("alerts")
    if inv is None or not len(inv):
        return pd.DataFrame(columns=["investigation_id", "cse_id", "severity",
                                     "evidence_entries"])
    if alerts is None or not len(alerts) or \
            "severity" not in inv.columns:
        if "severity" not in inv.columns:
            inv = inv.copy()
            inv["severity"] = None
        return inv
    return inv.merge(alerts[["alert_id", "severity"]], on="alert_id",
                     how="left")


def _joined_escalations(frames: Dict[str, pd.DataFrame],
                        inv_sev: pd.DataFrame) -> pd.DataFrame:
    """Escalations carrying their investigation's severity."""
    esc = frames.get("escalations")
    if esc is None or not len(esc):
        return pd.DataFrame(columns=["escalation_id", "cse_id", "severity"])
    if not len(inv_sev):
        esc = esc.copy()
        esc["severity"] = None
        return esc
    return esc.merge(inv_sev[["investigation_id", "severity"]],
                     on="investigation_id", how="left")


def evidence_table_for(cse_id: str, frames: Dict[str, pd.DataFrame],
                       band_z: float = 3.0, overdispersion: float = 0.001) \
        -> Optional[Dict[str, Dict[str, Any]]]:
    """Expected-vs-observed table for one CSE (leave-self-out baselines).

    Returns ``{dimension: {observed, expected, ratio, band_low, band_high}}``
    or ``None`` when the CSE submitted no records at all.
    """
    alerts = frames.get("alerts")
    meta = frames.get("cse_metadata")
    if alerts is None or not len(alerts) or cse_id not in set(alerts["cse_id"]):
        return None

    own_alerts = alerts[alerts["cse_id"] == cse_id]
    inv_sev = _joined_investigations(frames)
    own_inv = inv_sev[inv_sev["cse_id"] == cse_id] if len(inv_sev) else inv_sev
    esc_sev = _joined_escalations(frames, inv_sev)
    own_esc = esc_sev[esc_sev["cse_id"] == cse_id] if len(esc_sev) else esc_sev

    own_a = _severity_counts(own_alerts)
    own_i = _severity_counts(own_inv)
    own_v = _severity_counts(own_inv, extra="evidence_entries")
    own_e = _severity_counts(own_esc)

    # Portfolio totals minus self = leave-self-out denominators.
    tot_a = _severity_counts(alerts)
    tot_i = _severity_counts(inv_sev)
    tot_v = _severity_counts(inv_sev, extra="evidence_entries")
    tot_e = _severity_counts(esc_sev)

    obs_a, obs_i = len(own_alerts), len(own_inv)
    obs_v = float(own_inv["evidence_entries"].fillna(0).sum()) \
        if len(own_inv) and "evidence_entries" in own_inv.columns else 0.0
    obs_e = len(own_esc)

    # --- expected alerts: leave-self-out size-band mean ---------------------
    exp_a = None
    if meta is not None and len(meta) and "size_band" in meta.columns:
        row = meta[meta["cse_id"] == cse_id]
        if len(row):
            band = row["size_band"].iloc[0]
            peers = alerts.merge(meta[["cse_id", "size_band"]], on="cse_id",
                                 how="left")
            peers = peers[peers["size_band"] == band]
            n_other = peers["cse_id"].nunique() - 1
            if n_other > 0:
                exp_a = (len(peers) - obs_a) / n_other

    # --- severity-conditioned expectations ----------------------------------
    exp_i = exp_v = exp_e = 0.0
    for s in SEVERITIES:
        other_a, other_i = tot_a[s] - own_a[s], tot_i[s] - own_i[s]
        if other_a > 0:
            exp_i += own_a[s] * (other_i / other_a)
        other_v = tot_v[s] - own_v[s]
        if other_i > 0:
            exp_v += own_i[s] * (other_v / other_i)
        other_e = tot_e[s] - own_e[s]
        if other_i > 0:
            exp_e += own_i[s] * (other_e / other_i)

    observed = {"alerts": float(obs_a), "investigations": float(obs_i),
                "evidence_entries": obs_v, "escalations": float(obs_e)}
    expected = {"alerts": exp_a, "investigations": exp_i,
                "evidence_entries": exp_v, "escalations": exp_e}

    table: Dict[str, Dict[str, Any]] = {}
    for dim in DIMENSIONS:
        mu, obs = expected[dim], observed[dim]
        entry: Dict[str, Any] = {
            _OBSERVED: _round(obs, 1),
            _EXPECTED: _round(mu, 1),
            _RATIO: _round(obs / mu) if mu and mu > 0 else None,
        }
        if mu and mu > 0:
            half = _band(mu, band_z, overdispersion)
            entry[_BAND_LOW] = _round(max(0.0, mu - half), 1)
            entry[_BAND_HIGH] = _round(mu + half, 1)
        else:
            entry[_BAND_LOW] = entry[_BAND_HIGH] = None
        table[dim] = entry
    return table


def build_evidence_model(frames: Dict[str, pd.DataFrame],
                         band_z: float = 3.0,
                         overdispersion: float = 0.001) \
        -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Full portfolio model: ``{cse_id: {dimension: table entry}}``."""
    alerts = frames.get("alerts")
    if alerts is None or not len(alerts):
        return {}
    return {
        cse_id: table
        for cse_id in sorted(alerts["cse_id"].dropna().unique())
        if (table := evidence_table_for(cse_id, frames,
                                        band_z=band_z,
                                        overdispersion=overdispersion))
    }
