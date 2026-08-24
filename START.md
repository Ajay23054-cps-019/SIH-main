# SAT-SA — Start Here

**Last updated:** 2026-08-24  
**Current status:** Phases 0–14 complete — full pipeline, API, dashboard,
validation harness, and demo materials. Suite: **276+ tests passing**.
Validation: 8/8 seeded weaknesses detected, 0 HIGH false alarms
(`docs/validation_report.md`).  
**Next action:** Demo rehearsal (`make demo`, script in
`docs/demo_script.md`) or post-MVP phases in `phases.md`.

## Quick commands

```bash
make setup        # venv + deps
make data         # generate demo CSVs (seed 42)
make pipeline     # ingest → profile → signals → peers → ranking
make validate     # validation harness → docs/validation_report.md
make demo         # rebuild store, then serve dashboard at :8000/dashboard/
make test         # full test suite
```

---

## Original Build Plan (reference)

The phase-by-phase build order below was executed sequentially; each
phase's acceptance criteria are covered by tests under `tests/`.

## Immediate Execution Order

Follow these phases in order. Do not skip ahead.

| Order | Phase | What you build | Est. time |
|-------|-------|---------------|-----------|
| 1 | Phase 0 | Project skeleton, venv, Makefile, `.gitignore` | 30 min |
| 2 | Phase 1 | Canonical Pydantic schemas for all entities | 1 hour |
| 3 | Phase 2 | Synthetic data generator with 8 seeded weaknesses | 2–3 hours |
| 4 | Phase 3 | Ingestion adapters (CSV/JSON/JSONL) + quality scorer | 2–3 hours |
| 5 | Phase 4 | Behavioral profiler (20+ metrics) | 2–3 hours |
| 6 | Phase 5 | Supervisory signal engine (15+ signals) | 3–4 hours |
| 7 | Phase 6 | Evidence tracer | 1–2 hours |
| 8 | Phase 7 | Peer benchmarking | 1–2 hours |
| 9 | Phase 8 | Supervisory Attention Score | 1 hour |
| 10 | Phase 9 | LLM explanation layer (optional) | 1–2 hours |
| 11 | Phase 10 | FastAPI backend | 2–3 hours |
| 12 | Phase 11 | Jinja2 + vanilla JS dashboard | 3–4 hours |
| 13 | Phase 12 | End-to-end integration | 1–2 hours |
| 14 | Phase 13 | Validation harness | 1–2 hours |
| 15 | Phase 14 | Demo script + rehearsal | 1–2 hours |

**Total estimated effort:** 25–35 hours for a solo developer, 15–20 hours for a pair.

---

## Phase 0: Project Bootstrap

### Step 0.1: Create directory structure

Run these commands in `/home/ajay/Desktop/SIH/`:

```bash
mkdir -p src/ingestion src/analytics src/evidence Api src/dashboard/templates src/dashboard/static/css src/dashboard/static/js
mkdir -p data/schemas data/samples data/config
mkdir -p tests docs scripts
touch src/__init__.py src/ingestion/__init__.py src/analytics/__init__.py src/evidence/__init__.py src/api/__init__.py src/dashboard/__init__.py
```

### Step 0.2: Create `.gitignore`

```gitignore
venv/
__pycache__/
*.pyc
.env
*.db
data/samples/*.csv
.pytest_cache/
```

### Step 0.3: Create `requirements.txt`

```
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
pydantic>=2.0.0
pandas>=2.0.0
numpy>=1.24.0
scipy>=1.10.0
scikit-learn>=1.3.0
sqlalchemy>=2.0.0
aiosqlite>=0.19.0
python-dotenv>=1.0.0
pytest>=7.4.0
pytest-asyncio>=0.21.0
jinja2>=3.1.0
python-multipart>=0.0.6
```

### Step 0.4: Create `Makefile`

```makefile
.PHONY: setup test run clean

setup:
	python3 -m venv venv
	. venv/bin/activate && pip install -r requirements.txt
	@echo "Run: . venv/bin/activate"

test:
	. venv/bin/activate && pytest tests/ -v

run:
	. venv/bin/activate && uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache/
```

### Step 0.5: Create `.env.example`

```
DATABASE_URL=sqlite+aiosqlite:///./data/sat_sa.db
SECRET_KEY=change-me-in-production
LOG_LEVEL=INFO
LLM_ENABLED=false
LLM_ENDPOINT=http://localhost:11434/api/generate
LLM_MODEL=llama3:8b
```

### Step 0.6: Create minimal `src/api/main.py`

```python
from fastapi import FastAPI

app = FastAPI(title="SAT-SA", version="0.1.0")

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}
```

### Step 0.7: Verify

```bash
make setup
make run
curl http://localhost:8000/health
# Should return: {"status":"ok","version":"0.1.0"}
```

### Acceptance Criteria

- [ ] Directory structure created
- [ ] `make setup` completes without errors
- [ ] `curl localhost:8000/health` returns `{"status":"ok"}`
- [ ] `make test` passes (no tests yet — that is fine)

---

## Phase 1: Canonical Data Schema

### What to build

`src/analytics/schemas.py` — All Pydantic models in one file.

### Models to define

1. `CSEMetadata`
2. `Alert`
3. `Investigation`
4. `Escalation`
5. `Case`
6. `Asset`
7. `Dataset` (container holding lists of all the above)

### Key rules

- Every field is `Optional` with `None` default
- Add enum validators for `severity` and `status`
- Add timestamp ordering validator (open < close)
- `Dataset.to_pandas()` returns Dict[str, pd.DataFrame]

### Acceptance Criteria

- [ ] All 7 models defined
- [ ] Models validate correctly with sample data
- [ ] Models accept missing fields without crashing
- [ ] `Dataset.to_pandas()` returns clean DataFrames

### Validation command

```bash
python -c "
from src.analytics.schemas import Alert, Dataset
a = Alert(alert_id='A1', cse_id='C1')
print('Alert OK:', a)
d = Dataset(alerts=[a])
df = d.to_pandas()
print('DataFrame OK:', df['alerts'].shape)
"
```

---

## Phase 2: Synthetic Data Generator

### What to build

`scripts/generate_sample_data.py` — CLI script that writes 6 CSV files.

### Data volumes

- 50 CSEs (20 Telecom, 15 Finance, 15 Power)
- ~500 alerts/CSE/quarter × 4 quarters = ~100K alerts
- ~80K investigations, ~10K escalations, ~50K cases
- ~15K assets

### Seeded weaknesses (MUST be discoverable without hardcoding IDs)

| CSE | Weakness | How to seed |
|-----|----------|-------------|
| CSE-042 | Investigation depth 70% decline over 4Q | Decrease `evidence_entries` by quarter |
| CSE-017 | Superficial closure + no escalation | Fast closure, shallow depth, 0% escalation on critical |
| CSE-089 | Missing endpoint telemetry | 0 alerts with category=endpoint despite 500+ endpoints |
| CSE-031 | Missing investigations on critical alerts | 95% of HIGH/CRITICAL have no investigation |
| CSE-055 | Closure velocity 3σ faster | Multiply closure time by 0.1 |
| CSE-073 | No weekend escalations | Force escalation timestamps to weekdays only |
| CSE-019 | Templated investigations | Set notes to 1 of 5 template strings |
| CSE-061 | Combined: shallow + fast + no escalation | Multiple seeded issues |

### Acceptance Criteria

- [ ] `python scripts/generate_sample_data.py` runs without errors
- [ ] 6 CSV files produced in `data/samples/demo_dataset/`
- [ ] All 8 weaknesses present and detectable
- [ ] Reproducible with `--seed 42`

---

## Phase 3: Format-Agnostic Ingestion

### What to build

| File | Purpose |
|------|---------|
| `src/ingestion/adapters.py` | BaseAdapter + CSVAdapter + JSONAdapter + JSONLAdapter |
| `src/ingestion/mapper.py` | Column name mapping (handle `alert_id` = `id` = `EventID` etc.) |
| `src/ingestion/normalizer.py` | Convert raw dicts → canonical Pydantic models |
| `src/ingestion/quality.py` | Data quality report (completeness, orphans, schema mismatches) |
| `src/ingestion/pipeline.py` | Orchestrate: parse → map → normalize → quality check → store |

### Acceptance Criteria

- [ ] CSV adapter parses all 6 sample files
- [ ] JSON adapter parses nested and flat JSON
- [ ] Column mapper handles ≥3 naming variations per field
- [ ] Quality score computed (0.0–1.0) with warnings list
- [ ] Pipeline stores normalized data in SQLite
- [ ] 85%+ test coverage

---

## Phase 4: Behavioral Profiler

### What to build

`src/analytics/profiler.py` — Per-CSE, per-period metrics.

### Minimum metrics (20+)

Alert: `volume_total`, `severity_distribution`, `category_distribution`, `density`  
Investigation: `rate`, `depth_mean`, `depth_median`, `duration_p50`, `duration_p90`, `closure_velocity_mean`  
Escalation: `rate`, `rate_by_severity`, `followthrough_rate`  
Evidence: `completeness_score`  
Temporal: `diurnal_distribution`, `weekly_distribution`

### Acceptance Criteria

- [ ] Profiles computed for all 50 CSEs × 4 quarters
- [ ] 20+ metrics per profile
- [ ] Missing data handled gracefully (returns 0.0 + warning)
- [ ] Stored in SQLite
- [ ] 85%+ test coverage

---

## Phase 5: Supervisory Signal Engine

### Signal categories to implement

**Execution Gaps (5 signals):**
- `superficial_closure`
- `escalation_without_action`
- `quality_degradation`
- `severity_mismatch`
- `template_investigation`

**Negative Space (5 signals):**
- `alert_volume_gap`
- `missing_investigations`
- `missing_alert_categories`
- `telemetry_absence`
- `escalation_absence`

**Behavioral Anomalies (5 signals):**
- `temporal_drift`
- `unusual_quiet_period`
- `bulk_closure_pattern`
- `shift_variance`
- `recurring_incident`

**Peer Deviation (3 signals):**
- `closure_velocity_outlier`
- `investigation_depth_outlier`
- `escalation_rate_outlier`

### Acceptance Criteria

- [ ] Each signal is a pure function returning `Optional[Finding]`
- [ ] All 8 seeded weaknesses detected
- [ ] Each finding includes contributing record IDs
- [ ] Each finding includes data-quality notes
- [ ] Configurable thresholds from `data/config/thresholds.json`
- [ ] 85%+ test coverage

---

## Phase 6–8: Evidence, Peers, Scoring

Quick summaries — full details in `phases.md`.

### Phase 6: Evidence Tracer
- `src/evidence/tracer.py` — Build `Finding → Signal → Metric → Records` chain
- Every finding includes `contributing_record_ids` and `detection_logic`
- Missing records noted explicitly

### Phase 7: Peer Benchmarking
- `src/analytics/benchmarking.py` — Rule-based grouping by `(sector, size_band)`
- Z-scores + percentiles for key metrics
- Outlier flag at `|z| > 2.5`
- Minimum group size: 3

### Phase 8: Supervisory Attention Score
- `src/analytics/scoring.py` — Transparent weighted formula
- `0.4×confidence + 0.3×severity + 0.3×diversity`
- Normalized to 0–100
- All components visible in API response

---

## Phase 9–14: LLM, API, Dashboard, Integration, Validation, Demo

These phases build the presentation layer on top of the analytics core.

| Phase | What | Key constraint |
|-------|------|----------------|
| 9 | Local LLM explainer | OPTIONAL — system works without it |
| 10 | FastAPI backend | All endpoints serve JSON |
| 11 | Jinja2 + vanilla JS dashboard | NO React, NO Node.js |
| 12 | End-to-end integration | Pipeline script runs start-to-finish |
| 13 | Validation harness | Coverage ≥ 70%, precision ≥ 60% |
| 14 | Demo preparation | ≤2 minutes, rehearsed, backup screenshots |

---

## Recommended Execution Strategy

If working alone: execute Phase 0 → 1 → 2 → 3 in the first session (≈6–8 hours).

If working in pairs: one person does Phase 0+1, the other does Phase 2 in parallel, then merge and continue.

**Do not start Phase 5 until Phases 0–4 are complete and tested.**

The signal engine depends on clean profiles. Profiles depend on clean ingestion. Ingestion depends on a clean schema. Chain of dependency is strict.

---

## Files to Create (Complete List)

```
src/__init__.py
src/ingestion/__init__.py
src/analytics/__init__.py
src/evidence/__init__.py
src/api/__init__.py
src/dashboard/__init__.py
src/analytics/schemas.py
src/analytics/sample_data.py
src/analytics/profiler.py
src/analytics/execution_gaps.py
src/analytics/negative_space.py
src/analytics/behavioral_anomalies.py
src/analytics/benchmarking.py
src/analytics/scoring.py
src/analytics/config.py
src/ingestion/adapters.py
src/ingestion/mapper.py
src/ingestion/normalizer.py
src/ingestion/quality.py
src/ingestion/pipeline.py
src/evidence/tracer.py
src/evidence/findings.py
src/evidence/reporter.py
src/api/main.py
src/api/routes.py
src/api/models.py
src/api/errors.py
src/dashboard/routes.py
src/dashboard/templates/base.html
src/dashboard/templates/portfolio.html
src/dashboard/templates/entity.html
src/dashboard/templates/finding.html
src/dashboard/static/css/style.css
src/dashboard/static/js/app.js
data/config/thresholds.json
data/config/peer_groups.json
tests/conftest.py
tests/test_schemas.py
tests/test_ingestion.py
tests/test_profiler.py
tests/test_signals.py
tests/test_api.py
tests/test_integration.py
scripts/generate_sample_data.py
scripts/run_pipeline.py
scripts/run_validation.py
```

---

*This file is the quick-reference start guide. Full implementation details are in `phases.md`.*
