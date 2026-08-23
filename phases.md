# SAT-SA Implementation Phases

**Project:** SAT-SA — Supervisory Analytics Tool for SOC Assessment  
**Competition:** Smart India Hackathon 2026 · SIH26157 · NCIIPC  
**Purpose:** Step-by-step implementation guide from scratch to full system  
**Status:** Living Document

---

## How to Use This Document

Each phase is a **self-contained unit of work** with:
- **Goal:** What the phase achieves
- **Why it matters:** How it contributes to the overall system
- **What to create:** Exact files, modules, and components
- **Where to put it:** Directory structure guidance
- **Dependencies:** What must exist before starting
- **Implementation requirements:** Specific technical details
- **Acceptance criteria:** How to know the phase is complete
- **Validation:** Commands to verify it works
- **Expected output:** What the phase produces
- **Risks/caveats:** Known issues and mitigations

Follow phases in order. Each phase builds on the previous one.

---

## Technology Stack (Final)

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Language** | Python 3.9+ | Team familiarity, offline-first, rich analytics ecosystem |
| **Backend** | FastAPI | Auto-generated docs, async support, easy local deployment |
| **Validation** | Pydantic | Schema enforcement, data quality, serialization |
| **Analytics** | Pandas / Polars + NumPy + SciPy | Statistical analysis, profiling, transformation |
| **ML (optional)** | scikit-learn | Only where genuinely useful (clustering, anomaly detection) |
| **Database** | SQLite (MVP) | Zero-config, file-based, fully local |
| **Future DB** | PostgreSQL | Documented for production, NOT required for MVP |
| **Frontend** | FastAPI + Jinja2 + vanilla JS + Chart.js | No Node.js, no React, lightweight, offline |
| **LLM (optional)** | Ollama or equivalent local runtime | Explanation layer only, not required |
| **Testing** | pytest | Industry standard, good fixtures |
| **Deployment** | Python venv + uvicorn | No Docker required, works with `python -m venv` |

**Explicitly excluded from MVP:**
- React / Node.js / npm
- Docker (optional convenience only)
- Redis
- PostgreSQL (documented for future, not required)
- Cloud services
- External APIs
- Microservices
- Kubernetes

---

## Canonical Data Schema

All ingestion formats (CSV, JSON, JSONL, structured TXT) are normalized into this schema before analytics run.

### CSE Metadata

```python
class CSEMetadata(BaseModel):
    cse_id: str
    name: Optional[str] = None
    sector: Optional[str] = None  # Telecom, Financial, Power, etc.
    size_band: Optional[str] = None  # Small, Medium, Large
    claimed_capabilities: Optional[Dict[str, Any]] = None
    submitted_at: Optional[datetime] = None
```

### Alert

```python
class Alert(BaseModel):
    alert_id: str
    cse_id: str
    timestamp: Optional[datetime] = None
    severity: Optional[str] = None  # CRITICAL, HIGH, MEDIUM, LOW
    category: Optional[str] = None  # malware, authentication, network, endpoint, database
    asset_id: Optional[str] = None
    status: Optional[str] = None  # open, investigating, escalated, closed
    closure_timestamp: Optional[datetime] = None
    description: Optional[str] = None
```

### Investigation

```python
class Investigation(BaseModel):
    investigation_id: str
    alert_id: Optional[str] = None
    cse_id: Optional[str] = None
    timestamp_open: Optional[datetime] = None
    timestamp_close: Optional[datetime] = None
    evidence_entries: int = 0
    assigned_to: Optional[str] = None
    notes: Optional[str] = None
    depth_score: Optional[float] = None
```

### Escalation

```python
class Escalation(BaseModel):
    escalation_id: str
    investigation_id: Optional[str] = None
    cse_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    decision: Optional[str] = None  # escalated, not_escalated, escalated_with_action
    has_followup: bool = False
    recipient: Optional[str] = None
    rationale: Optional[str] = None
```

### Case

```python
class Case(BaseModel):
    case_id: str
    related_alerts: List[str] = []
    cse_id: Optional[str] = None
    case_type: Optional[str] = None
    severity: Optional[str] = None
    closure_time: Optional[datetime] = None
    resolution: Optional[str] = None
```

### Asset

```python
class Asset(BaseModel):
    asset_id: str
    cse_id: str
    asset_type: Optional[str] = None  # server, endpoint, network_device, database
    criticality: Optional[str] = None  # CRITICAL, HIGH, MEDIUM, LOW
    environment: Optional[str] = None  # production, staging, development
    monitoring_status: Optional[str] = None  # monitored, partially_monitored, unmonitored
```

### Design Principles

- **Nullable fields:** Every field is optional. Missing data is represented as `None`, not as empty strings or sentinel values.
- **No assumptions:** Analytics must handle cases where entire tables are missing (e.g., no investigation records).
- **Forward compatibility:** Raw JSON blobs stored alongside normalized fields for future analysis.
- **Referential integrity:** IDs are strings; broken links are logged as data-quality issues, not crashes.

---

## Phase 0: Project Bootstrap

**Goal:** Establish the foundational project structure and local development environment.

### Why It Matters

Without a clean foundation, later phases accumulate technical debt. This phase ensures the project runs with standard Python tooling and has clear conventions from day one.

### What to Create

| Item | Path | Purpose |
|------|------|---------|
| Project root | `/home/ajay/Desktop/SIH/` | All code lives here |
| `README.md` | `/home/ajay/Desktop/SIH/README.md` | Project overview (keep updated) |
| `plan.md` | `/home/ajay/Desktop/SIH/plan.md` | Implementation plan (keep updated) |
| `Product.md` | `/home/ajay/Desktop/SIH/Product.md` | Product definition (keep updated) |
| `MVP.md` | `/home/ajay/Desktop/SIH/MVP.md` | MVP scope (keep updated) |
| `phases.md` | `/home/ajay/Desktop/SIH/phases.md` | This file |
| `.gitignore` | `/home/ajay/Desktop/SIH/.gitignore` | Exclude venv, __pycache__, .env, *.db |
| `requirements.txt` | `/home/ajay/Desktop/SIH/requirements.txt` | Python dependencies |
| `.env.example` | `/home/ajay/Desktop/SIH/.env.example` | Environment variable template |
| `Makefile` | `/home/ajay/Desktop/SIH/Makefile` | Common commands (setup, test, run) |

### Directory Structure to Create

```
SIH/
├── src/
│   ├── ingestion/          # Format adapters, validation, normalization
│   │   ├── adapters.py     # CSV, JSON, JSONL, TXT parsers
│   │   ├── normalizer.py   # Canonical schema transformation
│   │   ├── quality.py      # Data quality assessment
│   │   └── pipeline.py     # Ingestion orchestrator
│   ├── analytics/          # Supervisory analytics engines
│   │   ├── profiler.py     # Behavioral profile extraction
│   │   ├── execution_gaps.py
│   │   ├── negative_space.py
│   │   ├── behavioral_anomalies.py
│   │   ├── benchmarking.py
│   │   ├── scoring.py      # Supervisory attention score
│   │   ├── expected_evidence.py  # Advanced, post-MVP core
│   │   └── config.py       # Threshold loader
│   ├── evidence/           # Finding construction and evidence tracing
│   │   ├── tracer.py       # Evidence chain builder
│   │   ├── findings.py     # Finding data structures
│   │   └── reporter.py     # Report generation
│   ├── api/                # FastAPI backend
│   │   ├── main.py         # App factory
│   │   ├── routes.py       # Endpoints
│   │   ├── models.py       # Pydantic request/response models
│   │   └── errors.py       # Error handlers
│   └── dashboard/          # Jinja2 + vanilla JS frontend
│       ├── templates/      # Jinja2 HTML templates
│       ├── static/         # CSS, JS, images
│       └── routes.py       # Dashboard page routes
├── data/
│   ├── schemas/            # Canonical schema definitions
│   │   └── canonical_schema.py
│   ├── samples/            # Sample CSE datasets for demonstration
│   │   ├── generate_sample_data.py
│   │   └── demo_dataset/
│   └── config/             # Analytics thresholds, peer group definitions
│       ├── thresholds.json
│       └── peer_groups.json
├── tests/                  # Unit and integration tests
│   ├── conftest.py
│   ├── test_ingestion.py
│   ├── test_profiler.py
│   ├── test_execution_gaps.py
│   ├── test_negative_space.py
│   ├── test_benchmarking.py
│   └── test_api.py
├── docs/                   # Additional documentation
├── scripts/                # Utility scripts
│   ├── generate_sample_data.py
│   ├── run_analytics.py
│   └── offline_install.sh  # Optional air-gap helper
├── requirements.txt
├── .env.example
└── Makefile
```

### Implementation Requirements

1. **Python 3.9+** required
2. **Virtual environment** managed via `venv`
3. **`Makefile`** targets: `setup`, `test`, `run`, `lint`, `format`
4. **`.gitignore`** excludes: `venv/`, `__pycache__/`, `*.db`, `.env`, `*.pyc`, `.pytest_cache/`, `data/samples/*.csv`
5. **`requirements.txt`** pinned versions for reproducibility

### `requirements.txt` Contents

```
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
pydantic>=2.0.0
pandas>=2.0.0
numpy>=1.24.0
scipy>=1.10.0
scikit-learn>=1.3.0  # optional, post-MVP core
sqlalchemy>=2.0.0
aiosqlite>=0.19.0    # async SQLite
python-dotenv>=1.0.0
pytest>=7.4.0
pytest-asyncio>=0.21.0
jinja2>=3.1.0
python-multipart>=0.0.6  # for file uploads
chart.js-py  # or use CDN in templates
# Optional:
# ollama>=0.1.0  # local LLM explanation layer
```

### Dependencies

None. This is the starting point.

### Acceptance Criteria

- [ ] `make setup` creates virtual environment and installs dependencies without errors
- [ ] `make test` runs pytest and all tests pass
- [ ] `make run` starts uvicorn and `curl http://localhost:8000/health` returns 200 OK
- [ ] Directory structure matches specification above
- [ ] `.gitignore` excludes sensitive/temporary files

### Validation Commands

```bash
make setup
make test
make run
curl http://localhost:8000/health
```

### Expected Output

- Working FastAPI app at `http://localhost:8000`
- `/health` endpoint returning `{"status": "ok"}`
- All tests passing

### Risks/Caveats

- If team uses Windows, adjust Makefile commands accordingly
- If Python version conflicts arise, use `pyenv` or conda

---

## Phase 1: Canonical Data Schema

**Goal:** Define the internal data structures that all analytics operate on.

### Why It Matters

Analytics must not depend on input format quirks. A canonical schema decouples ingestion from analysis and makes the system format-agnostic.

### What to Create

| Item | Path | Purpose |
|------|------|---------|
| Schema module | `src/analytics/schemas.py` | Pydantic models for all entities |
| Schema documentation | `docs/canonical_schema.md` | Field definitions, types, constraints |
| Quality rules | `src/ingestion/quality.py` | Data quality checks |

### Implementation Requirements

1. Define Pydantic models for: `CSEMetadata`, `Alert`, `Investigation`, `Escalation`, `Case`, `Asset`
2. Every field must be `Optional` with explicit `None` defaults
3. Add validators for: timestamp ordering (open < close), severity enum, status enum
4. Define a `Dataset` container that holds lists of all entity types
5. Add `to_dataframe()` methods for Pandas/Polars conversion
6. Document required vs optional fields per entity type

### Acceptance Criteria

- [ ] All Pydantic models validate correctly with sample data
- [ ] Models accept missing fields without crashing
- [ ] Timestamp validators reject impossible dates
- [ ] `Dataset.to_dataframe()` returns clean DataFrames
- [ ] Schema documentation complete

### Validation Commands

```bash
python -c "from src.analytics.schemas import Alert, Dataset; a = Alert(alert_id='A1', cse_id='C1'); print(a)"
python -c "from src.analytics.schemas import Dataset; d = Dataset(alerts=[], investigations=[]); print(d.to_dataframe())"
```

### Expected Output

- `src/analytics/schemas.py` with 7 Pydantic models
- `docs/canonical_schema.md` with field reference

---

## Phase 2: Synthetic SOC Dataset Generator

**Goal:** Create a realistic synthetic data generator with seeded supervisory weaknesses.

### Why It Matters

Real CSE data is unavailable during the hackathon. Synthetic data lets the team control exactly which weaknesses are present, ensuring the demo is reliable and repeatable.

### What to Create

| Item | Path | Purpose |
|------|------|---------|
| Generator module | `src/analytics/sample_data.py` | Core generation logic |
| Generator CLI | `scripts/generate_sample_data.py` | Command-line entry point |
| Demo dataset | `data/samples/demo_dataset/` | Pre-generated files |
| Generator config | `data/config/sample_params.json` | Tunable parameters |

### Data to Generate

1. **CSE metadata** — 50 CSEs, 3 sectors, 3 size bands
2. **Assets** — 200–500 assets per CSE with realistic criticality distribution
3. **Alerts** — ~500 alerts/CSE/quarter × 4 quarters = ~100K total
4. **Investigations** — 80–95% of alerts have investigations with realistic depth
5. **Escalations** — 10–20% of investigations escalate, with follow-through evidence
6. **Cases** — Linked to alerts and investigations

### Seeded Weaknesses (8 CSEs)

| CSE ID | Weakness Category | Seeding Strategy |
|--------|------------------|-----------------|
| CSE-042 | Execution gap: investigation degradation | 70% decline in evidence_entries over 4 quarters, change-point in Q3 |
| CSE-017 | Execution gap: superficial closures + no escalation | Fast closure + shallow depth + 0% critical escalation |
| CSE-089 | Negative space: missing telemetry | 0 endpoint alerts despite 500+ endpoints in inventory |
| CSE-031 | Negative space: missing investigations | 95% of HIGH/CRITICAL alerts lack investigation records |
| CSE-055 | Peer deviation: closure velocity | 3σ faster closure than peer median |
| CSE-073 | Behavioral anomaly: temporal pattern | 0 escalations on weekends |
| CSE-019 | Behavioral anomaly: templated investigations | 90%+ lexical similarity in investigation notes |
| CSE-061 | Execution gap + negative space | Multiple combined weaknesses |

### Implementation Requirements

1. Use `numpy.random.Generator` with explicit seeds for reproducibility
2. Generate correlations: high-severity alerts → longer investigations → higher escalation rates
3. Asset criticality influences alert severity distribution
4. Temporal patterns: diurnal cycles, weekday/weekend differences
5. Each CSE has a `scenario` parameter controlling its behavior profile
6. Output as CSV with UTF-8 encoding, one file per entity type

### Acceptance Criteria

- [ ] Generator produces 6 CSV files in `data/samples/demo_dataset/`
- [ ] All 8 seeded weaknesses are detectable by the analytics engine
- [ ] Running generator twice with same seed produces identical output
- [ ] Total records: ~100K alerts, ~80K investigations, ~10K escalations
- [ ] Generation completes in <30 seconds

### Validation Commands

```bash
python scripts/generate_sample_data.py --output data/samples/demo_dataset/ --seed 42
wc -l data/samples/demo_dataset/*.csv
```

### Expected Output

```
data/samples/demo_dataset/
├── cse_metadata.csv
├── alerts.csv
├── investigations.csv
├── escalations.csv
├── cases.csv
└── assets.csv
```

### Risks/Caveats

- Synthetic data will never fully match real CSE submissions
- Seeded weaknesses must be discoverable without hardcoding CSE IDs in detection logic

---

## Phase 3: Format-Agnostic Ingestion Layer

**Goal:** Build adapters that ingest CSV, JSON, JSONL, and structured TXT into the canonical schema.

### Why It Matters

NCIIPC does not control CSE submission formats. The ingestion layer must be flexible enough to handle heterogeneous inputs without changing analytics code.

### What to Create

| Item | Path | Purpose |
|------|------|---------|
| Adapter interface | `src/ingestion/adapters.py` | Base adapter class |
| CSV adapter | `src/ingestion/adapters.py` | CSV parser |
| JSON adapter | `src/ingestion/adapters.py` | JSON/JSONL parser |
| TXT adapter | `src/ingestion/adapters.py` | Structured text parser |
| Column mapper | `src/ingestion/mapper.py` | Heterogeneous column name mapping |
| Normalizer | `src/ingestion/normalizer.py` | Transform to canonical schema |
| Pipeline | `src/ingestion/pipeline.py` | Orchestrate ingestion |
| Quality assessor | `src/ingestion/quality.py` | Data quality scoring |
| Tests | `tests/test_ingestion.py` | Unit tests |

### Adapter Design

```python
class BaseAdapter(ABC):
    @abstractmethod
    def parse(self, file_path: str) -> Dict[str, List[Dict]]:
        """Return dict of entity_type -> list of raw records."""
        pass
    
    @abstractmethod
    def validate(self, raw: Dict[str, List[Dict]]) -> ValidationReport:
        """Check required columns, types, referential integrity."""
        pass
```

### Column Mapping Strategy

Handle common naming variations:

```python
COLUMN_MAPPINGS = {
    "alert_id": ["alert_id", "id", "alert_uuid", "event_id", "EventID"],
    "timestamp": ["timestamp", "created_time", "alert_time", "created_at", "time"],
    "severity": ["severity", "priority", "level", "severity_level"],
    "asset_id": ["asset_id", "asset", "system_id", "host_id"],
    # ... extend as needed
}
```

### Data Quality Assessment

Before analytics run, compute a quality score:

```python
class DataQualityReport:
    def __init__(self, dataset: Dataset):
        self.total_alerts = len(dataset.alerts)
        self.missing_timestamps = sum(1 for a in dataset.alerts if a.timestamp is None)
        self.missing_severity = sum(1 for a in dataset.alerts if a.severity is None)
        self.missing_asset_id = sum(1 for a in dataset.alerts if a.asset_id is None)
        self.orphan_investigations = ...  # investigations without parent alert
        self.orphan_escalations = ...    # escalations without parent investigation
        self.schema_mismatches = ...     # unexpected column names
    
    def overall_score(self) -> float:
        """0.0 (unusable) to 1.0 (clean)."""
        ...
    
    def warnings(self) -> List[str]:
        """List of data-quality concerns."""
        ...
```

### Implementation Requirements

1. Each adapter returns a `Dict[str, List[Dict]]` mapping entity type to raw records
2. Normalizer converts raw dicts to canonical Pydantic models
3. Failed conversions are logged as data-quality issues, not crashes
4. Pipeline returns `IngestionResult` with: records ingested, quality score, warnings, errors
5. Column mapper is configurable via JSON (not hardcoded)

### Acceptance Criteria

- [ ] CSV adapter parses sample CSV files
- [ ] JSON adapter parses nested and flat JSON
- [ ] JSONL adapter parses line-delimited JSON
- [ ] Normalizer produces valid canonical models
- [ ] Quality score computed (0.0–1.0)
- [ ] Warnings list includes missing fields, orphans, schema mismatches
- [ ] 85%+ test coverage

### Validation Commands

```bash
python -m src.ingestion.pipeline ingest data/samples/demo_dataset/alerts.csv --format csv --cse-id CSE-042
python -m src.ingestion.pipeline quality data/samples/demo_dataset/ --cse-id CSE-042
```

### Expected Output

- `IngestionResult` with `records_ingested`, `quality_score`, `warnings`, `errors`
- SQLite database populated with normalized records

### Risks/Caveats

- Real CSE data may have unexpected column names; keep column mapping configurable
- Large files (>100MB) may require chunked reading

---

## Phase 4: Behavioral Profiling

**Goal:** Compute per-CSE behavioral profiles from normalized data.

### Why It Matters

Profiles transform raw records into metrics that supervisory analytics can compare across entities and time periods.

### What to Create

| Item | Path | Purpose |
|------|------|---------|
| Profiler | `src/analytics/profiler.py` | Core profiling logic |
| Profile model | `src/analytics/profiles.py` | Profile data structures |
| Profile API | `src/api/routes.py` | Endpoints |
| Tests | `tests/test_profiler.py` | Unit tests |

### Profile Dimensions

**Alert Metrics:**
- `alert_volume_total`, `alert_volume_per_day`
- `severity_distribution` (counts and percentages)
- `category_distribution`
- `alert_density` (alerts per monitored asset)

**Investigation Metrics:**
- `investigation_rate` (% of alerts with investigations)
- `investigation_depth_mean`, `investigation_depth_median`
- `investigation_duration_mean`, `p50`, `p90`
- `closure_velocity_mean`, `closure_velocity_by_severity`

**Escalation Metrics:**
- `escalation_rate`
- `escalation_rate_by_severity`
- `escalation_followthrough_rate`
- `escalation_appropriateness` (critical alerts escalated)

**Evidence Completeness:**
- `evidence_completeness_score` (0.0–1.0)
- `missing_required_fields` list

**Temporal Patterns:**
- `diurnal_distribution` (hour-of-day)
- `weekly_distribution` (day-of-week)
- `quiet_period_count` (gaps > threshold)

**Quality Trends:**
- `investigation_depth_trend` (quarter-over-quarter)
- `escalation_rate_trend`
- `closure_velocity_trend`

### Implementation Requirements

1. All metrics computed with Pandas groupby/aggregation
2. Handle missing data gracefully: if investigations table is empty, `investigation_rate = 0.0` with warning
3. Return `BehavioralProfile` dataclass per CSE per period
4. Store profiles in SQLite for later retrieval
5. Profiles must be serializable to JSON for API responses

### Acceptance Criteria

- [ ] Profiles computed for all 50 CSEs across 4 quarters
- [ ] Profile includes 20+ metrics
- [ ] Profiles stored in SQLite
- [ ] API endpoint returns profile JSON
- [ ] Handles missing investigation/escalation data without crashing
- [ ] 85%+ test coverage

### Validation Commands

```bash
python -m src.analytics.profiler run --input data/samples/demo_dataset/ --output data/profiles.db
python -c "from src.analytics.profiler import get_profile; print(get_profile('CSE-042', '2024-Q1'))"
```

### Expected Output

- SQLite database with `behavioral_profiles` table
- JSON profile per CSE per quarter

### Risks/Caveats

- If data is sparse, some metrics will have high variance; always include confidence intervals where possible

---

## Phase 5: Supervisory Signal Engine

**Goal:** Implement detection logic for execution gaps, negative space, behavioral anomalies, and peer deviation.

### Why It Matters

This is the core differentiator. The signal engine transforms profiles into actionable supervisory findings.

### Signal Categories

#### 5a. Execution Gaps

Patterns where claimed/expected behavior diverges from observed evidence.

| Signal | Description | Required Data |
|--------|-------------|---------------|
| `superficial_closure` | Fast closure + shallow investigation | Alerts, investigations, timestamps |
| `escalation_without_action` | Escalation logged but no follow-through | Escalations, investigations |
| `quality_degradation` | Investigation depth declining over time | Investigations across multiple periods |
| `severity_mismatch` | High-severity alerts closed as benign without investigation | Alerts, investigations, closure reasons |
| `template_investigation` | Investigation notes are highly repetitive | Investigations with notes field |

#### 5b. Negative Space

Absence of expected evidence.

| Signal | Description | Required Data |
|--------|-------------|---------------|
| `alert_volume_gap` | Expected alerts vs. observed (based on assets) | Alerts, assets |
| `missing_investigations` | High-severity alerts without investigation records | Alerts, investigations |
| `missing_alert_categories` | Expected alert types absent | Alerts, asset inventory |
| `telemetry_absence` | Critical assets producing no alerts | Alerts, assets |
| `escalation_absence` | Alerts meeting criteria but not escalated | Alerts, escalations |

#### 5c. Behavioral Anomalies

Unusual temporal or operational patterns.

| Signal | Description | Required Data |
|--------|-------------|---------------|
| `temporal_drift` | Sudden change in investigation depth or closure velocity | Profiles across periods |
| `unusual_quiet_period` | No alerts during expected active hours | Alerts with timestamps |
| `bulk_closure_pattern` | Mass closures on specific days/times | Alerts with closure timestamps |
| `shift_variance` | Quality differs significantly across shifts | Investigations with timestamps |
| `recurring_incident` | Same alert pattern repeats without resolution | Alerts, cases |

#### 5d. Peer Deviation

Statistically unusual behavior compared to peers.

| Signal | Description | Required Data |
|--------|-------------|---------------|
| `closure_velocity_outlier` | Closure speed significantly different from peer median | Profiles, peer group |
| `investigation_depth_outlier` | Investigation depth significantly different | Profiles, peer group |
| `escalation_rate_outlier` | Escalation rate significantly different | Profiles, peer group |

### Implementation Requirements

1. Each signal is a function: `detect_<signal_name>(cse_id, profiles, dataset, config) -> Optional[Finding]`
2. Signals return `None` if data is insufficient or quality is too low
3. Every `Finding` includes: `finding_id`, `cse_id`, `signal_type`, `severity`, `confidence`, `evidence`, `contributing_record_ids`, `detection_logic`, `caveats`, `recommended_actions`
4. Configurable thresholds loaded from `data/config/thresholds.json`
5. No signal uses hardcoded "NCIIPC standard" values

### Finding Data Structure

```python
@dataclass
class Finding:
    finding_id: str
    cse_id: str
    signal_type: str
    signal_category: str  # execution_gap, negative_space, behavioral_anomaly, peer_deviation
    severity: str  # HIGH, MEDIUM, LOW
    confidence: float  # 0.0–1.0
    evidence: Dict[str, Any]  # Quantitative backing
    contributing_record_ids: List[str]
    detection_logic: str  # Human-readable explanation
    caveats: List[str]
    recommended_actions: List[str]
    data_quality_notes: List[str]  # What data was missing
    created_at: datetime
```

### Acceptance Criteria

- [ ] All 15+ signals implemented as pure functions
- [ ] Each signal handles missing data gracefully (returns `None` with logged warning)
- [ ] Seeded weaknesses detected in demo dataset
- [ ] Configurable thresholds loaded from JSON
- [ ] Every finding includes data-quality notes
- [ ] 85%+ test coverage

### Validation Commands

```bash
python -m src.analytics.execution_gaps run --cse-id CSE-042 --profiles data/profiles.db
python -m src.analytics.negative_space run --cse-id CSE-089 --profiles data/profiles.db
python -m src.analytics.behavioral_anomalies run --cse-id CSE-073 --profiles data/profiles.db
```

### Expected Output

- Findings list per CSE
- Each finding traceable to specific record IDs

### Risks/Caveats

- Small sample sizes produce noisy signals; always attach confidence and caveats
- Do not claim findings are "non-compliant" — frame as "potential supervisory concern"

---

## Phase 6: Evidence Tracing

**Goal:** Build the traceability layer that links every finding to its source records.

### Why It Matters

Traceability is the core differentiator. Examiners must be able to validate any finding by inspecting the underlying records.

### What to Create

| Item | Path | Purpose |
|------|------|---------|
| Evidence tracer | `src/evidence/tracer.py` | Build evidence chains |
| Finding generator | `src/evidence/findings.py` | Assemble findings from signals |
| Tests | `tests/test_evidence.py` | Unit tests |

### Evidence Chain

Every finding must trace back to source records:

```
Finding
  → Signal
    → Metric
      → Calculation
        → Source records (alert IDs, investigation IDs, etc.)
```

### Implementation Requirements

1. `EvidenceTracer.trace(finding_id) -> EvidenceChain`
2. `EvidenceChain` contains: metric name, value, calculation method, contributing records
3. Each contributing record includes: record type, record ID, key fields, relevance explanation
4. Tracer queries SQLite for contributing records by ID
5. If a referenced record is missing (data quality issue), the chain notes this explicitly

### Acceptance Criteria

- [ ] Every finding has an evidence chain
- [ ] Evidence chain includes ≥3 levels of traceability
- [ ] Missing records are noted explicitly
- [ ] Examiner can navigate from finding → signal → metric → records
- [ ] 85%+ test coverage

### Validation Commands

```bash
python -m src.evidence.tracer trace --finding-id F-001 --db data/profiles.db
```

### Expected Output

```
Evidence Chain for F-001:
  Signal: superficial_closure
  Metric: closure_velocity_p50 = 3.2 minutes
  Calculation: median of alert-to-closure timestamps for CSE-042, 2024-Q4
  Contributing Records:
    - Alert AL-10291: closed in 2 minutes, severity=CRITICAL
    - Alert AL-10432: closed in 3 minutes, severity=HIGH
    - Alert AL-10778: closed in 4 minutes, severity=MEDIUM
    ... (237 total)
  Data Quality Note: 12 records missing closure_timestamp
```

### Risks/Caveats

- Large evidence chains (1000+ records) should be paginated in the UI

---

## Phase 7: Peer Benchmarking

**Goal:** Compare CSE behavior against normalized peer baselines.

### Why It Matters

Raw metrics are meaningless without context. Peer benchmarking answers: "Is this CSE different, and is the difference concerning?"

### What to Create

| Item | Path | Purpose |
|------|------|---------|
| Peer grouper | `src/analytics/benchmarking.py` | Group CSEs into peer sets |
| Benchmark calculator | `src/analytics/benchmarking.py` | Z-scores, percentiles |
| Tests | `tests/test_benchmarking.py` | Unit tests |

### Implementation Requirements

1. **Rule-based grouping (MVP):** Group by `(sector, size_band)`
2. Minimum peer group size: 3 CSEs
3. For each metric in a profile, compute:
   - Peer mean, median, std
   - CSE z-score: `(cse_value - peer_mean) / peer_std`
   - CSE percentile rank
   - Outlier flag: `|z_score| > 2.5`
4. Handle edge cases: single-member groups, zero-variance metrics
5. Document peer group definitions in every finding that uses them

### Acceptance Criteria

- [ ] Peer groups built for 50 CSEs
- [ ] Z-scores computed for key metrics
- [ ] Outliers flagged with peer context
- [ ] Peer group definitions included in findings
- [ ] Handles edge cases gracefully (small groups, zero variance)
- [ ] 85%+ test coverage

### Validation Commands

```bash
python -m src.analytics.benchmarking run --cse-id CSE-042 --profiles data/profiles.db
```

### Expected Output

```
Peer Group: Telecom_Large (n=8)
Metric: investigation_depth_mean
  CSE-042: 2.1 (z=-3.2, 5th percentile) ← OUTLIER
  Peer median: 6.1
  Peer std: 1.25
```

### Risks/Caveats

- Rule-based grouping is simplistic; clustering-based grouping is post-MVP
- Always disclose peer group composition in findings

---

## Phase 8: Supervisory Attention Score

**Goal:** Rank CSEs by supervisory priority using transparent, explainable scoring.

### Why It Matters

NCIIPC cannot manually review all CSEs. The score directs limited examiner time to highest-priority entities.

### What to Create

| Item | Path | Purpose |
|------|------|---------|
| Score engine | `src/analytics/scoring.py` | Core scoring logic |
| Tests | `tests/test_scoring.py` | Unit tests |

### Implementation Requirements

1. Score formula (configurable weights):

```python
score = (
    0.4 * avg_confidence +
    0.3 * avg_severity +
    0.3 * (0.5 * signal_count_score + 0.5 * diversity_score)
)
```

2. `avg_confidence`: mean of finding confidences
3. `avg_severity`: mean of severity scores (HIGH=1.0, MEDIUM=0.6, LOW=0.3)
4. `signal_count_score`: `min(len(findings) / 10, 1.0)`
5. `diversity_score`: `len(unique_signal_categories) / 4`
6. Normalize to 0–100 scale
7. **Do NOT call this a "risk score" or "compliance score"** — it is a prioritization tool
8. Consider naming: `Supervisory Attention Priority` instead of `Score`

### Acceptance Criteria

- [ ] Score computed for all 50 CSEs
- [ ] CSEs with seeded weaknesses rank in top 10
- [ ] Score components are transparent and logged
- [ ] Weights are configurable via `thresholds.json`
- [ ] 85%+ test coverage

### Validation Commands

```bash
python -m src.analytics.scoring rank --profiles data/profiles.db --findings data/findings.db
```

### Expected Output

```
CSE-042: 87.3 (5 findings, 4 signal types, avg confidence 0.88)
CSE-017: 82.1 (4 findings, 3 signal types, avg confidence 0.85)
CSE-089: 79.5 (3 findings, 2 signal types, avg confidence 0.82)
...
```

### Risks/Caveats

- Score is a prioritization heuristic, not a security rating
- Low score does NOT mean "safe" — it means "lower priority for this review cycle"

---

## Phase 9: Local LLM Explanation Layer (Optional)

**Goal:** Add an optional local LLM to generate examiner-friendly explanations.

### Why It Matters

LLMs can summarize findings, suggest review questions, and produce narrative reports. But they must not make analytical decisions or invent evidence.

### What to Create

| Item | Path | Purpose |
|------|------|---------|
| LLM client | `src/evidence/llm_explainer.py` | Local LLM interface |
| Prompt templates | `src/evidence/prompts/` | Finding explanation templates |
| Config toggle | `data/config/llm_config.json` | Enable/disable LLM |
| Tests | `tests/test_llm_explainer.py` | Unit tests (mock LLM) |

### What the LLM May Do

- Summarize a finding in plain language
- Suggest 2–3 questions for examiner investigation
- Produce a narrative report combining multiple findings
- Explain statistical concepts (z-score, percentile) to non-technical reviewers

### What the LLM MUST NOT Do

- Invent evidence or record IDs
- Change calculated metrics
- Claim certainty beyond the analytical engine
- Generate findings without analytical backing
- Access external APIs or cloud services

### Implementation Requirements

1. Use Ollama or equivalent local runtime
2. LLM is **optional** — system functions fully without it
3. All LLM outputs are labeled as "generated narrative" and distinguished from analytical evidence
4. Prompt templates enforce: "Base your explanation only on the following evidence..."
5. LLM receives: finding JSON + evidence chain + contributing records
6. LLM returns: plain-language explanation + suggested questions

### Configuration

```json
{
  "enabled": false,
  "provider": "ollama",
  "model": "llama3:8b",
  "endpoint": "http://localhost:11434/api/generate",
  "timeout_seconds": 30,
  "max_tokens": 500
}
```

### Acceptance Criteria

- [ ] System runs and produces all findings without LLM installed
- [ ] When LLM is enabled, explanations are generated
- [ ] LLM outputs are clearly labeled as narrative, not evidence
- [ ] LLM does not invent record IDs or metrics
- [ ] Tests mock LLM responses for deterministic testing
- [ ] 80%+ test coverage

### Validation Commands

```bash
# Without LLM
python -m src.api.main  # Should work without Ollama

# With LLM (if installed)
export LLM_ENABLED=true
python -m src.api.main
curl http://localhost:8000/api/findings/F-001/explain?use_llm=true
```

### Expected Output

```json
{
  "finding_id": "F-001",
  "analytical_explanation": "...",
  "llm_narrative": "CSE-042 shows a concerning pattern...",
  "suggested_questions": [
    "Did staffing levels change in Q3 2024?",
    "Was there a new KPI introduced that rewards fast closure?"
  ],
  "llm_disclaimer": "This narrative was generated by AI. Verify against source records."
}
```

### Risks/Caveats

- Local LLM quality depends on available hardware
- LLM is a nice-to-have, not a judging criterion
- Do not rely on LLM for any analytical decision

---

## Phase 10: FastAPI Backend

**Goal:** Build the complete REST API that serves analytics results and dashboard data.

### Why It Matters

The backend is the bridge between analytics and the examiner interface. It must be fast, well-documented, and locally deployable.

### What to Create

| Item | Path | Purpose |
|------|------|---------|
| App factory | `src/api/main.py` | FastAPI application setup |
| Routes | `src/api/routes.py` | All API endpoints |
| Pydantic models | `src/api/models.py` | Request/response schemas |
| Error handlers | `src/api/errors.py` | Consistent error responses |
| CORS middleware | `src/api/middleware.py` | Frontend access |
| Tests | `tests/test_api.py` | Integration tests |

### API Endpoints

```
# Health
GET /health

# Ingestion
POST /api/ingest/upload
GET  /api/ingest/status/{cse_id}
GET  /api/ingest/quality/{cse_id}

# Profiles
GET  /api/profiles/{cse_id}?period=2024-Q1
GET  /api/profiles/{cse_id}/trends?metric=investigation_depth&periods=4
GET  /api/profiles/compare?cse_ids=CSE-042,CSE-017&period=2024-Q1

# Findings
GET  /api/findings?cse_id=CSE-042&severity=HIGH
GET  /api/findings/{finding_id}
GET  /api/findings/{finding_id}/explain
GET  /api/findings/execution-gaps
GET  /api/findings/negative-space
GET  /api/findings/behavioral-anomalies
GET  /api/findings/peer-deviations

# Portfolio
GET  /api/portfolio/rankings
GET  /api/portfolio/summary

# Peers
GET  /api/peers/{cse_id}
GET  /api/peers/compare?cse_ids=CSE-042,CSE-017

# Analytics (run on demand)
POST /api/analytics/run
GET  /api/analytics/status/{job_id}
```

### Implementation Requirements

1. Use `sqlalchemy` with `aiosqlite` for async database access
2. All endpoints return JSON with consistent structure: `{ "data": ..., "meta": ..., "errors": ... }`
3. CORS enabled for local frontend access
4. OpenAPI docs auto-generated at `/docs`
5. Error responses use standard HTTP status codes with structured JSON body
6. File upload via `python-multipart` for ingestion endpoint

### Acceptance Criteria

- [ ] All endpoints return valid JSON
- [ ] OpenAPI docs accessible at `/docs`
- [ ] CORS configured
- [ ] Error handling returns consistent structure
- [ ] Integration tests pass

### Validation Commands

```bash
uvicorn src.api.main:app --reload
open http://localhost:8000/docs
curl http://localhost:8000/health
curl http://localhost:8000/api/portfolio/rankings
```

### Expected Output

- Swagger UI at `http://localhost:8000/docs`
- JSON responses for all endpoints

### Risks/Caveats

- Keep API simple; do not add authentication for MVP
- Pagination not required for MVP (portfolio is 50 CSEs, not 50K)

---

## Phase 11: Local Dashboard (Jinja2 + Vanilla JS)

**Goal:** Build a lightweight, offline-capable dashboard using FastAPI + Jinja2 + vanilla JavaScript + Chart.js.

### Why It Matters

The dashboard is the examiner's interface. It must prioritize clarity, evidence drill-down, and workflow over visual complexity.

### What to Create

| Item | Path | Purpose |
|------|------|---------|
| Dashboard routes | `src/dashboard/routes.py` | Page routes |
| Base template | `src/dashboard/templates/base.html` | Layout shell |
| Portfolio view | `src/dashboard/templates/portfolio.html` | Entity rankings |
| Entity view | `src/dashboard/templates/entity.html` | Entity deep dive |
| Finding view | `src/dashboard/templates/finding.html` | Finding detail + evidence |
| Static CSS | `src/dashboard/static/css/style.css` | Styling |
| Static JS | `src/dashboard/static/js/app.js` | Fetch API, rendering |
| Chart.js | CDN or local copy | Lightweight charts |

### Technology Constraints

- **NO React**
- **NO Node.js / npm**
- **NO build step required**
- Jinja2 templates served by FastAPI
- Vanilla JavaScript with `fetch()` for API calls
- Chart.js via CDN or local `static/js/lib/chart.min.js`
- CSS: plain CSS or lightweight framework (no Tailwind build step)

### View Specifications

#### Portfolio View (`/dashboard/`)

```html
<!-- portfolio.html -->
<h1>SAT-SA Portfolio Overview</h1>
<div class="summary-cards">
  <div class="card">Total CSEs: <span id="total-cses">50</span></div>
  <div class="card">High-Priority Findings: <span id="high-priority">12</span></div>
  <div class="card">Critical Signals: <span id="critical-signals">3</span></div>
</div>
<table id="rankings-table">
  <thead>
    <tr>
      <th>Rank</th>
      <th>CSE ID</th>
      <th>Sector</th>
      <th>Attention Priority</th>
      <th>Findings</th>
      <th>Top Signal</th>
    </tr>
  </thead>
  <tbody id="rankings-body">
    <!-- Populated by JS -->
  </tbody>
</table>
<script>
  fetch('/api/portfolio/rankings')
    .then(r => r.json())
    .then(data => renderRankings(data));
</script>
```

#### Entity View (`/dashboard/entity/{cse_id}`)

- Profile summary cards (alert volume, investigation depth, closure velocity, escalation rate)
- Findings list with severity badges
- Peer comparison chart (Chart.js bar chart)
- Recommended actions

#### Finding View (`/dashboard/finding/{finding_id}`)

- Finding header (type, severity, confidence)
- Rationale section
- Evidence table (contributing records)
- Record detail expandable rows
- Peer context (if applicable)
- Recommended examiner actions

### Implementation Requirements

1. FastAPI serves Jinja2 templates via `Jinja2Templates`
2. Static files (CSS, JS) served from `src/dashboard/static/`
3. JavaScript uses `fetch()` for all API calls — no build step
4. Chart.js loaded via CDN or local file
5. Responsive layout using CSS Grid/Flexbox
6. Color coding: red (HIGH), yellow (MEDIUM), green (LOW)

### Acceptance Criteria

- [ ] Portfolio view displays 50 CSEs ranked by priority
- [ ] Click navigates to entity detail
- [ ] Entity view shows profile, findings, peer chart
- [ ] Finding view shows full evidence chain
- [ ] Works without internet (no CDN dependencies)
- [ ] Responsive on mobile/tablet

### Validation Commands

```bash
uvicorn src.api.main:app --reload
open http://localhost:8000/dashboard/
```

### Expected Output

- Fully functional dashboard at `http://localhost:8000/dashboard/`
- No external build tools required

### Risks/Caveats

- Chart.js CDN dependency breaks offline; bundle locally or use inline SVG
- Large tables (1000+ rows) require virtual scrolling or pagination — defer to post-MVP

---

## Phase 12: End-to-End Integration

**Goal:** Connect all components into a working pipeline: ingest → profile → analyze → find → prioritize → display.

### Why It Matters

Individual components are useless without integration. This phase proves the full data flow works end-to-end.

### What to Create

| Item | Path | Purpose |
|------|------|---------|
| Pipeline script | `scripts/run_pipeline.py` | One-command end-to-end run |
| Integration tests | `tests/test_integration.py` | Full pipeline tests |
| Demo data loader | `scripts/load_demo_data.py` | Load demo dataset into DB |

### Pipeline Flow

```python
# scripts/run_pipeline.py
def main():
    # 1. Generate sample data (if not present)
    generate_sample_data_if_missing()
    
    # 2. Ingest
    ingestion = ingest_directory("data/samples/demo_dataset/")
    print(f"Ingested {ingestion.total_records} records (quality: {ingestion.quality_score:.0%})")
    
    # 3. Profile
    profiles = compute_all_profiles()
    print(f"Computed {len(profiles)} profiles")
    
    # 4. Detect signals
    all_findings = []
    for cse_id in get_all_cse_ids():
        findings = run_all_signals(cse_id, profiles)
        all_findings.extend(findings)
    print(f"Generated {len(all_findings)} findings")
    
    # 5. Score and rank
    rankings = rank_portfolio(all_findings)
    print(f"Top CSE: {rankings[0]['cse_id']} (priority: {rankings[0]['score']:.1f})")
    
    # 6. Store in DB
    store_findings(all_findings)
    store_rankings(rankings)
    
    print("Pipeline complete.")
```

### Acceptance Criteria

- [ ] `python scripts/run_pipeline.py` runs end-to-end without errors
- [ ] All 8 seeded weaknesses detected
- [ ] Rankings place seeded CSEs in top 10
- [ ] Findings stored in SQLite
- [ ] Dashboard displays results
- [ ] Integration tests pass

### Validation Commands

```bash
python scripts/run_pipeline.py
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
open http://localhost:8000/dashboard/
```

### Expected Output

- Working end-to-end pipeline
- Dashboard showing findings and rankings
- 2-minute demo possible

### Risks/Caveats

- Pipeline must be idempotent (can run multiple times without corrupting data)
- Large datasets may require progress indicators

---

## Phase 13: Testing and Validation

**Goal:** Validate that the analytics engine detects seeded weaknesses reliably.

### Why It Matters

SIH judges will evaluate whether the system actually works. Validation proves detection capability.

### What to Create

| Item | Path | Purpose |
|------|------|---------|
| Validation runner | `scripts/run_validation.py` | Execute validation suite |
| Test oracle | `scripts/design_test_cases.py` | Define ground truth |
| Validation report | `docs/validation_report.md` | Results documentation |
| Tests | `tests/test_validation.py` | Automated validation |

### Ground Truth Design

For each seeded CSE, define:

```python
TEST_CASES = [
    {
        "cse_id": "CSE-042",
        "expected_signals": ["quality_degradation", "investigation_depth_outlier"],
        "min_confidence": 0.7,
        "description": "Investigation depth declined 70% over 4 quarters"
    },
    {
        "cse_id": "CSE-089",
        "expected_signals": ["alert_volume_gap", "telemetry_absence"],
        "min_confidence": 0.8,
        "description": "0 endpoint alerts despite 500+ endpoints"
    },
    # ... 6 more
]
```

### Metrics to Report

| Metric | Target | Definition |
|--------|--------|-----------|
| **Coverage (Recall)** | ≥ 70% | Seeded weaknesses detected / total seeded weaknesses |
| **Precision** | ≥ 60% | True findings / total findings generated |
| **False Positive Rate** | < 40% | False findings / total findings |
| **Examiner Alignment** | ≥ 0.7 | Correlation with expected ranking |

### Acceptance Criteria

- [ ] All 8 seeded weaknesses detected
- [ ] Coverage ≥ 70%
- [ ] Precision ≥ 60%
- [ ] False positive rate < 40%
- [ ] Validation report documents results and limitations
- [ ] Automated tests catch regressions

### Validation Commands

```bash
python scripts/run_validation.py --dataset data/samples/demo_dataset/ --output docs/validation_report.md
pytest tests/test_validation.py -v
```

### Expected Output

- `docs/validation_report.md` with metrics and analysis
- All tests passing

### Risks/Caveats

- Precision/recall require ground truth; use seeded weaknesses as oracle
- Do not over-claim performance; document limitations honestly

---

## Phase 14: SIH Demo Preparation

**Goal:** Create a polished 2-minute demo that tells a compelling story.

### Why It Matters

Judges evaluate the demo, not just the code. A clear demo story is worth more than unimplemented advanced features.

### What to Create

| Item | Path | Purpose |
|------|------|---------|
| Demo script | `docs/demo_script.md` | Timed 2-minute script |
| Curated dataset | `data/samples/demo_dataset/` | Pre-generated, reliable |
| Backup screenshots | `docs/demo_screenshots/` | Fallback if live demo fails |
| Demo video guide | `docs/demo_video_guide.md` | Recording instructions |

### Demo Storyboard (2 Minutes)

```
[0:00-0:10] Problem
  "NCIIPC supervises 50+ critical infrastructure entities. Manual review doesn't scale.
   KPIs look green while operational quality degrades. SAT-SA finds what dashboards miss."

  [Screen: Portfolio overview with 50 CSEs]

[0:10-0:30] Portfolio View
  "50 CSEs analyzed. 12 with supervisory findings. Ranked by Supervisory Attention Priority —
   not a risk score, but a prioritization of where examiners should look."

  "CSE-042 is ranked #1. Let me investigate."

  [Screen: Click CSE-042 → entity view]

[0:30-0:50] Execution Gap Finding
  "CSE-042 shows investigation depth declining 70% over 4 quarters.
   Q1: 7.2 evidence entries per alert. Q4: 2.1 entries.
   Change point detected in Q3.

   At the same time, closure velocity improved.
   That's an execution gap: closing faster, investigating less."

  [Screen: Trend chart + peer comparison]

[0:50-1:10] Evidence Drill-Down
  "Every finding traces to specific records.
   Investigation 042-8821: high-severity alert, closed in 3 hours, 2 evidence entries.
   Compare to Q1: same alert type, 10 entries, 14-hour investigation.

   The system identifies the question. The examiner answers it."

  [Screen: Side-by-side record comparison]

[1:10-1:25] Negative Space Finding
  "CSE-089 claims 2,000 endpoints under EDR. Expected: 300+ endpoint alerts per quarter.
   Observed: zero.

   This is negative space — expected evidence that is absent.
   Either EDR is broken, monitoring is disabled, or data wasn't submitted.
   That's a supervisory question for NCIIPC."

  [Screen: Alert volume gap visualization]

[1:25-1:45] Peer Context
  "CSE-042 is in a peer group of 8 telecom SOCs.
   Peer median investigation depth: 6.1 entries.
   CSE-042: 2.1 entries. That's 3.2 standard deviations.
   Not borderline — clear deviation requiring examiner review."

  [Screen: Peer comparison chart]

[1:45-2:00] Closing
  "SAT-SA doesn't replace examiners. It extends their reach.
   Raw SOC data → analytics → evidence-backed findings → prioritized for human review.
   The system identifies. The examiner decides."

  [Screen: SAT-SA positioning]
```

### Acceptance Criteria

- [ ] Demo script timed and rehearsed (≤2 minutes)
- [ ] Curated dataset loads reliably
- [ ] Backup screenshots taken for all key screens
- [ ] Demo flow is smooth with no errors
- [ ] Team can explain each finding in <30 seconds

### Validation Commands

```bash
python scripts/load_demo_data.py
make run
# Manually walk through demo flow, time it
```

### Expected Output

- Timed demo that fits in 2 minutes
- Clear, compelling narrative

### Risks/Caveats

- Live demos fail. Have backup screenshots and a pre-recorded video ready
- Practice extensively; 2 minutes is very short

---

## Phase 15: Post-MVP / Future Capabilities

**Goal:** Document advanced capabilities that are NOT part of the MVP but strengthen the long-term vision.

### Why It Matters

Clear separation of MVP vs. post-MVP prevents scope creep while showing judges the roadmap.

### Post-MVP Capabilities

| Capability | Priority | Effort | Description |
|------------|----------|--------|-------------|
| **Full Expected Evidence Model** | High | 2–3 weeks | Bayesian expected-vs-observed with uncertainty quantification |
| **Signal Fusion Engine** | High | 1–2 weeks | Combine multiple weak signals into high-confidence supervisory cases |
| **KPI-Reality Divergence** | High | 1 week | Detect metric gaming (SLA improves while quality declines) |
| **Temporal Drift Detection** | High | 1 week | CUSUM/PELT change-point detection on time series |
| **Cyclical/Temporal Anomalies** | Medium | 1 week | Bulk closures, weekend gaps, shift variance |
| **Investigation Quality NLP** | Medium | 2 weeks | Detect templated investigation notes via text similarity |
| **Clustering-Based Peer Grouping** | Medium | 1 week | K-means/DBSCAN peer groups instead of rule-based |
| **Examiner Feedback Loop** | Medium | 1 week | Examiner ratings feed back into threshold calibration |
| **Graph Analytics** | Low | 2 weeks | Asset-alert-case escalation relationship mapping |
| **PDF Report Export** | Low | 1 week | Generate printable examiner reports |
| **Multi-Period Trend Analysis** | Low | 1 week | Portfolio-wide trend dashboards |
| **Advanced Data Quality** | Low | 1 week | Statistical outlier detection for data quality |
| **Streaming Ingestion** | Low | 3 weeks | Real-time or near-real-time data feeds |
| **PostgreSQL Migration** | Low | 1 week | Production-scale database |

### Out-of-Scope (Never)

- Real-time SOC monitoring
- SIEM correlation
- Network packet analysis
- Cloud deployment
- External API integrations
- Generic AI chatbot
- Compliance certification

### Post-MVP Roadmap

**Month 1–2:** Signal fusion + KPI-reality divergence + temporal drift  
**Month 3–4:** Investigation NLP + clustering peer groups  
**Month 5–6:** Examiner feedback loop + validation with real data  
**Month 7–12:** Production deployment with NCIIPC

---

## Phase Dependencies

```
Phase 0:  Project Bootstrap
    ↓
Phase 1:  Canonical Data Schema
    ↓
Phase 2:  Synthetic SOC Dataset Generator
    ↓
Phase 3:  Format-Agnostic Ingestion Layer
    ↓
Phase 4:  Behavioral Profiling
    ↓
Phase 5:  Supervisory Signal Engine
    ↓
Phase 6:  Evidence Tracing
    ↓
Phase 7:  Peer Benchmarking
    ↓
Phase 8:  Supervisory Attention Score
    ↓
Phase 9:  Local LLM Explanation Layer (optional)
    ↓
Phase 10: FastAPI Backend
    ↓
Phase 11: Local Dashboard
    ↓
Phase 12: End-to-End Integration
    ↓
Phase 13: Testing and Validation
    ↓
Phase 14: SIH Demo Preparation
```

Post-MVP phases (15+) are independent and can be pursued after SIH.

---

## MVP Checklist

Use this checklist to verify the MVP is complete:

### Data Pipeline
- [ ] Canonical schema defined and documented
- [ ] CSV/JSON/JSONL ingestion adapters working
- [ ] Data quality assessment produces score and warnings
- [ ] Synthetic data generator produces realistic seeded dataset

### Analytics
- [ ] Behavioral profiler computes 20+ metrics per CSE per period
- [ ] Execution gap signals (≥3) detect seeded weaknesses
- [ ] Negative space signals (≥2) detect seeded weaknesses
- [ ] Behavioral anomaly signals (≥3) detect seeded weaknesses
- [ ] Peer benchmarking identifies outliers with z-scores
- [ ] Supervisory Attention Score ranks CSEs transparently

### Evidence & Findings
- [ ] Every finding includes contributing record IDs
- [ ] Evidence chains traceable: Finding → Signal → Metric → Records
- [ ] Data quality notes included in findings
- [ ] LLM explanation layer optional and non-blocking

### Backend & Dashboard
- [ ] FastAPI serves all endpoints
- [ ] Local dashboard (Jinja2 + vanilla JS) functional
- [ ] Portfolio view shows ranked CSEs
- [ ] Entity view shows profile + findings + peer comparison
- [ ] Finding view shows evidence chain with drill-down

### Validation
- [ ] All 8 seeded weaknesses detected
- [ ] Coverage ≥ 70%
- [ ] Precision ≥ 60%
- [ ] False positive rate < 40%

### Demo
- [ ] 2-minute demo script rehearsed
- [ ] Demo runs locally without internet
- [ ] Backup screenshots prepared
- [ ] Team can explain each finding in <30 seconds

---

## Final Quality Check

Before considering the plan complete, verify it answers these questions:

1. **What exactly does SAT-SA analyze?**
   SOC alerts, investigations, escalations, cases, and asset inventory from CSE submissions.

2. **Who uses it?**
   NCIIPC examiners and supervisors conducting periodic CSE assessments.

3. **What makes it different from a SOC dashboard?**
   It analyzes evidence chains and behavioral patterns to detect execution gaps and negative space, not real-time attacks or KPIs.

4. **How does raw SOC data become a finding?**
   Ingestion → canonical schema → behavioral profiles → signal detection → evidence tracing → finding generation.

5. **How is every finding backed by evidence?**
   Every finding includes contributing record IDs, detection logic, and a traceable evidence chain.

6. **How does the system handle missing/incomplete data?**
   Data quality assessment runs first. Missing data generates warnings. Findings include data-quality notes. Missing data does not automatically become a security finding.

7. **Why is an LLM optional?**
   The primary analytical engine is deterministic/statistical. The LLM only generates explanations. The system functions fully without it.

8. **How can the entire system run offline?**
   All dependencies are local Python packages. No cloud services, no external APIs, no Node.js build step. Runs with `python -m venv && pip install && uvicorn`.

9. **What is the minimum viable SIH demo?**
   Load demo dataset → run analytics → show portfolio rankings → drill into CSE-042 → show execution gap finding → show evidence chain → show peer comparison → explain examiner workflow.

10. **Which capabilities are genuinely novel versus standard analytics?**
    Execution gap detection, negative space detection, evidence chain tracing, and supervisory attention prioritization are novel. Standard profiling and peer benchmarking are established techniques applied to a new domain.

11. **Can a small student team realistically implement the MVP?**
    Yes. 14 phases, each with clear deliverables. Core analytics use Pandas + SciPy. No distributed systems, no ML training, no cloud.

12. **Can the entire demo be run locally on one machine?**
    Yes. SQLite database, FastAPI backend, Jinja2 dashboard, all served from one process. No network dependencies.

---

*Last updated: 2026-08-23*  
*Status: Rewritten for SIH26157 — Simplified, local-first, implementation-ready*
