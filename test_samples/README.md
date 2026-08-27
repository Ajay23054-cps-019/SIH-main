# Test Sample Data

This folder contains sample CSE data files for testing SAT-SA's upload and analysis capabilities.

## Directory Structure

```
test_samples/
├── my_cse_data/           # Standard CSV format (5 alerts)
│   ├── cse_metadata.csv
│   ├── alerts.csv
│   ├── investigations.csv
│   ├── escalations.csv
│   ├── cases.csv
│   └── assets.csv
├── another_cse/           # Different column names (7 alerts)
│   ├── cse_metadata.csv   # Uses "id" instead of "cse_id"
│   ├── alerts.csv         # Uses "EventID", "priority", "type"
│   ├── investigations.csv # Uses "id", "evidence_count"
│   └── assets.csv         # Uses "system_id", "env", "monitoring"
└── json_format/           # JSON format
    └── alerts.json
```

## Sample 1: my_cse_data (Standard Format)

**Purpose:** Test standard CSV upload with all entity types.

**CSE:** MY-CSE-001 (Telecom, Medium)

**Expected Findings:**
- `shallow_justification` — AL-001, AL-002, AL-005 closed with minimal notes ("Checked. Benign.")
- `template_notes` — Multiple identical notes detected
- `superficial_closure` — AL-002 (CRITICAL) closed in 1 minute

**Notes Quality:**
- AL-001: "Checked. Benign." (shallow)
- AL-002: "Checked." (shallow)
- AL-003: Detailed technical analysis (deep)
- AL-004: Moderate detail (medium)
- AL-005: "Checked." (shallow)

## Sample 2: another_cse (Different Column Names)

**Purpose:** Test column name mapping/heterogeneous format support.

**CSE:** ORG-002 (Financial Services, Large)

**Column Mappings Tested:**
| Our Column | Their Column |
|------------|--------------|
| alert_id | EventID |
| severity | priority |
| category | type |
| asset_id | system_id |
| timestamp | created_time |
| evidence_entries | evidence_count |
| assigned_to | analyst |

**Expected Findings:**
- `shallow_justification` — EVT-001, EVT-002, EVT-005, EVT-006
- `template_notes` — "Checked." repeated
- `closure_velocity_outlier` — EVT-001, EVT-006 (CRITICAL closed in 1 minute)

## Sample 3: json_format (JSON Upload)

**Purpose:** Test JSON format ingestion.

**CSE:** JSON-CSE

**Expected Findings:**
- Basic profiling (alert volume, severity distribution)
- Limited signals (no investigation notes provided)

## How to Test

### Via Dashboard
1. Start the app: `python scripts/demo.py`
2. Open http://localhost:8000/dashboard/
3. Use the upload panel at the top of the portfolio page
4. Select entity type → Choose file → Upload
5. Refresh dashboard to see new CSE in rankings

### Via API
```bash
# Upload alerts
curl -X POST http://localhost:8000/api/ingest/upload \
  -F "file=@test_samples/my_cse_data/alerts.csv" \
  -F "entity=alerts" \
  -F "format=csv"

# Upload investigations
curl -X POST http://localhost:8000/api/ingest/upload \
  -F "file=@test_samples/my_cse_data/investigations.csv" \
  -F "entity=investigations" \
  -F "format=csv"

# Check findings
curl http://localhost:8000/api/findings?cse_id=MY-CSE-001
```

### Via Python
```python
from src.ingestion.pipeline import IngestionPipeline

pipeline = IngestionPipeline("data/sat_sa.db")
result = pipeline.ingest_file("test_samples/my_cse_data/alerts.csv", "alerts", "csv")
print(f"Ingested {result.records_ingested} records")
```

## Validation Checklist

- [ ] Upload my_cse_data → CSE appears in portfolio rankings
- [ ] Upload another_cse → Column mapping works correctly
- [ ] Upload json_format → JSON parsing works
- [ ] shallow_justification fires for MY-CSE-001
- [ ] template_notes fires for MY-CSE-001
- [ ] Report generation works for uploaded CSEs
- [ ] Feedback can be submitted on findings

---

*Created: 2026-08-27*
