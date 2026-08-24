"""Normalize raw mapped records into canonical Pydantic models.

Conversion failures (bad timestamps, impossible orderings, malformed JSON
payloads in JSON-typed columns) are *collected*, not raised — a single bad
row must never abort a 100K-record submission. The quality layer reports
what was rejected and why.
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from pydantic import ValidationError

from src.analytics.schemas import (
    Alert,
    Asset,
    Case,
    CSEMetadata,
    Dataset,
    Escalation,
    Investigation,
)

ENTITY_MODELS = {
    "cse_metadata": CSEMetadata,
    "alerts": Alert,
    "investigations": Investigation,
    "escalations": Escalation,
    "cases": Case,
    "assets": Asset,
}


def _maybe_json(value: Any) -> Any:
    """Decode JSON-encoded strings for list/dict typed fields."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in ("[", "{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value  # let the model validator / quality layer flag it
    return value


def _nan_to_none(value: Any) -> Any:
    """Empty CSV cells arrive as NaN/pd.NA — canonical schema wants None."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if value is pd.NA:
        return None
    return value


def _preprocess(entity: str, record: dict) -> dict:
    record = {k: _nan_to_none(v) for k, v in record.items()}
    # Drop adapter-internal error markers so they don't leak into models.
    record.pop("__parse_error__", None)
    if entity == "cases":
        record["related_alerts"] = _maybe_json(record.get("related_alerts"))
    elif entity == "cse_metadata":
        record["claimed_capabilities"] = _maybe_json(record.get("claimed_capabilities"))
    return record


def normalize_records(
    entity: str, records: List[dict], source: str = ""
) -> Tuple[List[Any], List[dict]]:
    """Convert raw records to canonical models.

    Returns ``(valid_models, rejections)`` where each rejection is
    ``{"entity", "index", "source", "error"}``.
    """
    model_cls = ENTITY_MODELS.get(entity)
    if model_cls is None:
        return [], [{"entity": entity, "index": i, "source": source,
                     "error": "unknown entity type"} for i in range(len(records))]

    valid: List[Any] = []
    rejections: List[dict] = []
    for idx, raw in enumerate(records):
        try:
            valid.append(model_cls(**_preprocess(entity, raw)))
        except ValidationError as exc:
            rejections.append({
                "entity": entity,
                "index": idx,
                "source": source,
                "error": exc.errors(include_url=False, include_context=False),
            })
        except (TypeError, ValueError) as exc:
            rejections.append({
                "entity": entity,
                "index": idx,
                "source": source,
                "error": str(exc),
            })
    return valid, rejections


def build_dataset(
    buckets: Dict[str, List[Any]], cse_id_hint: Optional[str] = None
) -> Dataset:
    """Assemble normalized models into a Dataset container."""
    return Dataset(
        cse_metadata=buckets.get("cse_metadata", []),
        alerts=buckets.get("alerts", []),
        investigations=buckets.get("investigations", []),
        escalations=buckets.get("escalations", []),
        cases=buckets.get("cases", []),
        assets=buckets.get("assets", []),
    )
