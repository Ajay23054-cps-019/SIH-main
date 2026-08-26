# SAT-SA Implementation Plan

**Project:** SAT-SA — Supervisory Analytics Tool for SOC Assessment  
**Competition:** Smart India Hackathon 2026 · SIH26157 · NCIIPC  
**Status:** MVP Complete — Enhancement Phase  
**Last updated:** 2026-08-26

---

## 1. Project Status

### What Is Complete

| Component | Status | Tests |
|-----------|--------|-------|
| Data ingestion (CSV/JSON/JSONL) | Done | 28 |
| Data quality assessment | Done | — |
| Behavioral profiling (20+ metrics) | Done | 33 |
| Execution gap detection (5 signals) | Done | — |
| Negative space detection (5 signals) | Done | — |
| Behavioral anomaly detection (5 signals) | Done | — |
| Peer benchmarking (3 signals) | Done | 42 |
| Supervisory Attention Score | Done | 16 |
| Evidence tracing (finding → records) | Done | 17 |
| Signal fusion (supervisory cases) | Done | — |
| FastAPI backend (20+ endpoints) | Done | 43 |
| Dashboard (portfolio/entity/finding) | Done | 8 |
| Examiner feedback loop | Done | 14 |
| Report generation (HTML) | Done | — |
| File upload (CSV/JSON/JSONL) | Done | — |
| Synthetic data generator (50 CSEs) | Done | 30+ |
| **Total** | | **337 passed** |

### Validation Results

| Metric | Result | Target |
|--------|--------|--------|
| Coverage | 100% (8/8) | ≥ 70% |
| Precision | 100% | ≥ 60% |
| False-positive rate | 0% | < 40% |
| Examiner alignment | 0.909 | ≥ 0.70 |

---

## 2. Our Approach: Hybrid Supervisory Analytics

### Core Philosophy

> **We don't detect hackers. We detect SOCs that are going through the motions — with evidence.**

Three principles differentiate us:

1. **Supervisory, not operational** — We audit SOCs, not detect threats
2. **Evidence, not AI** — Deterministic, traceable analytics; every finding → specific records
3. **Negative space, not just anomaly** — We find what's missing, not just what's unusual

### The Hybrid Engine

```
RAW SOC DATA
    ↓
DATA QUALITY ASSESSMENT
    ↓
BEHAVIORAL PROFILING (20+ metrics per CSE per period)
    ↓
SUPERVISORY SIGNAL DETECTION (22 signals, 5 categories)
    ├── Execution Gaps (5 signals) — claimed ≠ observed
    ├── Negative Space (5 signals) — expected ≠ present
    ├── Behavioral Anomalies (5 signals) — normal ≠ current
    ├── Peer Deviation (3 signals) — entity ≠ peers
    └── Reasoning Quality (4 signals) — justification depth analysis [PLANNED]
    ↓
EVIDENCE TRACING (every finding → specific records)
    ↓
SUPERVISORY ATTENTION PRIORITIZATION (transparent scoring)
    ↓
EXAMINER REVIEW → FEEDBACK LOOP (system learns, human decides)
```

---

## 3. Architecture

### Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Backend | Python + FastAPI | Offline-first, auto-documented API |
| Database | SQLite | Zero-config, file-based, air-gap ready |
| Analytics | Pandas + NumPy + SciPy | Statistical analysis, no ML training needed |
| Frontend | Jinja2 + vanilla JS + Chart.js | No build step, no Node.js, offline |
| Reports | Jinja2 HTML → print-to-PDF | Self-contained, no external deps |
| LLM (optional) | Ollama local runtime | Explanation layer only, not required |

### Directory Structure

```
SIH/
├── src/
│   ├── ingestion/          # Adapters, normalizer, quality scorer, pipeline
│   ├── analytics/          # Profiler, signal engine, benchmarking, scoring
│   ├── evidence/           # Tracer, findings, LLM explainer
│   ├── api/                # FastAPI app, routes, models, errors
│   └── dashboard/          # Jinja2 templates, static assets
├── data/
│   ├── samples/demo_dataset/  # 6 CSV files (50 CSEs, 243K records)
│   └── config/             # thresholds.json, peer_groups.json
├── tests/                  # 337 tests across 18 files
├── scripts/                # Pipeline, validation, demo launcher
├── docs/                   # Demo script, validation report, screenshots
├── requirements.txt        # Python dependencies
└── Makefile                # setup, test, run, clean
```

---

## 4. Signal Catalog (22 Signals)

### Execution Gaps (5)

| Signal | Description | Detection Method |
|--------|-------------|------------------|
| `superficial_closure` | Fast closure + shallow investigation | Closure velocity + depth correlation |
| `escalation_without_action` | Escalation logged but no follow-through | Escalation → follow-up evidence check |
| `quality_degradation` | Investigation depth declining over time | Change-point detection on depth series |
| `severity_mismatch` | High-severity alerts closed as benign | Severity vs. depth vs. closure time |
| `kpi_divergence` | Metrics improve while quality declines | KPI trend vs. operational quality trend |

### Negative Space (5)

| Signal | Description | Detection Method |
|--------|-------------|------------------|
| `alert_volume_gap` | Expected alerts vs. observed | Bayesian expected volume model |
| `missing_investigations` | High-severity alerts without investigation | Severity → investigation record check |
| `missing_alert_categories` | Expected alert types absent | Inventory-to-alert mapping |
| `telemetry_absence` | Critical assets producing no alerts | Asset criticality → alert presence |
| `escalation_absence` | Alerts meeting criteria but not escalated | Severity → escalation record check |

### Behavioral Anomalies (5)

| Signal | Description | Detection Method |
|--------|-------------|------------------|
| `temporal_drift` | Sudden change in investigation depth | CUSUM/PELT change-point detection |
| `unusual_quiet_period` | No alerts during expected active hours | Temporal gap detection |
| `bulk_closure_pattern` | Mass closures on specific days/times | Daily closure distribution anomaly |
| `shift_variance` | Quality differs across shifts | Hour-of-day coherence variance |
| `recurring_incident` | Same alert pattern repeats without resolution | Alert recurrence + case reopen check |

### Peer Deviation (3)

| Signal | Description | Detection Method |
|--------|-------------|------------------|
| `closure_velocity_outlier` | Closure speed ≠ peers | Z-score vs. peer group |
| `investigation_depth_outlier` | Investigation depth ≠ peers | Z-score vs. peer group |
| `escalation_rate_outlier` | Escalation rate ≠ peers | Z-score vs. peer group |

### Reasoning Quality (4) — PLANNED

| Signal | Description | Detection Method |
|--------|-------------|------------------|
| `shallow_justification` | High-severity alerts with minimal notes | Word count + keyword analysis |
| `template_notes` | Identical investigation notes across cases | Linguistic similarity detection |
| `missing_escalation_rationale` | Escalated cases without documented rationale | Escalation → note presence check |
| `reasoning_inflation` | Claims actions not evidenced in notes | Keyword claims vs. evidence markers |

---

## 5. Implementation Timeline

### Phase 1: MVP (COMPLETE)

| Week | Deliverable | Status |
|------|-------------|--------|
| 1 | Project bootstrap, schema design, synthetic data | Done |
| 2 | Ingestion pipeline, profiling engine | Done |
| 3 | Signal engine (22 signals), benchmarking | Done |
| 4 | Evidence tracing, scoring, API | Done |
| 5 | Dashboard, feedback loop, reports | Done |
| 6 | Validation, demo prep, documentation | Done |

### Phase 2: Enhancement (CURRENT)

| Task | Effort | Priority |
|------|--------|----------|
| Reasoning Quality layer (4 signals) | 2 days | High |
| Investigation notes in synthetic data | 1 day | High |
| Enhanced demo script with reasoning | 0.5 day | High |
| Backup screenshots for all views | 0.5 day | Medium |
| Final documentation update | 1 day | Medium |

### Phase 3: Submission (PENDING)

| Task | Effort | Priority |
|------|--------|----------|
| Demo video recording (2 min) | 1 day | High |
| Presentation slides (5 slides) | 1 day | High |
| Final rehearsal | 0.5 day | High |
| Submission package assembly | 0.5 day | Medium |

---

## 6. Reasoning Quality Layer — Implementation Plan

### 6.1 Overview

The Reasoning Quality layer analyzes the **justification content** in SOC investigation notes to detect execution gaps that statistical analysis cannot see.

**Core insight:** An alert closed quickly with detailed technical reasoning is different from an alert closed quickly with "checked." Both are statistically identical. Operationally, they are worlds apart.

### 6.2 Components

#### A. Justification Parser
- Extract investigation notes, escalation rationale, closure notes from case records
- Handle free-text, semi-structured, and empty notes
- Tokenize into reasoning fragments

#### B. Semantic Classifier
- Rule-based classification (no ML needed):
  - **Technical depth**: invokes specific tools, techniques, technical knowledge
  - **Evidence-based**: references artifacts (logs, network data, asset properties)
  - **Procedural**: cites policy, procedure, runbook
  - **Template**: boilerplate language, minimal variation
  - **Absent**: no notes recorded
- Depth scoring: 1 (absent) to 5 (technical depth)

#### C. Coherence Scorer
```
Coherence = Σ(depth_score × relevance_weight) / alert_severity
```
- High-severity alerts should have deep reasoning
- Low-severity alerts can have lighter reasoning
- Peer-relative: compare to entity's own baseline

#### D. Pattern Detector
- **Reasoning consistency**: same alert type → reasoning variance (low = thoughtful; very high = template)
- **Reasoning inflation**: claims actions not evidenced in notes
- **Escalation justification delta**: escalated cases should have deeper reasoning
- **Negative space in reasoning**: absence of expected justification types

### 6.3 New Signals

| Signal | Trigger | Finding |
|--------|---------|---------|
| `shallow_justification` | High-severity + notes < 20 words + no technical keywords | "Critical alert closed with minimal investigation notes" |
| `template_notes` | >80% identical notes across same alert type | "Investigation notes are template-driven" |
| `missing_escalation_rationale` | Escalated case without documented rationale | "Case escalated without justification" |
| `reasoning_inflation` | Claims TI lookup, asset verification without references | "Investigation claims actions not evidenced in notes" |

### 6.4 Synthetic Data Extension

Extend `generate_dataset()` to produce investigation notes with varying quality:

```python
# High-quality notes (detailed technical reasoning)
"Verified source IP {ip} against asset registry. Confirmed activity expected "
"per maintenance window (ticket #{ticket}). Checked event logs for suspicious "
"patterns—none detected. Cross-referenced threat intelligence—no known IOCs."

# Template notes (boilerplate)
"Checked. Benign."

# Absent notes (empty)
""
```

Seed specific CSEs with poor reasoning quality to validate detection.

### 6.5 Dashboard Integration

- **Entity view**: Add "Investigation Depth" metric card
- **Finding view**: Show "Reasoning Certificate" — alert metadata + recorded justification + coherence score
- **Portfolio view**: Add "Reasoning Quality" column to rankings

---

## 7. API Endpoints

### Existing (20+ endpoints)

```
GET    /health
POST   /api/ingest/upload
GET    /api/ingest/status/{cse_id}
GET    /api/ingest/quality/{cse_id}
GET    /api/profiles/{cse_id}?period=2024-Q1
GET    /api/profiles/{cse_id}/trends?metric=investigation_depth&periods=4
GET    /api/profiles/compare?cse_ids=CSE-042,CSE-017&period=2024-Q1
GET    /api/findings?cse_id=CSE-042&severity=HIGH
GET    /api/findings/{finding_id}
GET    /api/findings/{finding_id}/explain
GET    /api/findings/execution-gaps
GET    /api/findings/negative-space
GET    /api/findings/behavioral-anomalies
GET    /api/findings/peer-deviations
GET    /api/portfolio/rankings
GET    /api/portfolio/summary
GET    /api/peers/{cse_id}
GET    /api/peers/compare?cse_ids=CSE-042,CSE-017
GET    /api/cases?cse_id=CSE-042
GET    /api/cases/{case_id}
GET    /api/feedback/summary
GET    /api/findings/{finding_id}/feedback
POST   /api/findings/{finding_id}/feedback
GET    /api/report/{cse_id}
POST   /api/analytics/run
GET    /api/analytics/status/{job_id}
```

### New (for Reasoning Quality)

```
GET    /api/findings/reasoning-quality        # New signal category
GET    /api/profiles/{cse_id}/reasoning-depth # Per-period reasoning metrics
```

---

## 8. Validation Strategy

### Seeded Weakness Detection

| CSE | Weakness | Expected Signal | Status |
|-----|----------|-----------------|--------|
| CSE-042 | Investigation depth 70% decline | `quality_degradation`, `temporal_drift` | Detected |
| CSE-017 | Superficial closure + no escalation | `superficial_closure` | Detected |
| CSE-089 | Missing endpoint telemetry | `missing_alert_categories` | Detected |
| CSE-031 | Missing investigations on critical | `missing_investigations` | Detected |
| CSE-055 | Closure velocity 3σ faster | `closure_velocity_outlier` | Detected |
| CSE-073 | No weekend escalations | `escalation_absence` | Detected |
| CSE-019 | Templated investigations | `template_investigation` | Detected |
| CSE-061 | Combined weaknesses | `investigation_depth_outlier` | Detected |

### Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Coverage | 100% (8/8) | ≥ 70% |
| Precision | 100% | ≥ 60% |
| False-positive rate | 0% | < 40% |
| Examiner alignment | 0.909 | ≥ 0.70 |

---

## 9. Risk Register

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Reasoning extraction noisy (different CSE documentation standards) | Medium | Medium | Treat "absent" as signal; model documentation completeness separately |
| Keyword dictionaries incomplete | Medium | Medium | Build iteratively; examiner feedback loop to improve |
| Coherence scoring subjective | Low | Medium | Relative to entity's own baseline, not absolute thresholds |
| Template-driven work flagged incorrectly | Low | Low | Combine with outcome validation (re-escalation check) |
| Demo timing exceeds 2 minutes | Medium | High | Script tightly; backup screenshots ready |
| Judge asks about AI/ML | Low | Medium | Emphasize deterministic analytics; LLM is optional explanation layer |

---

## 10. Key Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-08-24 | SQLite instead of PostgreSQL | Zero-config, file-based, air-gap ready |
| 2026-08-24 | Jinja2 + vanilla JS instead of React | No build step, no Node.js, fully offline |
| 2026-08-24 | Deterministic analytics, not black-box ML | Auditability, explainability, no training data needed |
| 2026-08-24 | LLM as optional explanation layer only | System works fully without LLM |
| 2026-08-25 | Supervisory lens (not SOC replacement) | NCIIPC has SOCs; needs to audit them |
| 2026-08-25 | Evidence chain tracing (finding → records) | Core differentiator for auditability |
| 2026-08-25 | Examiner feedback loop (advisory only) | System learns without auto-applying changes |
| 2026-08-26 | Hybrid approach: statistical + reasoning quality | Combines proven reliability with genuine novelty |

---

## 11. Out of Scope (Enforced)

- Real-time SOC monitoring or alerting
- SIEM correlation or live event processing
- Network packet capture or analysis
- Customer data or PII processing
- Cloud deployment or SaaS features
- External API integrations
- Generic chatbot or LLM wrapper
- Compliance scoring or certification

---

## 12. Success Criteria

### Functional

- [x] Ingest structured CSE submissions (CSV/JSON/JSONL)
- [x] Compute behavioral profiles (20+ metrics)
- [x] Detect execution gaps (5 signals)
- [x] Detect negative space (5 signals)
- [x] Detect behavioral anomalies (5 signals)
- [x] Benchmark against peers (3 signals)
- [x] Generate evidence-backed findings with full traceability
- [x] Score entities with Supervisory Attention Score
- [x] Present interactive dashboard with drill-down
- [x] Support examiner feedback loop
- [x] Generate downloadable reports
- [ ] Add Reasoning Quality layer (4 signals)

### Technical

- [x] 337 tests passing
- [x] Pipeline completes in <2 minutes for 50 CSEs
- [x] No critical bugs in demo path
- [x] Fully offline operation

### Validation

- [x] Coverage ≥ 70% (achieved: 100%)
- [x] Precision ≥ 60% (achieved: 100%)
- [x] False-positive rate < 40% (achieved: 0%)
- [x] Examiner alignment ≥ 0.70 (achieved: 0.909)

---

## 13. How to Run

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run full demo (pipeline + server)
python scripts/demo.py

# Or step by step:
python scripts/load_demo_data.py    # ~45s
uvicorn src.api.main:app --reload   # start server

# Dashboard: http://localhost:8000/dashboard/
# API docs:  http://localhost:8000/docs
```

---

*Last updated: 2026-08-26*  
*Status: MVP Complete — Implementing Reasoning Quality Layer*
