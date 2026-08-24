"""Ingestion pipeline: parse → map → normalize → quality-check → (store).

Usage:
    python -m src.ingestion.pipeline ingest data/samples/demo_dataset/ --db data/sat_sa.db
    python -m src.ingestion.pipeline quality data/samples/demo_dataset/
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.analytics.schemas import Dataset
from src.ingestion.adapters import (
    SUPPORTED_SUFFIXES,
    BaseAdapter,
    ParseError,
    get_adapter,
)
from src.ingestion.mapper import ColumnMapper
from src.ingestion.normalizer import normalize_records
from src.ingestion.quality import DataQualityReport, assess_quality


@dataclass
class IngestionResult:
    dataset: Dataset
    frames: Dict[str, pd.DataFrame]
    records_ingested: int
    records_rejected: int
    quality_score: float
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    files_processed: int = 0
    files_skipped: int = 0


def _iter_submission_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    return sorted(
        p for p in path.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )


def ingest_path(path: Path, mapper: Optional[ColumnMapper] = None) -> IngestionResult:
    """Ingest a single file or a directory of submissions."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    mapper = mapper or ColumnMapper()
    all_frames: Dict[str, pd.DataFrame] = {}
    rejections: List[dict] = []
    errors: List[str] = []
    ingested = rejected = processed = skipped = 0

    for file_path in _iter_submission_files(path):
        adapter: BaseAdapter = get_adapter(file_path)
        try:
            buckets_raw = adapter.parse(file_path, mapper.infer_entity)
        except ParseError as exc:
            errors.append(str(exc))
            skipped += 1
            continue
        processed += 1

        for entity, raw_records in buckets_raw.items():
            mapped = [mapper.map_record(rec, entity=entity) for rec in raw_records]
            valid_models, rej = normalize_records(entity, mapped, source=file_path.name)
            rejections.extend(rej)
            rejected += len(rej)
            ingested += len(valid_models)
            if valid_models:
                rows = [m.model_dump(mode="python") for m in valid_models]
                df = pd.DataFrame(rows)
                frame = all_frames.get(entity)
                all_frames[entity] = pd.concat([frame, df], ignore_index=True) \
                    if frame is not None else df

    report: DataQualityReport = assess_quality(all_frames, rejections, mapper.unknown_columns)
    dataset = _frames_to_dataset(all_frames)

    return IngestionResult(
        dataset=dataset,
        frames=all_frames,
        records_ingested=ingested,
        records_rejected=rejected,
        quality_score=report.overall_score(),
        warnings=report.warnings(),
        errors=errors,
        files_processed=processed,
        files_skipped=skipped,
    )


def _frames_to_dataset(frames: Dict[str, pd.DataFrame]) -> Dataset:
    """Rebuild the canonical Dataset container from per-entity frames.

    Rows are re-validated through the Pydantic models, so anything stored or
    served downstream is guaranteed schema-conformant.
    """
    from src.analytics.schemas import (
        Alert, Asset, Case, CSEMetadata, Escalation, Investigation,
    )

    def _clean(value):
        # pd.isna on list/dict values returns arrays; leave containers as-is.
        if isinstance(value, (list, dict)):
            return value
        return None if pd.isna(value) else value

    def _records(frame, model_cls):
        if frame is None or not len(frame):
            return []
        return [
            model_cls(**{k: _clean(v) for k, v in rec.items()})
            for rec in frame.to_dict(orient="records")
        ]

    return Dataset(
        cse_metadata=_records(frames.get("cse_metadata"), CSEMetadata),
        alerts=_records(frames.get("alerts"), Alert),
        investigations=_records(frames.get("investigations"), Investigation),
        escalations=_records(frames.get("escalations"), Escalation),
        cases=_records(frames.get("cases"), Case),
        assets=_records(frames.get("assets"), Asset),
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="ingest", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Ingest submissions into SQLite")
    p_ingest.add_argument("path", type=Path)
    p_ingest.add_argument("--db", type=Path, default=Path("data/sat_sa.db"))

    p_quality = sub.add_parser("quality", help="Score submission quality only")
    p_quality.add_argument("path", type=Path)

    args = parser.parse_args(argv)

    start = time.perf_counter()
    result = ingest_path(args.path)
    elapsed = time.perf_counter() - start

    print(f"Files processed : {result.files_processed} "
          f"(skipped {result.files_skipped})")
    print(f"Records ingested: {result.records_ingested:,}")
    print(f"Records rejected: {result.records_rejected:,}")
    print(f"Quality score   : {result.quality_score:.2f}")
    print(f"Ingestion time  : {elapsed:.1f}s")
    if result.warnings:
        print("\nWarnings:")
        for w in result.warnings[:15]:
            print(f"  - {w}")

    if args.command == "ingest":
        from src.storage.db import save_frames
        save_frames(result.frames, args.db)
        print(f"\nStored to {args.db}: "
              + ", ".join(f"{k}={len(v):,}" for k, v in sorted(result.frames.items())))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
