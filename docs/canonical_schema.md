# Canonical Schema Reference

All CSE submissions are normalized into the Pydantic models in
`src/analytics/schemas.py` before any analytics run.

## Design Rules

1. **Missing data is `None`** — never empty strings, `-1`, or sentinel values.
2. **Partial submissions are valid** — every entity list in `Dataset` defaults
   to empty; analytics must handle absent tables gracefully.
3. **Normalization, not rejection** — severities are upper-cased and alias-mapped
   (`crit` → `CRITICAL`); unknown values pass through for the quality layer to flag.
   The only hard failures are impossible timestamp orderings (close before open)
   and negative counts.
4. **Referential integrity is a quality issue** — broken alert↔investigation links
   are logged by the ingestion quality layer, not raised here.

## Entity Models

### CSEMetadata

| Field | Type | Notes |
|-------|------|-------|
| `cse_id` | str (required) | Entity identifier |
| `name` | str? | |
| `sector` | str? | Telecom, Financial, Power, ... |
| `size_band` | str? | Small, Medium, Large |
| `claimed_capabilities` | dict? | Free-form claims (e.g., EDR coverage) |
| `submitted_at` | datetime? | Submission timestamp |

### Alert

| Field | Type | Notes |
|-------|------|-------|
| `alert_id` | str (required) | |
| `cse_id` | str (required) | |
| `timestamp` | datetime? | Alert creation time |
| `severity` | str? | CRITICAL / HIGH / MEDIUM / LOW (normalized) |
| `category` | str? | malware, authentication, network, endpoint, database, ... |
| `asset_id` | str? | FK → Asset |
| `status` | str? | open / investigating / escalated / closed |
| `closure_timestamp` | datetime? | Must be ≥ `timestamp` |
| `description` | str? | |

### Investigation

| Field | Type | Notes |
|-------|------|-------|
| `investigation_id` | str (required) | |
| `alert_id` | str? | FK → Alert |
| `cse_id` | str? | Denormalized for convenience; may be missing |
| `timestamp_open` | datetime? | |
| `timestamp_close` | datetime? | Must be ≥ `timestamp_open` |
| `evidence_entries` | int (≥0, default 0) | Depth proxy |
| `assigned_to` | str? | Analyst identifier |
| `notes` | str? | Free text; input to template-detection signal |
| `depth_score` | float? | Optional pre-computed depth |

### Escalation

| Field | Type | Notes |
|-------|------|-------|
| `escalation_id` | str (required) | |
| `investigation_id` | str? | FK → Investigation |
| `cse_id` | str? | |
| `timestamp` | datetime? | |
| `decision` | str? | escalated / not_escalated / escalated_with_action |
| `has_followup` | bool (default False) | Follow-through evidence present |
| `recipient` | str? | |
| `rationale` | str? | |

### Case

| Field | Type | Notes |
|-------|------|-------|
| `case_id` | str (required) | |
| `related_alerts` | list[str] (default []) | FKs → Alerts |
| `cse_id` | str? | |
| `case_type` | str? | |
| `severity` | str? | Normalized like Alert.severity |
| `closure_time` | datetime? | |
| `resolution` | str? | |

### Asset

| Field | Type | Notes |
|-------|------|-------|
| `asset_id` | str (required) | |
| `cse_id` | str (required) | |
| `asset_type` | str? | server, endpoint, network_device, database |
| `criticality` | str? | Normalized like severity |
| `environment` | str? | production, staging, development |
| `monitoring_status` | str? | monitored, partially_monitored, unmonitored |

## Dataset Container

`Dataset` holds lists of all six entity types and provides:

- `to_pandas() -> Dict[str, pd.DataFrame]` — one DataFrame per entity type;
  empty entity lists yield zero-row frames (keys always present).
- `summary() -> Dict[str, int]` — record counts per entity type.

## Quick Validation

```bash
./venv/bin/python - <<'EOF'
from src.analytics.schemas import Alert, Dataset
a = Alert(alert_id='A1', cse_id='CSE-001', severity='crit')
d = Dataset(alerts=[a])
print(d.summary())
print(d.to_pandas()['alerts'].shape)
EOF
```
