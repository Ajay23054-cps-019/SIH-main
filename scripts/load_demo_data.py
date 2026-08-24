#!/usr/bin/env python
"""Load (or regenerate) the demo dataset into a SQLite DB for demos.

    python scripts/load_demo_data.py                    # data/sat_sa.db
    python scripts/load_demo_data.py --db demo.db --regenerate

Thin wrapper over scripts.run_pipeline: generates CSVs if missing, loads
them into the DB, profiles, detects, benchmarks and ranks — i.e. leaves
the store exactly as the dashboard and API expect to find it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_pipeline import DEFAULT_DATASET, DEFAULT_DB, main as pipeline_main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--regenerate", action="store_true",
                        help="Regenerate CSVs even if they exist")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    return pipeline_main([
        "--db", str(args.db),
        "--dataset-dir", str(args.dataset_dir),
        "--seed", str(args.seed),
    ] + (["--regenerate"] if args.regenerate else []))


if __name__ == "__main__":
    raise SystemExit(main())
