# SAT-SA — Updates & Next Steps

**Last updated:** 2026-08-25  
**Current status:** Documentation complete — source code not started  
**Active file:** `phases.md`

---

## Current State

| Layer | Status | Notes |
|-------|--------|-------|
| Problem understanding | ✅ Complete | Mapped every PS requirement |
| Architecture design | ✅ Complete | README Section 6, phases.md |
| Analytics methodology | ✅ Complete | 18+ signals across 4 categories |
| Data schema | ✅ Canonical schema defined | Phase 1 |
| Implementation plan | ✅ Complete | 15 phases, START.md quick-reference |
| Source code | ❌ **Zero** | No `.py` files written yet |
| Prototype | ❌ **None** | Nothing runnable |
| Demo | ❌ **Nothing** | No demo script executed |

---

## Immediate Next Steps (in order)

### 1. Execute Phase 0 — Project Bootstrap

**What to do:**
- Create directory structure (`src/`, `data/`, `tests/`, etc.)
- Create `requirements.txt`
- Create `Makefile`
- Create `.gitignore`
- Create minimal `src/api/main.py` with `/health` endpoint
- Run `make setup && make run && curl localhost:8000/health`

**Time:** 30 minutes  
**File:** `START.md` → Phase 0 section

**Commands:**
```bash
mkdir -p src/ingestion src/analytics src/evidence src/api src/dashboard/templates src/dashboard/static/css src/dashboard/static/js
mkdir -p data/schemas data/samples data/config tests docs scripts
touch src/__init__.py src/ingestion/__init__.py src/analytics/__init__.py src/evidence/__init__.py src/api/__init__.py src/dashboard/__init__.py
```

---

### 2. Execute Phase 1 — Canonical Data Schema

**What to do:**
- Create `src/analytics/schemas.py`
- Define 7 Pydantic models: `CSEMetadata`, `Alert`, `Investigation`, `Escalation`, `Case`, `Asset`, `Dataset`
- All fields Optional with None defaults
- Enum validators for severity/status
- Timestamp ordering validators
- `Dataset.to_pandas()` method

**Time:** 1 hour

---

### 3. Execute Phase 2 — Synthetic Data Generator

**What to do:**
- Create `scripts/generate_sample_data.py`
- Generate 50 CSEs × 4 quarters × ~500 alerts = ~100K alerts
- Seed 8 specific weaknesses (CSE-042, CSE-017, CSE-089, CSE-031, CSE-055, CSE-073, CSE-019, CSE-061)
- Output: 6 CSV files in `data/samples/demo_dataset/`

**Time:** 2–3 hours

---

### 4. Execute Phase 3 — Ingestion Layer

**What to do:**
- Create `src/ingestion/adapters.py` (BaseAdapter, CSVAdapter, JSONAdapter, JSONLAdapter)
- Create `src/ingestion/mapper.py` (column name mapping)
- Create `src/ingestion/normalizer.py` (raw dicts → Pydantic models)
- Create `src/ingestion/quality.py` (data quality scoring)
- Create `src/ingestion/pipeline.py` (orchestrate: parse → map → normalize → quality → store)

**Time:** 2–3 hours

---

### 5. Execute Phase 4 — Behavioral Profiler

**What to do:**
- Create `src/analytics/profiler.py`
- Compute 20+ metrics per CSE per period
- Handle missing data gracefully (0.0 + warning)
- Store in SQLite

**Time:** 2–3 hours

---

### 6. Execute Phase 5 — Supervisory Signal Engine (CRITICAL)

**What to do:**
- Create `src/analytics/execution_gaps.py` (5 signals)
- Create `src/analytics/negative_space.py` (5 signals)
- Create `src/analytics/behavioral_anomalies.py` (5 signals)
- Create `src/analytics/benchmarking.py` (3 peer deviation signals)
- Create `src/analytics/config.py` (threshold loader)
- Each signal: pure function returning `Optional[Finding]`
- All 8 seeded weaknesses must be detected

**Time:** 3–4 hours  
**Priority:** HIGHEST — this is the core value of SAT-SA

---

### 7. Execute Phase 6 — Evidence Tracer

**What to do:**
- Create `src/evidence/tracer.py`
- Build `Finding → Signal → Metric → Records` chain
- Every finding includes `contributing_record_ids`
- Missing records noted explicitly

**Time:** 1–2 hours

---

### 8. Execute Phases 7–8 — Peers + Scoring

**What to do:**
- Peer grouping by `(sector, size_band)`
- Z-scores + percentiles
- Supervisory Attention Score: `0.4×confidence + 0.3×severity + 0.3×diversity`

**Time:** 2–3 hours

---

### 9. Execute Phase 10 — FastAPI Backend

**What to do:**
- Create `src/api/main.py` (app factory)
- Create `src/api/routes.py` (15+ endpoints)
- Create `src/api/models.py` (Pydantic request/response)
- All endpoints serve JSON

**Time:** 2–3 hours

---

### 10. Execute Phase 11 — Dashboard

**What to do:**
- Create `src/dashboard/templates/base.html` (layout)
- Create `src/dashboard/templates/portfolio.html` (rankings table)
- Create `src/dashboard/templates/entity.html` (profile + findings)
- Create `src/dashboard/templates/finding.html` (evidence drill-down)
- Create `src/dashboard/static/css/style.css`
- Create `src/dashboard/static/js/app.js`
- Chart.js for peer comparison charts

**Time:** 3–4 hours

---

### 11. Execute Phase 12 — Integration

**What to do:**
- Create `scripts/run_pipeline.py`
- One-command: ingest → profile → analyze → find → prioritize → display
- Verify all 8 seeded weaknesses detected end-to-end

**Time:** 1–2 hours

---

### 12. Execute Phases 13–14 — Validation + Demo

**What to do:**
- Create `scripts/run_validation.py`
- Measure coverage, precision, recall against seeded weaknesses
- Write `docs/validation_report.md`
- Rehearse 2-minute demo script from `START.md`

**Time:** 2–3 hours

---

## Priority Order (if time is limited)

If you only have **10 hours**, build in this order:

| Order | Phase | What | Time |
|-------|-------|------|------|
| 1 | Phase 0 | Bootstrap | 30 min |
| 2 | Phase 1 | Schemas | 1 hour |
| 3 | Phase 2 | Synthetic data | 2 hours |
| 4 | Phase 5 | Signal engine | 3 hours |
| 5 | Phase 10 | FastAPI backend | 1.5 hours |
| 6 | Phase 11 | Dashboard | 2 hours |

**Total: ~10 hours** → You have a working prototype that ingests data, detects findings, and displays them.

---

## Risks & Blockers

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Time shortage | Can't complete all phases | Follow priority order above — minimum demo in 10 hours |
| Scope creep | Adding post-MVP features too early | Strictly follow phases; post-MVP is Phase 15 |
| Synthetic data too fake | Judges see through it | Use realistic correlations (severity → investigation depth → escalation) |
| Over-reliance on LLM | LLM not installed at judging venue | Phase 9 is optional; all analytics work without LLM |
| Dashboard too complex | Demo fails | Keep it simple: 3 views (portfolio, entity, finding) with vanilla JS |

---

## What NOT to Do

- Do NOT install PostgreSQL — SQLite is sufficient
- Do NOT install Docker — `python -m venv` is enough
- Do NOT use React — Jinja2 + vanilla JS
- Do NOT use Node.js — no frontend build step
- Do NOT call thresholds "NCIIPC standards" — they are configurable heuristics
- Do NOT claim the score is a "risk rating" — it is a prioritization tool
- Do NOT train an LLM — use optional local Ollama for explanation only
- Do NOT implement all 18 signals at once — start with 5 core signals

---

## Key Reminders

- **The signal engine (Phase 5) is the core value.** Everything else is plumbing.
- **Every finding must trace to records.** This is the differentiator.
- **Synthetic data must be realistic.** Correlated, not random.
- **Missing data must be handled.** It is not a finding; it is a data-quality note.
- **The system must run offline.** No internet, no cloud, no external APIs at demo time.
- **Keep it simple.** Judges prefer a working simple prototype over a broken complex one.

---

*Update this file after each phase is completed. Mark phases as ✅ when done.*
