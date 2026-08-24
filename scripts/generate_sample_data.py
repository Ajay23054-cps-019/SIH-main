#!/usr/bin/env python
"""CLI entry point for the synthetic SOC dataset generator.

Usage:
    python scripts/generate_sample_data.py [--output DIR] [--seed N]
                                           [--cses N] [--force]

Writes six CSV files (cse_metadata, alerts, investigations, escalations,
cases, assets) into the output directory. Defaults to data/samples/demo_dataset/.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from src.analytics.sample_data import generate_dataset  # noqa: E402

DEFAULT_OUTPUT = Path("data/samples/demo_dataset")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cses", type=int, default=None,
                        help="Generate only the first N CSEs (smoke testing)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing dataset")
    args = parser.parse_args()

    if args.output.exists() and any(args.output.iterdir()) and not args.force:
        print(f"Refusing to overwrite non-empty {args.output} (use --force)")
        return 1

    start = time.perf_counter()
    frames = generate_dataset(seed=args.seed, n_cses=args.cses)

    args.output.mkdir(parents=True, exist_ok=True)
    for name, df in frames.items():
        path = args.output / f"{name}.csv"
        df.to_csv(path, index=False)
        print(f"{path}: {len(df):>8,} records")

    elapsed = time.perf_counter() - start
    print(f"\nDone in {elapsed:.1f}s (seed={args.seed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
