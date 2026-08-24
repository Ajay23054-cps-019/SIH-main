"""Format adapters: parse CSV / JSON / JSONL submissions into raw records.

An adapter turns one file into ``dict[str, list[dict]]`` — entity type → raw
records — without interpreting field names (that is the mapper's job) or
types (that is the normalizer's job).
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List

import pandas as pd


class ParseError(Exception):
    """Raised when a file cannot be read at all (vs. per-record issues)."""


class BaseAdapter(ABC):
    format_name: str = "abstract"

    @abstractmethod
    def load_rows(self, path: Path) -> List[dict]:
        """Read the file into a flat list of raw record dicts."""

    def parse(self, path: Path, infer_entity) -> Dict[str, List[dict]]:
        """Load rows, bucket them by inferred entity type.

        ``infer_entity`` is a callable(dict) -> Optional[str] supplied by the
        pipeline (it needs the column mapper). Records with no identifiable
        entity land in the ``"unknown"`` bucket.
        """
        buckets: Dict[str, List[dict]] = {}
        for row in self.load_rows(path):
            if not isinstance(row, dict):
                row = {"value": row}
            entity = infer_entity(row) or "unknown"
            buckets.setdefault(entity, []).append(row)
        return buckets


class CsvAdapter(BaseAdapter):
    format_name = "csv"

    def load_rows(self, path: Path) -> List[dict]:
        try:
            df = pd.read_csv(path)
        except Exception as exc:  # unreadable file is a hard error
            raise ParseError(f"CSV parse failed for {path}: {exc}") from exc
        return df.to_dict(orient="records")


class JsonAdapter(BaseAdapter):
    """Handles flat lists, nested dicts keyed by entity, and single objects."""

    format_name = "json"

    def load_rows(self, path: Path) -> List[dict]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ParseError(f"JSON parse failed for {path}: {exc}") from exc
        return self._flatten(payload)

    def _flatten(self, payload) -> List[dict]:
        # Unwrap one level of common envelope keys.
        if isinstance(payload, dict) and set(payload) <= {"data", "records", "items"} \
                and isinstance(list(payload.values())[0], (list, dict)):
            payload = next(iter(payload.values()))

        if isinstance(payload, list):
            return [r for r in payload if isinstance(r, dict)]
        if isinstance(payload, dict):
            # Entity-keyed: {"alerts": [...], "assets": [...]}
            if payload and all(isinstance(v, list) for v in payload.values()):
                rows: List[dict] = []
                for records in payload.values():
                    rows.extend(r for r in records if isinstance(r, dict))
                return rows
            return [payload]
        raise ParseError("JSON payload must be an object, list, or entity-keyed map")


class JsonlAdapter(BaseAdapter):
    format_name = "jsonl"

    def load_rows(self, path: Path) -> List[dict]:
        rows: List[dict] = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                # One malformed line should not kill a large submission.
                rows.append({"__parse_error__": f"line {line_no}: {exc}"})
                continue
            if isinstance(obj, dict):
                rows.append(obj)
        return rows


ADAPTERS_BY_SUFFIX = {
    ".csv": CsvAdapter,
    ".json": JsonAdapter,
    ".jsonl": JsonlAdapter,
    ".ndjson": JsonlAdapter,
}

SUPPORTED_SUFFIXES = tuple(ADAPTERS_BY_SUFFIX)


def get_adapter(path: Path) -> BaseAdapter:
    adapter_cls = ADAPTERS_BY_SUFFIX.get(path.suffix.lower())
    if adapter_cls is None:
        raise ParseError(f"Unsupported format '{path.suffix}' for {path}")
    return adapter_cls()
