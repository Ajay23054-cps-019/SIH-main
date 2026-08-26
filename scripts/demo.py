#!/usr/bin/env python3
"""One-command demo launcher for SIH judging.

    python scripts/demo.py

Does everything needed to go from zero to a running demo:
1. Regenerates synthetic data (deterministic seed 42)
2. Runs the full pipeline (ingest → profile → signals → benchmarks → ranking)
3. Prints the validation summary
4. Starts the FastAPI server (Ctrl+C to stop)

The dashboard is then live at http://localhost:8000/dashboard/
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.run_pipeline import run_pipeline, print_report  # noqa: E402


def main() -> int:
    print("=" * 60)
    print("SAT-SA Demo Launcher")
    print("=" * 60)
    print()

    print("[1/2] Running full pipeline on 50 CSEs ...")
    summary = run_pipeline(regenerate=True, seed=42)
    ok = print_report(summary)
    print()

    print("[2/2] Starting FastAPI server ...")
    print("      Dashboard: http://localhost:8000/dashboard/")
    print("      API docs:  http://localhost:8000/docs")
    print("      Press Ctrl+C to stop")
    print()

    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "src.api.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
        ])
    except KeyboardInterrupt:
        print("\nServer stopped.")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
