#!/usr/bin/env python
"""One-command end-to-end pipeline (Phase 12).

    python scripts/run_pipeline.py [--db data/sat_sa.db] [--regenerate]

Flow: ensure demo CSVs exist -> load into SQLite -> profile -> detect
signals -> peer benchmarks -> attention ranking -> verify the eight seeded
weaknesses are detected. Safe to re-run: entity tables are replaced and
derived tables are cleared before rebuild, so results never duplicate.

Exit code 0 means the pipeline ran AND every acceptance check passed.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

DEFAULT_DB = Path("data/sat_sa.db")
DEFAULT_DATASET = Path("data/samples/demo_dataset")

ENTITY_TYPES = ("cse_metadata", "alerts", "investigations",
                "escalations", "cases", "assets")

# Datetime columns the profiler expects as real timestamps (CSV round-trips
# turn them back into strings, so they must be parsed on load).
PARSE_DATES = {
    "alerts": ["timestamp", "closure_timestamp"],
    "investigations": ["timestamp_open", "timestamp_close"],
    "escalations": ["timestamp"],
    "cse_metadata": [],
    "cases": ["closure_time"],
    "assets": [],
}


def generate_if_missing(dataset_dir: Path, seed: int,
                        n_cses: Optional[int] = None) -> Path:
    """Generate the demo CSVs unless they already exist."""
    if dataset_dir.exists() and any(dataset_dir.glob("*.csv")):
        return dataset_dir
    from src.analytics.sample_data import generate_dataset

    print(f"[data] generating synthetic portfolio into {dataset_dir} "
          f"(seed={seed}) ...")
    start = time.perf_counter()
    frames = generate_dataset(seed=seed, n_cses=n_cses)
    dataset_dir.mkdir(parents=True, exist_ok=True)
    for name, df in frames.items():
        df.to_csv(dataset_dir / f"{name}.csv", index=False)
    print(f"[data] wrote {len(frames)} files in "
          f"{time.perf_counter() - start:.1f}s")
    return dataset_dir


def read_frames(dataset_dir: Path) -> Dict[str, pd.DataFrame]:
    """Read the six entity CSVs with profiler-friendly dtypes."""
    frames = {}
    for name in ENTITY_TYPES:
        path = dataset_dir / f"{name}.csv"
        if not path.exists():
            raise FileNotFoundError(f"missing {path}; run with --regenerate")
        frames[name] = pd.read_csv(path, parse_dates=PARSE_DATES.get(name, []))
    return frames


def clear_derived(db_path: Path) -> None:
    """Wipe derived tables so a smaller re-run cannot leave stale rows.

    Creates each table if missing (fresh-DB runs hit this path first).
    """
    from sqlalchemy import text

    from src.analytics.benchmarking import BENCHMARKS_TABLE_SQL
    from src.analytics.profiler import PROFILES_TABLE_SQL
    from src.analytics.scoring import SCORES_TABLE_SQL
    from src.storage.db import get_engine

    with get_engine(db_path).begin() as conn:
        for create_sql in (PROFILES_TABLE_SQL, BENCHMARKS_TABLE_SQL,
                           SCORES_TABLE_SQL):
            conn.execute(text(create_sql))
        for table in ("behavioral_profiles", "peer_benchmarks",
                      "attention_scores"):
            conn.execute(text(f"DELETE FROM {table}"))


def run_pipeline(db_path: Path = DEFAULT_DB,
                 dataset_dir: Path = DEFAULT_DATASET,
                 regenerate: bool = False, seed: int = 42,
                 n_cses: Optional[int] = None) -> Dict[str, Any]:
    """Ingest -> profile -> signals -> benchmarks -> ranking -> checks.

    Returns a summary dict; ``summary["checks"]`` carries the seeded-
    weakness verification used by both the printed report and tests.
    """
    from src.analytics.benchmarking import build_all_benchmarks, \
        store_benchmarks
    from src.analytics.finding import load_thresholds
    from src.analytics.profiler import compute_all_profiles, store_profiles
    from src.analytics.sample_data import expected_seed_signals
    from src.analytics.scoring import compute_attention_scores, rank_scores, \
        store_scores
    from src.analytics.signal_engine import run_signals
    from src.ingestion.quality import assess_quality
    from src.storage.db import save_frames

    thresholds = load_thresholds()

    if regenerate:
        import shutil

        if dataset_dir.exists():
            shutil.rmtree(dataset_dir)

    started = time.perf_counter()

    # 1-2. Ensure + ingest -------------------------------------------------
    dataset_dir = generate_if_missing(dataset_dir, seed=seed, n_cses=n_cses)
    print(f"[ingest] loading {dataset_dir} -> {db_path}")
    frames = read_frames(dataset_dir)
    total_records = sum(len(df) for df in frames.values())
    report = assess_quality(frames, rejections=[], unknown_columns=set())
    save_frames(frames, db_path, if_exists="replace")
    clear_derived(db_path)
    print(f"[ingest] {total_records:,} records, data quality "
          f"{report.overall_score():.0%}")

    # 3. Profile ------------------------------------------------------------
    print("[profile] computing behavioral profiles ...")
    profiles = compute_all_profiles(frames)
    store_profiles(profiles, db_path)
    print(f"[profile] {len(profiles)} profiles "
          f"(x{len({p.period for p in profiles})} periods)")

    # 4. Signals ------------------------------------------------------------
    print("[signals] running detection engine ...")
    findings = run_signals(db_path, thresholds=thresholds)
    flagged = sorted({f.cse_id for f in findings})
    print(f"[signals] {len(findings)} findings across {len(flagged)} CSEs")

    # 5. Benchmarks ----------------------------------------------------------
    print("[peers] sector x size benchmarking ...")
    benches = build_all_benchmarks(profiles, frames["cse_metadata"],
                                   thresholds=thresholds)
    n_bench_rows = store_benchmarks(benches, db_path)
    n_outliers = sum(len(b.outliers) for b in benches if b.usable)
    print(f"[peers] {n_bench_rows} metric comparisons, "
          f"{n_outliers} outlier flags")

    # 6. Attention ranking ----------------------------------------------------
    all_ids = frames["cse_metadata"]["cse_id"].astype(str).tolist()
    ranked = rank_scores(compute_attention_scores(
        findings, all_cse_ids=all_ids, thresholds=thresholds))
    store_scores(ranked, db_path)
    print("[rank] top of the review queue:")
    for s in ranked[:10]:
        marker = " *" if s.cse_id in expected_seed_signals() else ""
        print(f"    {s.cse_id}: {s.priority:5.1f}"
              f" ({s.n_findings} findings){marker}")
    print("    (* seeded weakness; priority is review ordering, "
          "NOT a risk or compliance score)")

    # Acceptance checks -------------------------------------------------------
    # Only enforced for seeded CSEs actually present in this dataset, so
    # --cses smoke runs are not failed by design.
    fired: Dict[str, set] = {}
    for f in findings:
        fired.setdefault(f.cse_id, set()).add(f.signal_type)
    wanted_all = expected_seed_signals()
    checks = []
    for cse_id, wanted in wanted_all.items():
        if cse_id not in all_ids:
            continue
        missing = wanted - fired.get(cse_id, set())
        checks.append({"cse_id": cse_id, "expected": sorted(wanted),
                       "missing": sorted(missing), "ok": not missing})
    rank_positions = {s.cse_id: i + 1 for i, s in enumerate(ranked)}
    top10_seeded = [c for c in wanted_all if c in all_ids
                    and rank_positions.get(c, 10 ** 9) <= 10]
    n_applicable = sum(1 for c in wanted_all if c in all_ids)
    checks.append({
        "check": "seeded_cses_in_top10",
        "found": top10_seeded, "count": len(top10_seeded),
        "applicable": n_applicable,
        "ok": len(top10_seeded) == n_applicable,
    })

    elapsed = time.perf_counter() - started
    return {
        "db_path": str(db_path), "elapsed_s": round(elapsed, 1),
        "records": total_records, "quality": report.overall_score(),
        "profiles": len(profiles), "findings": len(findings),
        "flagged_cses": len(flagged), "benchmark_rows": n_bench_rows,
        "outlier_flags": n_outliers,
        "scores_stored": len(ranked),
        "checks": checks,
    }


def print_report(summary: Dict[str, Any]) -> bool:
    """Print the acceptance table; True when everything passed."""
    ok_all = True
    print("\nSeeded-weakness detection:")
    for check in summary["checks"]:
        if "expected" in check:
            state = "PASS" if check["ok"] else "FAIL"
            print(f"  [{state}] {check['cse_id']}: "
                  f"{', '.join(check['expected'])}")
            if not check["ok"]:
                ok_all = False
                print(f"         missing: {', '.join(check['missing'])}")
        else:
            state = "PASS" if check["ok"] else "FAIL"
            print(f"  [{state}] seeded CSEs in top-10 ranks: "
                  f"{check['count']}")
            if not check["ok"]:
                ok_all = False

    print(f"\nDone in {summary['elapsed_s']}s — dashboard: "
          f"uvicorn src.api.main:app then open /dashboard/")
    return ok_all


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="SQLite target (default: %(default)s)")
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--regenerate", action="store_true",
                        help="Discard existing CSVs and regenerate")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cses", type=int, default=None,
                        help="Shrink to N CSEs (smoke runs; skips strict "
                             "acceptance)")
    args = parser.parse_args(argv)

    summary = run_pipeline(args.db, args.dataset_dir,
                           regenerate=args.regenerate, seed=args.seed,
                           n_cses=args.cses)
    ok = print_report(summary)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
