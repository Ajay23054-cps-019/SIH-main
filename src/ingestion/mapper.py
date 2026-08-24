"""Column-name mapping for heterogeneous CSE submissions.

Real CSEs will never agree on column names. This module maps the variants we
anticipate onto canonical schema fields, in two passes:

1. **Generic pass** (before entity is known): unambiguous aliases only.
2. **Entity-specific pass** (after the primary key identifies the entity):
   riskier aliases such as ``id`` or ``type`` that mean different things in
   different tables.

Defaults live here; ``data/config/column_mappings.json`` can extend them
without code changes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

# Canonical key -> accepted variants (normalized: lowercase, spaces/hyphens -> _)
GENERIC_MAPPINGS: Dict[str, List[str]] = {
    # Primary keys
    "cse_id": ["cse_id", "cse", "entity_id", "organisation_id", "organization_id"],
    "alert_id": ["alert_id", "alert_uuid", "alert_ref"],
    "investigation_id": ["investigation_id", "investigation_uuid", "case_work_id"],
    "escalation_id": ["escalation_id", "escalation_uuid"],
    "case_id": ["case_id", "case_uuid"],
    "asset_id": ["asset_id", "asset_uuid"],
    # Common fields
    "timestamp": ["timestamp", "created_at", "created_time", "alert_time", "event_time"],
    "severity": ["severity"],
    "closure_timestamp": ["closure_timestamp", "closed_at", "closed_time", "resolved_at"],
    "status": ["status"],
    "sector": ["sector", "industry", "vertical"],
    "size_band": ["size_band", "size_tier"],
}

PER_ENTITY_MAPPINGS: Dict[str, Dict[str, List[str]]] = {
    "alerts": {
        "alert_id": ["alert_id", "alert_uuid", "id", "event_id", "eventid", "ref"],
        "severity": ["severity", "priority", "level", "severity_level", "sev"],
        "category": ["category", "type", "alert_type", "category_name", "signature"],
        "asset_id": ["asset_id", "asset", "system_id", "host_id", "host", "device_id"],
        "status": ["status", "state", "alert_status"],
        "description": ["description", "message", "msg", "summary", "details"],
    },
    "investigations": {
        "investigation_id": ["investigation_id", "inv_id", "id", "work_id"],
        "evidence_entries": ["evidence_entries", "evidence_count", "num_evidence", "artifacts"],
        "assigned_to": ["assigned_to", "assignee", "analyst", "owner"],
        "notes": ["notes", "note", "comments", "comment", "notes_text"],
        "depth_score": ["depth_score", "depth", "quality_score"],
        "timestamp_open": ["timestamp_open", "opened_at", "open_time", "start_time"],
        "timestamp_close": ["timestamp_close", "closed_at", "close_time", "end_time",
                             "completed_at"],
    },
    "escalations": {
        "escalation_id": ["escalation_id", "esc_id", "id"],
        "decision": ["decision", "action", "decision_type", "outcome"],
        "has_followup": ["has_followup", "followup", "follow_up", "followed_up"],
        "recipient": ["recipient", "sent_to", "escalated_to", "forwarded_to"],
        "rationale": ["rationale", "reason", "justification", "explanation"],
    },
    "cases": {
        "case_id": ["case_id", "case", "incident_id", "id"],
        "related_alerts": ["related_alerts", "alert_ids", "linked_alerts", "alerts"],
        "case_type": ["case_type", "type", "incident_type"],
        "resolution": ["resolution", "resolution_text", "outcome", "result"],
        "closure_time": ["closure_time", "closure_timestamp", "closed_at"],
    },
    "assets": {
        "asset_id": ["asset_id", "asset", "host_id", "system_id", "device_id", "id"],
        "asset_type": ["asset_type", "type", "asset_class", "device_type"],
        "criticality": ["criticality", "criticality_level", "business_criticality"],
        "environment": ["environment", "env", "tier"],
        "monitoring_status": ["monitoring_status", "monitored", "coverage_status",
                               "monitoring"],
    },
    "cse_metadata": {
        "name": ["name", "cse_name", "organization", "organisation", "org_name"],
        "claimed_capabilities": ["claimed_capabilities", "capabilities", "claims",
                                  "declared_capabilities"],
        "submitted_at": ["submitted_at", "submission_date", "submitted_on"],
    },
}

CONFIG_PATH = Path("data/config/column_mappings.json")

_NORMALIZE_RE = re.compile(r"[\s\-]+")


def normalize_key(key: str) -> str:
    """Lowercase and canonicalize a raw column name for lookup."""
    return _NORMALIZE_RE.sub("_", str(key).strip().lower())


def load_mappings(config_path: Path = CONFIG_PATH) -> tuple[dict, dict]:
    """Return (generic, per_entity) mappings, extended by JSON config if present.

    Config format::

        {
          "generic": {"severity": ["importance"]},
          "per_entity": {"alerts": {"category": ["class"]}}
        }

    Extra variants are appended to the built-in lists (config cannot remove
    defaults, keeping behaviour predictable).
    """
    generic = {k: list(v) for k, v in GENERIC_MAPPINGS.items()}
    per_entity = {e: {k: list(v) for k, v in m.items()} for e, m in PER_ENTITY_MAPPINGS.items()}

    if config_path.exists():
        cfg = json.loads(config_path.read_text())
        for canon, variants in cfg.get("generic", {}).items():
            generic.setdefault(canon, []).extend(variants)
        for entity, mapping in cfg.get("per_entity", {}).items():
            for canon, variants in mapping.items():
                per_entity.setdefault(entity, {}).setdefault(canon, []).extend(variants)
    return generic, per_entity


def build_reverse_map(mapping: Dict[str, List[str]]) -> Dict[str, str]:
    """variant -> canonical. First-listed variant wins on conflicts."""
    reverse: Dict[str, str] = {}
    for canon, variants in mapping.items():
        if normalize_key(canon) not in reverse:
            reverse[normalize_key(canon)] = canon
        for v in variants:
            nv = normalize_key(v)
            reverse.setdefault(nv, canon)
    return reverse


class ColumnMapper:
    """Two-pass mapper: generic rename → entity inference → entity-specific rename."""

    def __init__(self, config_path: Path = CONFIG_PATH):
        generic, per_entity = load_mappings(config_path)
        self._generic_reverse = build_reverse_map(generic)
        self._per_entity_reverse = {
            e: build_reverse_map(m) for e, m in per_entity.items()
        }
        # Union view for entity inference: a key counts as a canonical field
        # if ANY entity's schema recognizes it.
        self._union_reverse = dict(self._generic_reverse)
        for rev in self._per_entity_reverse.values():
            for variant, canon in rev.items():
                self._union_reverse.setdefault(variant, canon)
        self.unknown_columns: set[str] = set()

    @property
    def known_keys(self) -> set[str]:
        return set(self._generic_reverse) | {
            k for m in self._per_entity_reverse.values() for k in m
        }

    def map_record(self, record: dict, entity: Optional[str] = None) -> dict:
        """Rename keys to canonical names. Unknown columns are preserved
        as-is (Pydantic ignores extras) and recorded as schema mismatches."""
        mapped: dict = {}
        for key, value in record.items():
            nk = normalize_key(key)
            canonical = self._generic_reverse.get(nk)
            if canonical is None and entity is not None:
                canonical = self._per_entity_reverse.get(entity, {}).get(nk)
            if canonical is not None:
                mapped[canonical] = value
            else:
                self.unknown_columns.add(nk)
                mapped[key] = value  # keep original name; ignored downstream
        return mapped

    def infer_entity(self, record: dict) -> Optional[str]:
        """Identify entity type from its primary-key columns.

        Checked most-specific-first so linked IDs (e.g. an escalation row also
        carrying investigation_id) resolve correctly.
        """
        keys = {normalize_key(k) for k in record}
        # Map raw keys through the union of all schemas so aliases count too.
        mapped_keys = {self._union_reverse.get(nk, nk) for nk in keys}

        checks = [
            ("escalations", "escalation_id"),
            ("investigations", "investigation_id"),
            ("cases", "case_id"),
            ("alerts", "alert_id"),
            ("assets", "asset_id"),
        ]
        for entity, pk in checks:
            if pk in mapped_keys:
                return entity
        if "cse_id" in mapped_keys:
            return "cse_metadata"
        return None
