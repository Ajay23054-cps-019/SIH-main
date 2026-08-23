# SAT-SA MVP

**Minimum Viable Product Definition**  
**Project:** SAT-SA — Supervisory Analytics Tool for SOC Assessment  
**Competition:** Smart India Hackathon 2026 · SIH26157 · NCIIPC  
**Status:** MVP Scope Locked

---

## 1. MVP Goal

Build a **demonstrable prototype** that proves SAT-SA's core value proposition: detecting supervisory gaps in SOC operational data that conventional dashboards and manual sampling miss.

The MVP must be **presentable to SIH judges** within the hackathon timeframe, with a working demo, clear documentation, and defensible methodology.

---

## 2. MVP Scope

### 2.1 In Scope (Must Have)

| Feature | Description | Rationale |
|---------|-------------|-----------|
| **Sample Data Generation** | Generate realistic synthetic CSE data (50 entities, 4 quarters, alerts, investigations, escalations, inventory) | Judges need to see the system working on realistic data without relying on external inputs |
| **Data Ingestion & Normalization** | Parse CSV/JSON submissions into unified schema; validate quality | Foundation for all analytics |
| **Behavioral Profiling** | Compute per-CSE profiles: alert volume, investigation depth, closure velocity, escalation rate, evidence completeness | Core input to all detection engines |
| **Execution Gap Engine (3 signals)** | Detect: (1) Superficial closures (fast closure + shallow depth), (2) Escalation without action, (3) Investigation quality degradation (temporal) | Directly addresses the "execution gap" problem statement |
| **Negative Space Engine (2 signals)** | Detect: (1) Alert volume gap (expected vs. observed), (2) Missing investigations for high-severity alerts | Directly addresses the "negative space" problem statement |
| **Expected Evidence Model** | Build CSE-specific models of "what should be observed" based on claims, assets, and history | Foundation for negative-space detection and anomaly identification |
| **Peer Benchmarking** | Simple peer grouping by sector + size; z-score and percentile comparison | Provides context for findings |
| **Supervisory Attention Score** | Weighted aggregation of detected signals into entity-level priority ranking | Directs limited review resources |
| **Finding Generation with Evidence Tracing** | Structured findings with: signal type, contributing records, detection rationale, confidence, recommended review action | Core deliverable to examiners |
| **Dashboard (3 views)** | Portfolio overview, entity deep-dive, finding detail with evidence drill-down | Judges need to see and interact with results |
| **2-Minute Demo Script** | Pre-built demo with curated data showing clear findings | Judges evaluate the demo |

### 2.2 Out of Scope for MVP (Post-MVP)

These features are planned but **not required** for the hackathon demo:

| Feature | Why Out of Scope |
|---------|-----------------|
| Temporal drift detection (change-point) | Nice-to-have but not essential for core demo; can be faked with pre-computed results |
| Signal fusion & supervisory cases | Adds complexity; individual findings are sufficient for MVP demo |
| Unsupervised pattern discovery | Novel but not required to prove core value |
| Investigation quality heuristics (NLP) | Requires ML; can be simulated with rule-based heuristics for MVP |
| KPI-reality divergence | Requires reported metrics input; not essential for core demo |
| Cyclical/temporal anomalies | Adds complexity without core demo value |
| Full explainability engine | Basic rationale per finding is sufficient for MVP |
| Report export (HTML/PDF) | Dashboard views are sufficient for demo |
| Validation harness | Synthetic data is pre-seeded with known weaknesses; formal validation can come later |
| Offline deployment packaging | Dockerfile is sufficient; full air-gap packaging is post-MVP |

---

## 3. MVP Architecture

```
┌─────────────────────────────────────────────┐
│         SAMPLE DATA (Synthetic)             │
│  50 CSEs × 4 quarters × alerts/inv/esc     │
└──────────────────┬──────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│         LAYER 1: INGESTION                  │
│  • CSV/JSON parser                          │
│  • Schema validation                        │
│  • Quality scoring                          │
└──────────────────┬──────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│         LAYER 2: PROFILING                  │
│  • Alert volume, severity distribution      │
│  • Investigation depth, closure velocity    │
│  • Escalation rate, follow-through          │
│  • Evidence completeness                    │
└──────────────────┬──────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│   LAYER 3: SUPERVISORY ANALYTICS (5 ENGINES)│
│  ┌─────────────────────────────────────┐   │
│  │ Execution Gap Engine (3 signals)    │   │
│  │ • Superficial closures              │   │
│  │ • Escalation without action         │   │
│  │ • Quality degradation (temporal)    │   │
│  └─────────────────────────────────────┘   │
│  ┌─────────────────────────────────────┐   │
│  │ Negative Space Engine (2 signals)   │   │
│  │ • Alert volume gap                  │   │
│  │ • Missing investigations            │   │
│  └─────────────────────────────────────┘   │
│  ┌─────────────────────────────────────┐   │
│  │ Peer Benchmark Engine               │   │
│  │ • Peer grouping (sector + size)     │   │
│  │ • Z-score, percentile               │   │
│  └─────────────────────────────────────┘   │
└──────────────────┬──────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│         LAYER 4: FINDINGS                   │
│  • Expected Evidence Model                  │
│  • Supervisory Attention Score              │
│  • Finding generation with evidence trace   │
│  • Priority ranking                         │
└──────────────────┬──────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│         LAYER 5: DASHBOARD (MVP)            │
│  • Portfolio overview (entity rankings)     │
│  • Entity deep-dive (profile + findings)    │
│  • Finding detail (evidence drill-down)     │
│  • Supervisory Finding Card                 │
└─────────────────────────────────────────────┘
```

---

## 4. MVP Data Model

### Required Inputs (Synthetic)

```python
# Alert
alert_id, cse_id, timestamp, severity, category, asset_id, status, closure_timestamp

# Investigation
investigation_id, alert_id, cse_id, timestamp_open, timestamp_close, 
evidence_entries (count), assigned_to, notes (text)

# Escalation
escalation_id, investigation_id, cse_id, timestamp, decision, 
has_followup (bool), recipient

# Inventory
asset_id, cse_id, asset_type, criticality, environment, sector, size_band

# CSE Metadata
cse_id, sector, size_band, claimed_capabilities
```

### Synthetic Data Design

**50 CSEs** across 3 sectors:
- Telecom (20 entities)
- Financial Services (15 entities)
- Power/Utilities (15 entities)

**Size bands:** Small (10), Medium (25), Large (15)

**4 quarters** of data (Q1-Q4 2024)

**Known weaknesses seeded** in 8-10 CSEs:
- CSE-042: Investigation depth degradation over time (70% decline)
- CSE-017: Superficial closures + no escalations for critical alerts
- CSE-089: Missing endpoint telemetry (0 endpoint alerts despite claimed EDR)
- CSE-031: High alert volume but 95% closed without investigation
- CSE-055: Peer outlier in closure velocity (3σ faster than peers)
- CSE-073: Weekend escalation gaps
- CSE-019: Template-driven investigations (high lexical similarity)
- CSE-061: KPI-reality divergence (reported 99% SLA but declining depth)

---

## 5. MVP Implementation Tasks

### Task 1: Schema & Sample Data (Days 1-3)

**Deliverable:** Unified schema + 50 CSE synthetic dataset with seeded weaknesses

**Acceptance Criteria:**
- Schema covers all required data domains
- 50 CSEs × 4 quarters × ~500 alerts/CSE/quarter = ~100K total records
- 8 CSEs have known seeded weaknesses detectable by MVP engines
- Data passes validation (no null required fields, referential integrity)

### Task 2: Ingestion & Profiling (Days 4-7)

**Deliverable:** Ingestion pipeline + behavioral profiles for all 50 CSEs

**Acceptance Criteria:**
- CSV/JSON ingestion functional
- Quality scoring returns 0-100 per submission
- Profiles computed: alert volume, severity distribution, investigation depth, closure velocity, escalation rate, evidence completeness
- Profiles stored in database

### Task 3: Execution Gap Engine (Days 8-12)

**Deliverable:** 3 detection functions producing findings

**Acceptance Criteria:**
- `detect_superficial_closures`: Flags CSEs where >30% of investigations show fast closure + shallow depth
- `detect_escalation_without_action`: Flags CSEs where >20% of escalations lack follow-up evidence
- `detect_quality_degradation`: Flags CSEs with >30% decline in investigation depth over 4 quarters
- Each finding includes: signal type, severity, confidence, contributing record IDs, detection rationale

### Task 4: Negative Space Engine (Days 13-16)

**Deliverable:** 2 detection functions producing findings

**Acceptance Criteria:**
- `detect_alert_volume_gap`: Flags CSEs where observed volume <50% of expected (based on asset count + peer baseline)
- `detect_missing_investigations`: Flags CSEs where >20% of high-severity alerts lack investigation records
- Each finding includes: gap magnitude, expected vs. observed, likely cause, confidence

### Task 5: Peer Benchmarking (Days 17-19)

**Deliverable:** Peer grouping + deviation scoring

**Acceptance Criteria:**
- CSEs grouped by (sector, size_band)
- Z-scores and percentiles computed for: investigation depth, closure velocity, escalation rate
- Outlier flagging: |z-score| > 2.5
- Peer group definitions disclosed in findings

### Task 6: Supervisory Attention Score (Days 20-21)

**Deliverable:** Weighted aggregation function

**Acceptance Criteria:**
- Score = 0.4 × confidence + 0.3 × severity + 0.3 × signal count
- Normalized to 0-100 scale
- Entities ranked by score
- Top 10 entities clearly distinguished from rest

### Task 7: Finding Engine & Evidence Tracing (Days 22-24)

**Deliverable:** Structured finding generation with record-level tracing

**Acceptance Criteria:**
- Each finding includes: entity ID, signal types, severity, confidence, contributing record IDs, detection rationale, recommended examiner actions, caveats
- Record-level drill-down shows: record content, why it contributed, related records
- Findings traceable to source data

### Task 8: Dashboard (Days 25-30)

**Deliverable:** Interactive dashboard with 3 core views

**Acceptance Criteria:**

**Portfolio Overview:**
- Table of 50 CSEs with Supervisory Attention Score, finding count, trend arrow
- Color-coded by priority (red/yellow/green)
- Sortable by score, sector, size

**Entity Deep-Dive:**
- CSE profile summary (alert volume, investigation depth, closure velocity, escalation rate)
- List of findings for selected entity
- Peer comparison chart (box plot or bar chart)

**Finding Detail:**
- Finding explanation (what, why, how)
- **Supervisory Finding Card** (priority, confidence, signal, evidence summary, affected cases, recommended action)
- Evidence table (contributing records with IDs, timestamps, key fields)
- Recommended examiner actions
- Caveats and alternative explanations

**Technical:**
- React or Vue.js frontend
- FastAPI or Flask backend
- Responsive design
- Demo-ready in <2 minutes

### Task 9: Demo Preparation (Days 31-33)

**Deliverable:** 2-minute demo script + curated demo dataset

**Acceptance Criteria:**
- 2-minute demo script with timing and talking points
- Curated dataset highlighting 3-4 entities with clear findings
- Demo flow: portfolio overview → entity deep-dive → finding detail → evidence drill-down
- Practice runs completed

---

## 6. MVP Demo Flow (2 Minutes)

### [0:00-0:10] Problem Statement
"NCIIPC supervises 50+ Critical Sector Entities by manually reviewing SOC evidence. Manual review is thorough but doesn't scale. SAT-SA applies supervisory analytics to detect execution gaps and negative space that conventional dashboards miss."

**[Screen: Portfolio overview with 50 CSEs ranked]**

### [0:10-0:30] Portfolio View
"Here's the portfolio view. 50 entities analyzed. 8 with supervisory findings. Ranked by Supervisory Attention Score — a weighted aggregation of execution gaps, negative space, and peer deviation.

Let me click on CSE-042, which has a HIGH-priority finding."

**[Screen: Click CSE-042 → Entity deep-dive]**

### [0:30-0:50] Execution Gap Finding
"CSE-042 shows investigation depth declining 70% over 4 quarters while alert volume stayed constant. Q1: 7.2 evidence entries per alert. Q4: 2.1 entries. Change point detected in Q3.

At the same time, closure velocity improved. This is a classic execution gap: the SOC is closing alerts faster, but with less investigation. Either staff are cutting corners, or something changed in Q3 that we need to understand."

**[Screen: Trend chart showing decline + peer comparison]**

### [0:50-1:10] Negative Space Finding
"Now look at CSE-089. Claims 2,000 endpoints under EDR monitoring. Expected: 300+ endpoint alerts per quarter. Observed: zero.

This is negative space: complete absence of expected evidence. Either the EDR is broken, monitoring is disabled, or data isn't being submitted. That's a supervisory question for NCIIPC examiners."

**[Screen: Alert volume gap visualization]**

### [1:10-1:30] Evidence Drill-Down
"Every finding traces back to specific records. Here's Investigation 042-8821 from CSE-042. High-severity alert. Closed in 3 hours. Two evidence entries: 'Reviewed firewall logs' and 'Alert appears benign.'

Compare to Q1: same alert type, 10 evidence entries, 14-hour investigation, detailed threat assessment. Same CSE. Completely different quality. That's an execution gap."

**[Screen: Side-by-side comparison]**

### [1:30-1:45] Peer Context
"CSE-042 is in a peer group of 8 telecom SOCs. Median investigation depth: 6.1 entries. CSE-042: 2.1 entries. That's a 3.2 standard deviation outlier. Not a borderline case — a clear deviation requiring examiner review."

**[Screen: Peer comparison chart]**

### [1:45-2:00] Positioning & Closing
"What makes SAT-SA different: it doesn't just flag anomalies. It models what *should* be observed, compares against what *is* observed, and fuses multiple weak signals into evidence-backed findings.

The system identifies the question. The examiner answers it. That's evidence-driven supervisory insight at portfolio scale."

**[Screen: SAT-SA positioning slide]**

---

## 7. MVP Success Criteria

### Functional Completeness

- [ ] Sample data loads successfully (50 CSEs, 4 quarters)
- [ ] All 3 execution gap signals detect seeded weaknesses
- [ ] Both negative space signals detect seeded weaknesses
- [ ] Peer benchmarking correctly identifies outliers
- [ ] Supervisory Attention Score ranks seeded CSEs in top 10
- [ ] Findings include record-level evidence tracing
- [ ] Dashboard displays all 3 views with drill-down
- [ ] 2-minute demo executes smoothly

### Technical Quality

- [ ] Pipeline completes in <60 seconds for 50 CSEs
- [ ] No critical bugs in demo path
- [ ] Code is readable and well-structured
- [ ] Offline-capable (no external API calls)

### Demo Quality

- [ ] Demo runs in ≤2 minutes
- [ ] All key innovations demonstrated (expected-evidence comparison, execution gap detection, negative space, peer context)
- [ ] Findings are explainable and evidence-backed
- [ ] Q&A preparation complete

---

## 8. MVP Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Backend** | Python + FastAPI | Fast to build, offline-compatible, auto-generated API docs |
| **Analytics** | Python + Pandas + NumPy | Simple, effective, no external dependencies |
| **Database** | SQLite (MVP) → PostgreSQL (post-MVP) | Zero-config for MVP; easy migration |
| **Frontend** | React (Vite) | Fast development, good component model, interactive |
| **Visualization** | Recharts or Chart.js | Simple, responsive, demo-ready |
| **Deployment** | Docker Compose | Single command to run entire stack |

---

## 9. MVP File Structure

```
SIH/
├── README.md                    # Full project README
├── plan.md                      # Full 12-week implementation plan
├── MVP.md                       # This file
├── src/
│   ├── ingestion/
│   │   ├── pipeline.py          # Main ingestion orchestrator
│   │   ├── parsers.py           # CSV/JSON parsers
│   │   ├── validators.py        # Schema validation
│   │   └── quality.py           # Quality scoring
│   ├── analytics/
│   │   ├── profiler.py          # Behavioral profile extraction
│   │   ├── execution_gaps.py    # 3 execution gap detectors
│   │   ├── negative_space.py    # 2 negative space detectors
│   │   ├── benchmarking.py      # Peer grouping + deviation scoring
│   │   └── scoring.py           # Supervisory Attention Score
│   ├── evidence/
│   │   ├── tracer.py            # Evidence tracing to source records
│   │   └── findings.py          # Finding generation and structuring
│   ├── api/
│   │   └── routes.py            # FastAPI endpoints
│   └── dashboard/
│       ├── main.pyx              # React app entry
│       ├── components/
│       │   ├── PortfolioView.jsx
│       │   ├── EntityView.jsx
│       │   └── FindingDetail.jsx
│       └── views/
│           ├── portfolio.pyx
│           ├── entity.pyx
│           └── finding.pyx
├── data/
│   ├── schemas/
│   │   └── satsa_schema.json     # Unified schema definition
│   ├── samples/
│   │   └── generate_sample_data.py  # Synthetic data generator
│   │   └── sample_50_cses.csv       # Pre-generated sample data
│   └── config/
│       └── thresholds.json       # Detection thresholds
├── tests/
│   ├── test_ingestion.py
│   ├── test_profiler.py
│   ├── test_execution_gaps.py
│   ├── test_negative_space.py
│   └── test_benchmarking.py
├── requirements.txt
├── docker-compose.yml
└── .env.example
```

---

## 10. MVP Configuration

### Detection Thresholds

```json
{
  "execution_gaps": {
    "superficial_closure": {
      "fast_closure_percentile": 25,
      "shallow_depth_percentile": 25,
      "min_flagged_ratio": 0.30
    },
    "escalation_without_action": {
      "min_no_followup_ratio": 0.20
    },
    "quality_degradation": {
      "min_decline_pct": 30,
      "min_periods": 3,
      "changepoint_penalty": "BIC"
    }
  },
  "negative_space": {
    "alert_volume_gap": {
      "min_gap_pct": 50,
      "min_confidence": 0.70
    },
    "missing_investigations": {
      "high_severity_threshold": "HIGH",
      "min_missing_ratio": 0.20
    }
  },
  "peer_benchmarking": {
    "outlier_zscore": 2.5,
    "min_peer_group_size": 3
  },
  "supervisory_attention_score": {
    "confidence_weight": 0.4,
    "severity_weight": 0.3,
    "signal_count_weight": 0.3
  }
}
```

---

## 11. MVP Limitations (Transparent)

The MVP has the following limitations that should be disclosed to judges:

1. **Synthetic data only:** MVP runs on generated data, not real CSE submissions. Real-world data quality issues may affect detection.
2. **Limited signal coverage:** Only 5 detection signals implemented (3 execution gaps + 2 negative space). Full system has 8+ signal groups.
3. **No formal validation:** MVP lacks precision/recall measurement against expert manual review. Validation is post-MVP.
4. **Simplified peer grouping:** Peer groups are defined by sector + size only. Full system uses clustering with multiple normalization factors.
5. **Rule-based only:** No ML components in MVP. Full system includes optional NLP and anomaly detection.
6. **Single-period analysis:** MVP analyzes one quarter at a time. Full system supports trend analysis across multiple periods.
7. **No signal fusion:** MVP generates individual findings. Full system fuses multiple signals into supervisory cases.
8. **Limited explainability:** Basic rationale per finding. Full system includes alternative explanations, caveats, and record-level drill-down.

These limitations are intentional: the MVP proves the core concept without over-engineering.

---

## 12. Post-MVP Roadmap

| Phase | Timeline | Deliverable |
|-------|----------|-------------|
| **MVP** | Weeks 1-5 | Core detection, dashboard, demo |
| **Phase 2** | Weeks 6-8 | Signal fusion, full explainability, report export |
| **Phase 3** | Weeks 9-10 | Validation harness, precision/recall measurement |
| **Phase 4** | Weeks 11-12 | Polish, deployment packaging, SIH submission |

---

## 13. MVP Decision Rationale

### Why These 5 Signals?

The MVP implements 3 execution gap signals + 2 negative space signals because:

1. **Directly map to problem statement:** SIH26157 explicitly calls out execution gaps and negative space as the two core supervisory problems
2. **Demonstrable with synthetic data:** These signals can be clearly seeded and detected in synthetic data
3. **Explainable to judges:** Detection logic is rule-based and easy to explain in 2 minutes
4. **Differentiate from dashboards:** These signals detect things conventional dashboards miss (workflow breaks, missing evidence)
5. **Scalable to full system:** These modules form the foundation for the 8-signal architecture in the full plan

### Why Not Include Signal Fusion?

Signal fusion adds complexity without proportional demo value. Individual findings are sufficient to prove the core concept. Fusion can be demonstrated with a slide or two in the presentation without requiring full implementation.

### Why Not Include Temporal Drift?

Temporal drift (change-point detection) is valuable but requires at least 4 data points per entity and adds implementation complexity. The MVP uses a simpler quarter-over-quarter comparison that is easier to implement and sufficiently demonstrates the concept.

### Why Synthetic Data?

Real CSE data is not available during the hackathon. Synthetic data allows the team to:
- Control exactly which weaknesses are present
- Ensure detection engines find known issues
- Create a reliable, repeatable demo
- Generate as much data as needed for performance testing

The synthetic data generator is itself a deliverable and can be reused for validation post-MVP.

---

## 14. Key MVP Risks

| Risk | Mitigation |
|------|-----------|
| **Synthetic data looks fake** | Invest in realistic data generation; base distributions on publicly available SOC metrics |
| **Demo fails live** | Pre-record backup demo; have curated screenshots ready |
| **Detection thresholds miss seeded weaknesses** | Tune thresholds aggressively for demo; document that production requires calibration |
| **Dashboard too complex for 2-minute demo** | Time-box demo to exactly 3 screens; practice extensively |
| **Judges don't understand the value** | Focus demo on "what a supervisor sees" not "how the algorithm works" |

---

## 15. MVP Acceptance Gate

Before proceeding to post-MVP development, the following must be true:

1. ✅ All 5 detection signals correctly identify seeded weaknesses in synthetic data
2. ✅ Supervisory Attention Score ranks 8+ seeded CSEs in top 10
3. ✅ Dashboard displays all 3 views with functional drill-down
4. ✅ 2-minute demo executes smoothly with no errors
5. ✅ Code is committed, documented, and runnable via Docker Compose
6. ✅ Team can explain each finding's detection logic in <30 seconds

---

*Last updated: 2026-08-22*  
*Status: MVP Scope Locked — Ready for Implementation*
