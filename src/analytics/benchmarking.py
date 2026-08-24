"""Peer benchmarking: rule-based groups, z-scores, percentile ranks.

Grouping is deliberately simple for the MVP — ``(sector, size_band)`` from
``cse_metadata`` — so an examiner can see exactly who a CSE is being
compared against. Every benchmark row persists its peer membership list,
and every printed/stored outlier carries that context: raw numbers are
meaningless without knowing the cohort behind them.

Statistics (documented because examiners must be able to recompute them):
- ``z_score = (value − peer_mean) / peer_std`` using the population std
  (ddof=0) over peers *excluding* the CSE itself.
- ``percentile`` is the mean rank of the CSE among peers+self, 0–100:
  ``100 × (below + 0.5 × tied) / n`` — ties split the difference.
- Zero-variance peer metrics yield ``z_score=None`` with an explanatory
  note instead of an infinite score; the percentile still applies.
- Groups whose member count (with profiles for the period) falls below
  ``min_group_size`` are reported but not scored.

Usage:
    python -m src.analytics.benchmarking run --cse-id CSE-042 --db data/sat_sa.db
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from src.analytics.profiles import PERIOD_ALL

# Defaults; override via thresholds file under the "benchmarking" section.
# ``min_group_size`` gates scoring a group at all; ``min_flag_peers`` is the
# tighter support a *flag* needs — calling something an outlier on the word
# of two peers is how false-positive storms start.
DEFAULT_BENCHMARKING = {
    "min_group_size": 3,
    "outlier_z": 2.5,
    "min_flag_peers": 3,
}

UNKNOWN = "Unknown"


def _benchmark_cfg(thresholds: Optional[Mapping[str, Any]] = None) \
        -> Dict[str, Any]:
    cfg = dict(DEFAULT_BENCHMARKING)
    if thresholds:
        cfg.update(thresholds.get("benchmarking") or {})
    return cfg


# ---------------------------------------------------------------------------
# Peer grouping
# ---------------------------------------------------------------------------


def _slug(text: Any) -> str:
    """'Power & Energy' -> 'Power_Energy'; blank/NaN -> 'Unknown'."""
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return UNKNOWN
    slug = re.sub(r"\W+", "_", str(text)).strip("_")
    return slug or UNKNOWN


def group_label(sector: Any, size_band: Any) -> str:
    return f"{_slug(sector)}_{_slug(size_band)}"


def normalize_metadata(metadata: Any) -> Dict[str, tuple]:
    """Coerce a metadata frame/mapping into ``{cse_id: (sector, band)}``.

    Missing or blank attributes degrade to ``("Unknown", "Unknown")`` rather
    than dropping the CSE — every entity must land in *some* peer group.
    """
    pairs: Dict[str, tuple] = {}
    if isinstance(metadata, pd.DataFrame):
        cols = set(metadata.columns)
        for _, row in metadata.iterrows():
            sector = row["sector"] if "sector" in cols else None
            band = row["size_band"] if "size_band" in cols else None
            pairs[str(row["cse_id"])] = (_clean_attr(sector),
                                         _clean_attr(band))
    elif isinstance(metadata, Mapping):
        for cse_id, attrs in metadata.items():
            if isinstance(attrs, (tuple, list)) and len(attrs) >= 2:
                pairs[str(cse_id)] = (_clean_attr(attrs[0]),
                                      _clean_attr(attrs[1]))
            else:
                pairs[str(cse_id)] = (UNKNOWN, UNKNOWN)
    else:
        raise TypeError(
            f"metadata must be a DataFrame or mapping, got {type(metadata)}")
    return pairs


def _clean_attr(value: Any) -> str:
    if value is None:
        return UNKNOWN
    try:
        if pd.isna(value):
            return UNKNOWN
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text else UNKNOWN


def build_peer_groups(metadata: Any) -> Dict[str, List[str]]:
    """Partition CSE IDs into ``(sector, size_band)`` groups."""
    groups: Dict[str, List[str]] = {}
    for cse_id, (sector, band) in normalize_metadata(metadata).items():
        groups.setdefault(group_label(sector, band), []).append(cse_id)
    return {label: sorted(members)
            for label, members in sorted(groups.items())}


# ---------------------------------------------------------------------------
# Per-metric benchmark
# ---------------------------------------------------------------------------


@dataclass
class MetricBenchmark:
    metric: str
    value: float
    n_peers: int
    peer_mean: float
    peer_median: float
    peer_std: float
    z_score: Optional[float]
    percentile: float
    is_outlier: bool = False
    note: Optional[str] = None


def percentile_rank(value: float, values: Sequence[float]) -> float:
    """Mean-rank percentile (0–100) of ``value`` among ``values`` (incl. self)."""
    below = sum(1 for v in values if v < value)
    tied = sum(1 for v in values if v == value)
    return 100.0 * (below + 0.5 * tied) / len(values)


def benchmark_metric(metric: str, value: float, peer_values: Sequence[float],
                     *, outlier_z: float = 2.5,
                     min_flag_peers: int = 3) -> Optional[MetricBenchmark]:
    """Compare one value against its peers; None when fewer than 2 peers."""
    peers = [float(v) for v in peer_values
             if v is not None and not pd.isna(v)]
    if len(peers) < 2:
        return None
    arr = np.asarray(peers, dtype=float)
    mean = float(arr.mean())
    median = float(np.median(arr))
    std = float(arr.std(ddof=0))

    pooled = peers + [float(value)]
    pct = percentile_rank(float(value), pooled)

    note = None
    if std > 0:
        z = (float(value) - mean) / std
        outlier = abs(z) > outlier_z and len(peers) >= min_flag_peers
        if abs(z) > outlier_z and not outlier:
            note = (f"|z| exceeds {outlier_z} but only {len(peers)} peers "
                    f"support it; outlier flag suppressed")
    else:
        z = None
        outlier = False
        note = ("peer values have zero variance; z-score undefined, "
                "percentile shown instead")
    return MetricBenchmark(
        metric=metric, value=float(value), n_peers=len(peers),
        peer_mean=round(mean, 6), peer_median=round(median, 6),
        peer_std=round(std, 6),
        z_score=None if z is None else round(z, 3),
        percentile=round(pct, 1), is_outlier=outlier, note=note,
    )


# ---------------------------------------------------------------------------
# Per-CSE benchmark
# ---------------------------------------------------------------------------


@dataclass
class CSEBenchmark:
    cse_id: str
    period: str
    sector: str
    size_band: str
    group_label: str
    peer_ids: List[str]
    benchmarks: List[MetricBenchmark] = field(default_factory=list)
    skipped: Dict[str, str] = field(default_factory=dict)

    @property
    def n_peers(self) -> int:
        return len(self.peer_ids)

    @property
    def usable(self) -> bool:
        return bool(self.benchmarks)

    @property
    def outliers(self) -> List[MetricBenchmark]:
        return [b for b in self.benchmarks if b.is_outlier]

    @property
    def group_definition(self) -> str:
        """Disclosure text: who the peers are. Required on any flagged CSE."""
        members = ", ".join(sorted([self.cse_id] + self.peer_ids))
        return (f"Peer group '{self.group_label}' ({self.n_peers} peers + "
                f"self, sector={self.sector}, size={self.size_band}): "
                f"{members}")

    def summary(self, max_metrics: Optional[int] = None) -> str:
        lines = [f"CSE {self.cse_id} — {self.group_definition}"]
        if not self.usable:
            reason = self.skipped.get("__all__", "insufficient peer coverage")
            lines.append(f"  Not benchmarked: {reason}")
            return "\n".join(lines)
        rows = self.benchmarks
        if max_metrics is not None:
            rows = rows[:max_metrics]
        for b in rows:
            z_text = "n/a" if b.z_score is None else f"z={b.z_score}"
            flag = " ← OUTLIER" if b.is_outlier else ""
            lines.append(f"Metric: {b.metric}")
            lines.append(f"  {self.cse_id}: {b.value} "
                         f"({z_text}, {b.percentile}th percentile){flag}")
            lines.append(f"  Peer mean: {b.peer_mean} | "
                         f"Peer median: {b.peer_median} | "
                         f"Peer std: {b.peer_std} (n={b.n_peers})")
            if b.note:
                lines.append(f"  Note: {b.note}")
        for metric, reason in self.skipped.items():
            if metric != "__all__":
                lines.append(f"Skipped {metric}: {reason}")
        return "\n".join(lines)


def benchmark_cse(
    cse_id: str,
    profiles: Iterable[Any],
    metadata: Any,
    *,
    period: str = PERIOD_ALL,
    thresholds: Optional[Mapping[str, Any]] = None,
) -> CSEBenchmark:
    """Benchmark one CSE's profile metrics against its (sector, size) peers."""
    cfg = _benchmark_cfg(thresholds)
    min_group = int(cfg["min_group_size"])
    outlier_z = float(cfg["outlier_z"])
    min_flag_peers = int(cfg.get("min_flag_peers", 3))

    pairs = normalize_metadata(metadata)
    sector, band = pairs.get(cse_id, (UNKNOWN, UNKNOWN))
    label = group_label(sector, band)
    member_ids = {cid for cid, ab in pairs.items() if group_label(*ab) == label}

    prof_list = list(profiles)
    target = next((p for p in prof_list
                   if p.cse_id == cse_id and p.period == period), None)
    peer_profiles = sorted(
        (p for p in prof_list
         if p.cse_id != cse_id and p.period == period
         and p.cse_id in member_ids),
        key=lambda p: p.cse_id,
    )
    peer_ids = [p.cse_id for p in peer_profiles]

    bench = CSEBenchmark(cse_id=cse_id, period=period, sector=sector,
                         size_band=band, group_label=label, peer_ids=peer_ids)
    if target is None:
        bench.skipped["__all__"] = f"no profile for period {period}"
        return bench

    total = len(peer_profiles) + 1
    if total < min_group:
        bench.skipped["__all__"] = (
            f"peer group too small ({total} member(s) with profiles; "
            f"minimum {min_group})")
        return bench

    for metric, value in target.scalar_metrics.items():
        peer_vals = [p.metrics.get(metric) for p in peer_profiles]
        covered = [v for v in peer_vals if v is not None]
        if len(covered) < 2:
            bench.skipped[metric] = (
                f"only {len(covered)} peer(s) report this metric")
            continue
        mb = benchmark_metric(metric, float(value), covered,
                              outlier_z=outlier_z,
                              min_flag_peers=min_flag_peers)
        assert mb is not None  # guarded above
        if mb.n_peers < 5:
            mb.note = "; ".join(
                filter(None, [mb.note,
                              f"small peer set (n={mb.n_peers}); "
                              f"z-scores are noisy"]))
        bench.benchmarks.append(mb)
    return bench


def build_all_benchmarks(
    profiles: Iterable[Any],
    metadata: Any,
    *,
    periods: Sequence[str] = (PERIOD_ALL,),
    thresholds: Optional[Mapping[str, Any]] = None,
) -> List[CSEBenchmark]:
    """Benchmark every CSE appearing in ``profiles`` for each period."""
    prof_list = list(profiles)
    ids = sorted({p.cse_id for p in prof_list})
    out: List[CSEBenchmark] = []
    for period in periods:
        for cse_id in ids:
            out.append(benchmark_cse(cse_id, prof_list, metadata,
                                     period=period, thresholds=thresholds))
    return out


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

BENCHMARKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS peer_benchmarks (
    cse_id TEXT NOT NULL,
    period TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL,
    peer_group_label TEXT,
    n_peers INTEGER,
    peer_mean REAL,
    peer_median REAL,
    peer_std REAL,
    z_score REAL,
    percentile REAL,
    is_outlier INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    peer_members_json TEXT,
    created_at TEXT,
    PRIMARY KEY (cse_id, period, metric)
)
"""


def store_benchmarks(benchmarks: Iterable[CSEBenchmark],
                     db_path: Path) -> int:
    """Upsert benchmark rows; clears each CSE's previous rows first."""
    from sqlalchemy import text

    from src.storage.db import get_engine

    engine = get_engine(db_path)
    rows_written = 0
    created_at = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(text(BENCHMARKS_TABLE_SQL))
        seen_periods: Dict[str, str] = {}
        for b in benchmarks:
            seen_periods.setdefault(b.cse_id, b.period)
        for cse_id, period in seen_periods.items():
            conn.execute(
                text("DELETE FROM peer_benchmarks "
                     "WHERE cse_id = :cse_id AND period = :period"),
                {"cse_id": cse_id, "period": period},
            )
        for b in benchmarks:
            for mb in b.benchmarks:
                conn.execute(text(
                    "INSERT OR REPLACE INTO peer_benchmarks "
                    "(cse_id, period, metric, value, peer_group_label, "
                    " n_peers, peer_mean, peer_median, peer_std, z_score, "
                    " percentile, is_outlier, note, peer_members_json, "
                    " created_at) VALUES "
                    "(:cse_id, :period, :metric, :value, :label, :n_peers, "
                    " :peer_mean, :peer_median, :peer_std, :z_score, "
                    " :percentile, :is_outlier, :note, :members, :created_at)"
                ), {
                    "cse_id": b.cse_id, "period": b.period,
                    "metric": mb.metric, "value": mb.value,
                    "label": b.group_label, "n_peers": mb.n_peers,
                    "peer_mean": mb.peer_mean, "peer_median": mb.peer_median,
                    "peer_std": mb.peer_std, "z_score": mb.z_score,
                    "percentile": mb.percentile,
                    "is_outlier": int(mb.is_outlier), "note": mb.note,
                    "members": json.dumps(sorted([b.cse_id] + b.peer_ids)),
                    "created_at": created_at,
                })
                rows_written += 1
    return rows_written


def load_benchmarks(db_path: Path,
                    cse_id: Optional[str] = None,
                    period: Optional[str] = None,
                    outliers_only: bool = False) -> pd.DataFrame:
    """Read stored benchmarks; empty frame when the table does not exist yet."""
    from sqlalchemy import text

    from src.storage.db import get_engine

    clauses, params = [], {}
    if cse_id:
        clauses.append("cse_id = :cse_id")
        params["cse_id"] = cse_id
    if period:
        clauses.append("period = :period")
        params["period"] = period
    if outliers_only:
        clauses.append("is_outlier = 1")
    query = "SELECT * FROM peer_benchmarks"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY cse_id, metric"
    engine = get_engine(db_path)
    try:
        return pd.read_sql(text(query), engine, params=params)
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_inputs(db_path: Path, period: str):
    from src.analytics.profiler import load_profiles
    from src.analytics.profiler import rows_to_profiles
    from src.storage.db import load_table

    profile_rows = load_profiles(db_path)
    profiles = rows_to_profiles(profile_rows)
    profiles = [p for p in profiles if p.period == period]
    try:
        metadata = load_table("cse_metadata", db_path)
    except Exception:
        metadata = pd.DataFrame(columns=["cse_id", "sector", "size_band"])
    return profiles, metadata


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="benchmarking", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Benchmark a CSE or the portfolio")
    run.add_argument("--cse-id", default=None,
                     help="one CSE; omit for a portfolio-wide summary")
    run.add_argument("--period", default=PERIOD_ALL)
    run.add_argument("--db", "--profiles", dest="db", type=Path,
                     default=Path("data/sat_sa.db"))
    args = parser.parse_args(argv)

    profiles, metadata = _load_inputs(args.db, args.period)
    if args.cse_id:
        if not any(p.cse_id == args.cse_id for p in profiles):
            print(f"No profile for {args.cse_id} in period {args.period} "
                  f"at {args.db}. Run the profiler first.")
            return 1
        bench = benchmark_cse(args.cse_id, profiles, metadata,
                              period=args.period)
        print(bench.summary())
        return 0

    benches = build_all_benchmarks(profiles, metadata, periods=[args.period])
    if not benches:
        print(f"No profiles for period {args.period} at {args.db}.")
        return 1
    store_benchmarks(benches, args.db)
    print(f"Benchmarked {len(benches)} CSEs for period {args.period}; "
          f"rows stored in peer_benchmarks.\n")
    for bench in benches:
        if not bench.usable:
            print(f"{bench.cse_id}: not benchmarked "
                  f"({bench.skipped.get('__all__', '?')})")
            continue
        flags = ", ".join(b.metric for b in bench.outliers) or "none"
        print(f"{bench.cse_id} [{bench.group_label}] "
              f"outliers: {flags}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
