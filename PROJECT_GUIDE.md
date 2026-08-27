# SAT-SA — Complete Project Guide

**Project:** SAT-SA (Supervisory Analytics Tool for SOC Assessment)  
**Competition:** Smart India Hackathon 2026 · SIH26157 · NCIIPC  
**Last updated:** 2026-08-27

---

## Table of Contents

1. [What This Project Is](#1-what-this-project-is)
2. [Technology Stack](#2-technology-stack)
3. [Directory Structure](#3-directory-structure)
4. [Every File Explained](#4-every-file-explained)
5. [How Data Flows](#5-how-data-flows)
6. [Signal Catalog](#6-signal-catalog)
7. [Test Examples](#7-test-examples)
8. [How to Run](#8-how-to-run)
9. [Key Architecture Decisions](#9-key-architecture-decisions)
10. [Seeded Weaknesses](#10-seeded-weaknesses-demo-dataset)

---

## 1. What This Project Is

SAT-SA analyzes SOC (Security Operations Center) records from Critical Sector Entities (CSEs) to find supervisory weaknesses — problems that KPIs, dashboards, and compliance reports miss.

**Core idea:** Don't detect hackers. Detect SOCs that are going through the motions.

**Two hidden problems we find:**

| Problem | Description | Example |
|---------|-------------|---------|
| **Execution Gap** | Policies say X, but evidence says Y | Alerts "investigated" in 30 seconds |
| **Negative Space** | Expected evidence is missing | 217 endpoints but zero endpoint alerts |

**Validation:** 100% coverage (9/9 seeded weaknesses found), 0% false-positive rate.

---

## 2. Technology Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Language** | Python 3.9+ | Offline-first, rich analytics ecosystem |
| **Backend** | FastAPI | Auto-documented API, async support |
| **Database** | SQLite | Zero-config, file-based, air-gap ready |
| **Analytics** | Pandas + NumPy + SciPy | Statistical analysis, no ML training needed |
| **Frontend** | Jinja2 + vanilla JS + Chart.js | No build step, no Node.js, fully offline |
| **Reports** | Jinja2 HTML → print-to-PDF | Self-contained, no external deps |
| **Testing** | pytest | 357+ tests across 19 test files |
| **Deployment** | Python venv + uvicorn | No Docker, no cloud, fully offline |

**No cloud. No internet. No external APIs. Runs on a laptop.**

---

## 3. Directory Structure

```
SIH/
├── src/                          # Source code
│   ├── analytics/                # Signal detection engine
│   │   ├── schemas.py            # Canonical data models (7 entities)
│   │   ├── sample_data.py        # Synthetic data generator (50 CSEs)
│   │   ├── profiler.py           # Behavioral profiling (20+ metrics)
│   │   ├── signal_engine.py      # Runs all 25 signals
│   │   ├── signal_common.py      # SignalContext dataclass
│   │   ├── execution_gaps.py     # 5 signals
│   │   ├── negative_space.py     # 5 signals
│   │   ├── behavioral_anomalies.py # 5 signals
│   │   ├── peer_deviation.py     # 3 signals
│   │   ├── reasoning_quality_signals.py # 4 signals (NEW)
│   │   ├── reasoning_quality.py  # Justification parser/classifier
│   │   ├── benchmarking.py       # Peer grouping + z-scores
│   │   ├── scoring.py            # Supervisory Attention Score
│   │   ├── finding.py            # Finding data structure
│   │   ├── fusion.py             # Signal fusion
│   │   ├── profiles.py           # BehavioralProfile class
│   │   └── expected_evidence.py  # Advanced: Bayesian expected evidence
│   ├── ingestion/                # Data pipeline
│   │   ├── adapters.py           # CSV/JSON/JSONL parsers
│   │   ├── mapper.py             # Column name normalization
│   │   ├── normalizer.py         # Raw dicts → Pydantic models
│   │   ├── quality.py            # Data quality scoring
│   │   └── pipeline.py           # Orchestrate: parse → map → normalize → store
│   ├── evidence/                 # Finding construction
│   │   ├── tracer.py             # Evidence chain: finding → records
│   │   ├── findings.py           # Load/store findings
│   │   ├── reporter.py           # Report generation
│   │   └── llm_explainer.py      # Optional: local LLM explanations
│   ├── api/                      # FastAPI backend
│   │   ├── main.py               # App factory
│   │   ├── routes.py             # 20+ API endpoints
│   │   ├── models.py             # Pydantic request/response
│   │   └── errors.py             # Error handlers + envelope format
│   ├── dashboard/                # Jinja2 frontend
│   │   ├── routes.py             # Page routes
│   │   ├── templates/            # HTML templates (base, portfolio, entity, finding, report)
│   │   └── static/               # CSS + JS
│   ├── storage/                  # Database layer
│   │   └── db.py                 # SQLite engine + CRUD
│   └── feedback.py               # Examiner feedback loop
├── tests/                        # 357 tests
│   ├── conftest.py               # Test fixtures
│   ├── test_schemas.py           # 18 tests
│   ├── test_ingestion.py         # 28 tests
│   ├── test_profiler.py          # 33 tests
│   ├── test_signal_engine.py     # 72 tests
│   ├── test_benchmarking.py      # 42 tests
│   ├── test_scoring.py           # 16 tests
│   ├── test_evidence.py          # 17 tests
│   ├── test_reasoning_quality.py # 20 tests (NEW)
│   ├── test_api.py               # 43 tests
│   ├── test_dashboard.py         # 8 tests
│   ├── test_feedback.py          # 14 tests
│   └── ...                       # More test files
├── scripts/                      # Utility scripts
│   ├── demo.py                   # One-command demo launcher
│   ├── run_pipeline.py           # Full pipeline
│   ├── run_validation.py         # Validation harness
│   ├── load_demo_data.py         # Load demo dataset
│   └── generate_sample_data.py   # Generate synthetic CSE data
├── data/                         # Data files
│   ├── samples/demo_dataset/     # 6 CSV files (50 CSEs, 243K records)
│   ├── config/
│   │   ├── thresholds.json       # Detection thresholds
│   │   └── peer_groups.json      # Peer group definitions
│   └── sat_sa.db                 # SQLite database (generated)
├── docs/                         # Documentation
│   ├── demo_script.md            # 2-minute demo script
│   ├── demo_checklist.md         # Pre-demo checklist
│   ├── validation_report.md      # Detection performance metrics
│   └── demo_screenshots/         # Backup screenshots
├── requirements.txt              # Python dependencies
├── Makefile                      # setup, test, run, clean
└── .env.example                  # Environment variables
```

---

## 4. Every File Explained

### 4.1 Analytics Module (`src/analytics/`)

| File | Purpose | Key Functions |
|------|---------|---------------|
| `schemas.py` | Canonical data models | `Alert`, `Investigation`, `Escalation`, `Case`, `Asset`, `CSEMetadata`, `Dataset` |
| `sample_data.py` | Synthetic data generator | `generate_dataset()`, `EntitySpec`, `ScenarioParams` |
| `profiler.py` | Behavioral profiling | `compute_all_profiles()`, `store_profiles()`, `load_profiles()` |
| `signal_engine.py` | Signal runner | `run_context()`, `build_contexts()`, `persist_findings()` |
| `signal_common.py` | Signal context | `SignalContext` dataclass |
| `execution_gaps.py` | 5 execution gap signals | `superficial_closure()`, `escalation_without_action()`, etc. |
| `negative_space.py` | 5 negative space signals | `alert_volume_gap()`, `missing_investigations()`, etc. |
| `behavioral_anomalies.py` | 5 behavioral anomaly signals | `temporal_drift()`, `unusual_quiet_period()`, etc. |
| `peer_deviation.py` | 3 peer deviation signals | `closure_velocity_outlier()`, etc. |
| `reasoning_quality.py` | Justification analysis | `parse_justification()`, `coherence_score()`, `detect_template_notes()` |
| `reasoning_quality_signals.py` | 4 reasoning quality signals | `_shallow_justification()`, `_template_notes()`, etc. |
| `benchmarking.py` | Peer benchmarking | `build_peer_benchmarks()`, `load_benchmarks()` |
| `scoring.py` | Attention Score | `calculate_supervisory_attention_score()`, `rank_portfolio()` |
| `finding.py` | Finding structure | `Finding` dataclass, `load_thresholds()` |
| `fusion.py` | Signal fusion | `fuse_signals()`, `generate_supervisory_cases()` |
| `profiles.py` | Profile class | `BehavioralProfile` dataclass |
| `expected_evidence.py` | Advanced expected evidence | Bayesian expected evidence model |

### 4.2 Ingestion Module (`src/ingestion/`)

| File | Purpose | Key Classes |
|------|---------|-------------|
| `adapters.py` | Format parsers | `CSVAdapter`, `JSONAdapter`, `JSONLAdapter` |
| `mapper.py` | Column name normalization | `ColumnMapper` |
| `normalizer.py` | Raw to canonical transform | `Normalizer` |
| `quality.py` | Data quality scoring | `DataQualityReport` |
| `pipeline.py` | Orchestration | `IngestionPipeline` |

### 4.3 API Module (`src/api/`)

| File | Purpose | Key Endpoints |
|------|---------|---------------|
| `main.py` | App factory | `create_app()` |
| `routes.py` | 20+ endpoints | `/health`, `/api/ingest/upload`, `/api/profiles/{id}`, `/api/findings`, etc. |
| `models.py` | Request/response | `envelope()` wrapper |
| `errors.py` | Error handling | `install_error_handlers()` |

### 4.4 Dashboard Module (`src/dashboard/`)

| File | Purpose |
|------|---------|
| `routes.py` | Page routes |
| `templates/base.html` | Layout shell |
| `templates/portfolio.html` | Rankings + upload |
| `templates/entity.html` | Profile + findings |
| `templates/finding.html` | Evidence + feedback |
| `templates/report.html` | Downloadable report |
| `static/css/style.css` | Styling |
| `static/js/app.js` | API calls + charts |

---

## 5. How Data Flows

```
1. DATA GENERATION
   scripts/load_demo_data.py
   └── generate_dataset(seed=42, n_cses=50)
       └── 6 CSV files in data/samples/demo_dataset/

2. INGESTION
   IngestionPipeline.run()
   └── adapters.py: Parse CSV/JSON/JSONL
   └── mapper.py: Normalize column names
   └── normalizer.py: Raw dicts → Pydantic models
   └── quality.py: Score completeness
   └── storage/db.py: Store in SQLite

3. PROFILING
   profiler.compute_all_profiles()
   └── 20+ metrics per CSE per period

4. SIGNAL DETECTION (25 signals, 5 categories)
   signal_engine.run_context()
   └── Execution Gaps (5 signals)
   └── Negative Space (5 signals)
   └── Behavioral Anomalies (5 signals)
   └── Peer Deviation (3 signals)
   └── Reasoning Quality (4 signals)

5. EVIDENCE TRACING
   evidence/tracer.py
   └── Every finding → specific record IDs

6. SCORING & RANKING
   scoring.py
   └── Supervisory Attention Score
   └── Rank all CSEs by score

7. PRESENTATION
   Dashboard: Portfolio → Entity → Finding → Evidence
   Feedback: Examiner marks findings
   Reports: Downloadable HTML
```

---

## 6. Signal Catalog

### Execution Gaps (5 signals)

| Signal | What It Detects | How |
|--------|----------------|-----|
| `superficial_closure` | Fast closure + shallow investigation | Closure velocity + depth correlation |
| `escalation_without_action` | Escalation without follow-through | Escalation → follow-up evidence check |
| `quality_degradation` | Investigation depth declining | Change-point detection |
| `severity_mismatch` | High-severity closed as benign | Severity vs. depth vs. closure time |
| `kpi_divergence` | Metrics improve while quality declines | KPI trend vs. quality trend |

### Negative Space (5 signals)

| Signal | What It Detects | How |
|--------|----------------|-----|
| `alert_volume_gap` | Expected alerts vs. observed | Bayesian expected volume |
| `missing_investigations` | High-severity without investigation | Severity → investigation check |
| `missing_alert_categories` | Expected alert types absent | Inventory-to-alert mapping |
| `telemetry_absence` | Critical assets producing no alerts | Asset criticality → alert check |
| `escalation_absence` | Alerts meeting criteria but not escalated | Severity → escalation check |

### Behavioral Anomalies (5 signals)

| Signal | What It Detects | How |
|--------|----------------|-----|
| `temporal_drift` | Sudden change in investigation depth | CUSUM/PELT change-point |
| `unusual_quiet_period` | No alerts during expected hours | Temporal gap detection |
| `bulk_closure_pattern` | Mass closures on specific days | Daily distribution anomaly |
| `shift_variance` | Quality differs across shifts | Hour-of-day variance |
| `recurring_incident` | Same alert repeats without resolution | Recurrence + reopen check |

### Peer Deviation (3 signals)

| Signal | What It Detects | How |
|--------|----------------|-----|
| `closure_velocity_outlier` | Closure speed ≠ peers | Z-score vs. peer group |
| `investigation_depth_outlier` | Investigation depth ≠ peers | Z-score vs. peer group |
| `escalation_rate_outlier` | Escalation rate ≠ peers | Z-score vs. peer group |

### Reasoning Quality (4 signals)

| Signal | What It Detects | How |
|--------|----------------|-----|
| `shallow_justification` | HIGH/CRITICAL alerts with minimal notes | Word count + keyword analysis |
| `template_notes` | Near-duplicate notes across cases | Linguistic similarity |
| `missing_escalation_rationale` | Escalated cases without justification | Escalation → note check |
| `reasoning_inflation` | Claims actions not evidenced | Keywords vs. evidence |

---

## 7. Test Examples

### Schema Tests

```python
def test_alert_validation():
    alert = Alert(alert_id="AL-001", cse_id="CSE-001", severity="HIGH")
    assert alert.severity == "HIGH"
    assert alert.status is None  # Optional fields default to None
```

### Ingestion Tests

```python
def test_csv_adapter_parses_standard_format():
    adapter = CSVAdapter()
    result = adapter.parse("data/samples/demo_dataset/alerts.csv")
    assert "alerts" in result
    assert len(result["alerts"]) > 1000
```

### Signal Engine Tests

```python
def test_registry_has_25_signals_in_five_categories():
    assert len(SIGNAL_REGISTRY) == 25
    cats = {cat for cat, _ in SIGNAL_REGISTRY.values()}
    assert "reasoning_quality" in cats

def test_all_nine_seeded_cses_flagged(demo_findings):
    flagged = {f.cse_id for f in demo_findings}
    assert SEEDED <= flagged  # All 9 seeded CSEs detected
```

### Reasoning Quality Tests

```python
def test_parse_justification_technical():
    notes = "Analyzed malware signature against threat intelligence feeds."
    result = parse_justification(notes)
    assert "technical" in result["reasoning_types"]
    assert result["depth_score"] >= 4

def test_coherence_score_high_severity_shallow():
    justification = parse_justification("Checked. Benign.")
    score, gaps = coherence_score(justification, "CRITICAL")
    assert score < 0.4
    assert len(gaps) > 0
```

### API Tests

```python
def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "ok"
```

### Feedback Tests

```python
def test_submit_feedback(client):
    response = client.post(
        "/api/findings/CSE-042:kpi_divergence/feedback",
        json={"disposition": "worthwhile", "examiner": "examiner_1"}
    )
    assert response.status_code == 200
```

---

## 8. How to Run

### Quick Start

```bash
source venv/bin/activate
python scripts/demo.py
# Open http://localhost:8000/dashboard/
```

### Step by Step

```bash
python scripts/generate_sample_data.py      # Generate data
python scripts/run_pipeline.py --cses 50    # Run pipeline
uvicorn src.api.main:app --reload           # Start server
python scripts/run_validation.py            # Validate
```

### Running Tests

```bash
pytest tests/test_reasoning_quality.py -v   # Fast (20 tests)
pytest tests/test_signal_engine.py -v      # Signal engine
pytest tests/test_api.py -v                # API
pytest tests/ -q                           # Full suite (~8 min)
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/ingest/upload` | POST | Upload CSV/JSON |
| `/api/profiles/{cse_id}` | GET | Behavioral profile |
| `/api/findings` | GET | All findings |
| `/api/portfolio/rankings` | GET | Ranked CSEs |
| `/api/feedback/summary` | GET | Feedback summary |
| `/api/report/{cse_id}` | GET | Download report |
| `/api/analytics/run` | POST | Run pipeline |

---

## 9. Key Architecture Decisions

| Decision | Why |
|----------|-----|
| SQLite over PostgreSQL | Zero-config, file-based, air-gap ready |
| Jinja2 over React | No build step, no Node.js, offline |
| Deterministic analytics over ML | Auditability, no training data, explainable |
| LLM optional | System works fully without LLM |
| Envelope response format | Consistent client handling |
| Adapter pattern for ingestion | New formats without changing analytics |

---

## 10. Seeded Weaknesses (Demo Dataset)

| CSE | Scenario | Signals |
|-----|----------|---------|
| CSE-042 | Investigation depth 70% decline | `quality_degradation`, `temporal_drift` |
| CSE-017 | Superficial closures + no escalation | `superficial_closure` |
| CSE-089 | Zero endpoint alerts | `missing_alert_categories` |
| CSE-031 | Missing investigations on critical | `missing_investigations` |
| CSE-055 | Closure velocity 3σ faster | `closure_velocity_outlier` |
| CSE-073 | No weekend escalations | `escalation_absence` |
| CSE-019 | Templated investigations | `template_investigation` |
| CSE-061 | Combined weaknesses | `investigation_depth_outlier` |
| CSE-037 | Shallow reasoning | `shallow_justification`, `template_notes` |

---

*Last updated: 2026-08-27*
