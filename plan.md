# SAT-SA Implementation Plan

**Project:** SAT-SA — Supervisory Analytics Tool for SOC Assessment  
**Competition:** Smart India Hackathon 2026  
**Problem Statement:** SIH26157 — NCIIPC  
**Timeline:** 3-Month Development Sprint (12 Weeks)  
**Status:** Planning Phase

---

## 1. Project Objectives

1. Build a functional prototype that demonstrates supervisory analytics capabilities across multiple CSEs
2. Implement 8 signal detection modules covering execution gaps, negative space, behavioral drift, peer benchmarking, and signal fusion
3. Create an explainable, evidence-backed finding engine with record-level tracing
4. Deliver a dashboard with portfolio, entity, and finding-level views
5. Validate against synthetic and historical supervisory data
6. Ensure offline-capable, air-gap-ready deployment

---

## 2. Sprint Timeline

| Week | Phase | Deliverable |
|------|-------|-------------|
| 1-2 | Foundation | Data ingestion, normalization, profiling engine |
| 3-4 | Detection Layer 1 | Execution gap engine + negative space engine |
| 5-6 | Detection Layer 2 | Temporal drift + peer benchmarking |
| 7-8 | Fusion & Cases | Signal fusion + supervisory case generation |
| 9 | Dashboard | Interactive dashboard with drill-down |
| 10 | Validation | Validation harness + synthetic test cases |
| 11 | Refinement | Bug fixes, performance, demo prep |
| 12 | Finalization | Documentation, pitch, deployment packaging |

---

## 3. Detailed Task Breakdown

### Sprint 1: Data Ingestion & Normalization (Weeks 1-2)

**Owner:** Backend Lead  
**Dependencies:** None

#### Tasks

| Task | Description | Effort | Acceptance Criteria |
|------|-------------|--------|---------------------|
| Schema definition | Define unified SATSA schema for alerts, investigations, escalations, cases, inventory | 2 days | Schema documented, validated against SIH requirements |
| CSV parser | Parse CSE CSV submissions with configurable column mapping | 2 days | Successfully parses 3+ sample formats |
| JSON parser | Parse CSE JSON submissions (nested and flat) | 1 day | Handles nested investigation and escalation records |
| XLSX parser | Parse Excel submissions (if required) | 1 day | Handles multi-sheet workbooks |
| Schema validation | Validate submissions against unified schema | 2 days | Returns detailed validation report with row-level errors |
| Quality scoring | Compute data quality score per submission | 1 day | Flags null rates, referential integrity, temporal consistency |
| Database design | Design PostgreSQL schema for normalized data | 2 days | Tables for submissions, alerts, investigations, escalations, cases, inventory, findings |
| Database migration | Implement Alembic or raw SQL migrations | 1 day | Reproducible schema setup |
| Ingestion API | REST endpoints for submission upload and processing | 2 days | POST /api/ingest returns normalized data + quality report |
| Sample data generation | Create 3 synthetic CSE datasets for demo | 2 days | 50 entities, 4 quarters, realistic distributions |
| Unit tests | Test parsers, validators, quality scoring | 2 days | 90%+ coverage for ingestion module |

**Deliverable:** Working ingestion pipeline with sample data loaded into database

---

### Sprint 2: Behavioral Profile Extraction (Weeks 1-2)

**Owner:** Analytics Lead  
**Dependencies:** Database schema, sample data

#### Tasks

| Task | Description | Effort | Acceptance Criteria |
|------|-------------|--------|---------------------|
| Profile schema | Define behavioral profile data structure (30-50 dimensions) | 1 day | Documented profile schema |
| Alert metrics | Volume, severity distribution, category mix | 1 day | Correctly computed on sample data |
| Investigation metrics | Depth, closure velocity, completion rate | 2 days | Depth = evidence entries count; velocity = open-to-close duration |
| Escalation metrics | Rate, appropriateness, follow-through | 2 days | Escalation rate by severity; follow-through = linked response evidence |
| Temporal patterns | Diurnal cycle, weekly patterns | 2 days | Hour-of-day and day-of-week distributions |
| Workflow integrity | Score based on state transition completeness | 3 days | Workflow graph model implemented |
| Evidence completeness | Presence/absence of expected artifacts | 2 days | Checks investigation, escalation, response artifacts |
| Quality trend | Quarter-over-quarter investigation depth trend | 1 day | Trend computed for sample data |
| Profile API | Endpoints to retrieve CSE profiles | 1 day | GET /api/profiles/{cse_id} |
| Unit tests | Test all profile extractors | 2 days | 90%+ coverage |

**Deliverable:** Behavioral profiles computed for all sample CSEs

---

### Sprint 3: Execution Gap Engine (Weeks 3-4)

**Owner:** Analytics Lead  
**Dependencies:** Behavioral profiles

#### Tasks

| Task | Description | Effort | Acceptance Criteria |
|------|-------------|--------|---------------------|
| Superficial closure detection | Fast closure + shallow depth correlation | 2 days | Flags >30% of investigations as superficial |
| Escalation without action | Escalations with no follow-through evidence | 1 day | Flags >20% escalations with no follow-up |
| Quality degradation detection | Investigation depth trend + change-point | 3 days | Change-point detection with p-value reporting |
| Template investigation detection | Lexical similarity scoring | 2 days | Cosine similarity + Jaccard index on investigation notes |
| Severity mismatch detection | Severity vs. investigation depth vs. closure time | 2 days | Flags inconsistent triage patterns |
| KPI-reality divergence | Reported metrics vs. operational outcomes | 2 days | Correlation matrix with significance testing |
| Gap severity assessment | Distinguish real gaps from data artifacts | 2 days | Bayesian prior + likelihood scoring |
| Execution gap API | Endpoints for execution gap findings | 1 day | GET /api/findings/execution-gaps/{cse_id} |
| Unit tests | Test each detection function | 3 days | 85%+ coverage |

**Deliverable:** Execution gap engine producing findings on sample data

---

### Sprint 4: Negative Space Engine (Weeks 3-4)

**Owner:** Analytics Lead  
**Dependencies:** Expected evidence model, behavioral profiles

#### Tasks

| Task | Description | Effort | Acceptance Criteria |
|------|-------------|--------|---------------------|
| Expected evidence model | Build CSE-specific expected-evidence profiles | 3 days | Predicts alert volume, categories, investigation ratio, escalation rate |
| Alert volume gap | Expected vs. observed volume | 1 day | Bayesian comparison with confidence intervals |
| Missing alert categories | Inventory-to-alert mapping | 2 days | Flags categories with <5% of expected frequency |
| Alert source distribution | Asset-to-source correlation | 2 days | Chi-squared test for distribution mismatch |
| Investigation ratio gap | Expected vs. observed investigation rate | 1 day | Flags high-severity alerts without investigation |
| Evidence artifact absence | Claimed capability vs. documented artifacts | 2 days | Checks for threat-intel lookup, config review, system state |
| Negative space API | Endpoints for negative space findings | 1 day | GET /api/findings/negative-space/{cse_id} |
| Unit tests | Test expected model and gap detection | 3 days | 85%+ coverage |

**Deliverable:** Negative space engine producing findings on sample data

---

### Sprint 5: Temporal Drift & Peer Benchmarking (Weeks 5-6)

**Owner:** Analytics Lead  
**Dependencies:** Behavioral profiles, historical data

#### Tasks

| Task | Description | Effort | Acceptance Criteria |
|------|-------------|--------|---------------------|
| Temporal feature extraction | Diurnal, weekly, seasonal patterns | 2 days | Fourier-based seasonality detection |
| Change-point detection | CUSUM, PELT algorithm implementation | 3 days | Detects structural breaks in time series |
| Drift classification | Gradual vs. abrupt change distinction | 2 days | Classifies drift type and velocity |
| Cyclical anomaly detection | Quiet periods, shift-based variance, bulk closures | 3 days | Flags anomalous temporal patterns |
| Peer grouping | Smart clustering by sector, size, capabilities | 3 days | k-means + DBSCAN with normalization |
| Peer benchmarking | Z-score, percentile, deviation scoring | 2 days | Normalized comparison with confidence intervals |
| Drift API | Endpoints for drift and peer findings | 1 day | GET /api/findings/drift/{cse_id}, GET /api/peers/{cse_id} |
| Unit tests | Test drift detection and peer benchmarking | 3 days | 85%+ coverage |

**Deliverable:** Drift detection and peer benchmarking engines producing findings

---

### Sprint 6: Signal Fusion & Supervisory Cases (Weeks 7-8)

**Owner:** Backend Lead + Analytics Lead  
**Dependencies:** All detection engines

#### Tasks

| Task | Description | Effort | Acceptance Criteria |
|------|-------------|--------|---------------------|
| Signal correlation | Group correlated signals into cases | 2 days | Signals clustered by detection type and entity |
| Confidence aggregation | Combined confidence from multiple signals | 2 days | Bayesian or weighted aggregation implemented |
| Case scoring | Priority score based on confidence, severity, count | 2 days | Score normalized 0.0-1.0 |
| Case generation | Supervisory case structure and generation | 2 days | Cases include signals, evidence, recommendations, caveats |
| Review queue | Prioritized list of entities and samples | 1 day | Ranked by priority score with urgency tiers |
| Case API | Endpoints for supervisory cases | 1 day | GET /api/cases, GET /api/cases/{case_id} |
| Unit tests | Test fusion logic and case generation | 2 days | 85%+ coverage |

**Deliverable:** Signal fusion engine generating supervisory cases

---

### Sprint 7: Explainability & Evidence Tracing (Weeks 7-8)

**Owner:** Backend Lead  
**Dependencies:** All detection engines, case generation

#### Tasks

| Task | Description | Effort | Acceptance Criteria |
|------|-------------|--------|---------------------|
| Evidence tracer | Trace findings to source records | 2 days | Returns list of contributing record IDs with explanations |
| Rationale generator | Generate detection rationale for each finding | 2 days | Includes what, why, how, confidence, caveats |
| Record-level drill-down | Detailed view of individual records | 2 days | Shows record content and why it contributed to finding |
| Alternative explanations | Generate plausible alternative causes | 1 day | Lists 2-3 alternative explanations per finding |
| Examiner recommendations | Generate recommended review actions | 1 day | Actionable recommendations per case |
| Explainability API | Endpoints for finding explanations | 1 day | GET /api/findings/{finding_id}/explain |
| Unit tests | Test explainability components | 2 days | 85%+ coverage |

**Deliverable:** Explainability engine integrated with all finding types

---

### Sprint 8: Dashboard UI (Week 9)

**Owner:** Frontend Lead  
**Dependencies:** Backend APIs, sample data

#### Tasks

| Task | Description | Effort | Acceptance Criteria |
|------|-------------|--------|---------------------|
| Dashboard framework | React/Vue setup with routing and state | 2 days | App scaffold with authentication placeholder |
| Portfolio overview | Entity rankings, finding counts, trend arrows | 2 days | Displays 50 entities with scores and finding counts |
| Entity deep-dive | Profile summary, findings list, peer comparison | 3 days | Drill-down from portfolio to entity view |
| Finding detail | Finding explanation, evidence table, peer context | 2 days | Shows rationale, evidence records, recommended actions |
| Evidence drill-down | Individual record viewer with context | 2 days | Shows record content and relationship to finding |
| Review queue | Prioritized list with urgency tiers | 1 day | Filterable by severity, entity, signal type |
| Trend analysis | Time-series charts for entity metrics | 2 days | Shows 4-quarter trends with change points |
| Signal fusion view | Multi-signal case visualization | 1 day | Shows how signals combine into cases |
| Report export | HTML and PDF report generation | 2 days | Exportable entity and portfolio reports |
| Demo polish | Loading states, error handling, responsive design | 1 day | Smooth demo flow |

**Deliverable:** Interactive dashboard with all conceptual views implemented

---

### Sprint 9: Validation & Testing (Week 10)

**Owner:** All Leads  
**Dependencies:** Complete system

#### Tasks

| Task | Description | Effort | Acceptance Criteria |
|------|-------------|--------|---------------------|
| Synthetic test cases | Inject known weaknesses into sample data | 2 days | 10+ test cases with known ground truth |
| Blind validation | Run against historical manual review data | 2 days | Compare SAT-SA findings to manual findings |
| Precision/recall measurement | Measure detection performance | 1 day | Precision, recall, F1 reported |
| Examiner agreement | Have reviewers evaluate SAT-SA findings | 2 days | Alignment score with expert judgment |
| False positive analysis | Analyze and categorize false positives | 1 day | Root causes identified and documented |
| Threshold calibration | Adjust detection thresholds based on validation | 2 days | Configurable thresholds with documented rationale |
| Integration tests | End-to-end pipeline tests | 2 days | Full pipeline runs on sample data without errors |
| Performance testing | Measure runtime and memory on full portfolio | 1 day | Completes in <30 minutes for 50 entities |
| Bug fixing | Address issues found in validation | 2 days | Critical bugs resolved |

**Deliverable:** Validation report with performance metrics and documented limitations

---

### Sprint 10: Refinement & Demo Prep (Week 11)

**Owner:** All Leads  
**Dependencies:** Validation results

#### Tasks

| Task | Description | Effort | Acceptance Criteria |
|------|-------------|--------|---------------------|
| Refine detection logic | Improve precision based on validation | 2 days | False positive rate reduced by ≥20% |
| Improve explainability | Enhance rationale quality and clarity | 1 day | Examiner feedback incorporated |
| Dashboard UX polish | Improve usability and visual design | 2 days | Smooth, intuitive navigation |
| Demo script | Write 2-minute demo script with timing | 1 day | Scripted flow with talking points |
| Demo data preparation | Curate compelling demo dataset | 1 day | 3-4 entities with clear findings |
| Presentation slides | Create SIH presentation slides | 2 days | 10-12 slides covering problem, solution, demo |
| Pitch rehearsal | Practice 2-minute demo and Q&A | 1 day | Smooth delivery within time limit |
| Documentation | Update README, architecture docs, API docs | 2 days | Complete and accurate documentation |

**Deliverable:** Demo-ready system with presentation materials

---

### Sprint 11: Finalization (Week 12)

**Owner:** All Leads  
**Dependencies:** Demo-ready system

#### Tasks

| Task | Description | Effort | Acceptance Criteria |
|------|-------------|--------|---------------------|
| Final bug fixes | Address any remaining issues | 1 day | No critical bugs |
| Deployment packaging | Docker images, offline installers | 2 days | Runnable in air-gapped environment |
| Code review | Review all code for quality and consistency | 1 day | Code meets project standards |
| Final documentation | Complete README, plan, architecture docs | 1 day | All docs updated and accurate |
| Submission preparation | Prepare SIH submission materials | 2 days | Code, docs, demo video, presentation ready |
| Backup & versioning | Tag release, create backup | 1 day | Versioned release ready for submission |

**Deliverable:** Complete SIH submission package

---

## 4. Module Dependencies

```
Data Ingestion & Normalization
    ↓
Behavioral Profile Extraction
    ↓
Expected Evidence Model
    ↓
├─ Execution Gap Engine
├─ Negative Space Engine
├─ Temporal Drift Detection
└─ Peer Benchmarking Engine
    ↓
Signal Fusion & Supervisory Case Generation
    ↓
Explainability & Evidence Tracing
    ↓
Dashboard & Reports
```

---

## 5. Team Structure & Responsibilities

| Role | Responsibilities | Owner |
|------|-----------------|-------|
| **Backend Lead** | Ingestion, normalization, database, APIs, signal fusion, explainability | TBD |
| **Analytics Lead** | All detection engines (execution gaps, negative space, drift, benchmarking, scoring) | TBD |
| **Frontend Lead** | Dashboard UI, visualization, report generation, drill-down interfaces | TBD |
| **Validation Lead** | Test case design, validation harness, precision/recall measurement, examiner coordination | TBD |

---

## 6. Key Milestones

| Milestone | Week | Criteria |
|-----------|------|----------|
| **M1: Ingestion Complete** | 2 | Sample data loaded, profiles computed, API functional |
| **M2: Detection Engines Complete** | 6 | All 5 detection engines producing findings on sample data |
| **M3: Fusion & Explainability Complete** | 8 | Supervisory cases generated with evidence tracing |
| **M4: Dashboard Complete** | 9 | Interactive dashboard with all views functional |
| **M5: Validation Complete** | 10 | Validation report with performance metrics |
| **M6: Demo Ready** | 11 | 2-minute demo scripted and rehearsed |
| **M7: Submission Ready** | 12 | Complete package ready for SIH submission |

---

## 7. Risk Register

| Risk | Probability | Impact | Mitigation | Owner |
|------|------------|--------|-----------|-------|
| **Data quality issues** | High | High | Build quality scoring; flag low-confidence findings; generate robust synthetic data | Backend Lead |
| **False positives** | Medium | High | Signal fusion + peer context; examiner validation; iterative threshold calibration | Analytics Lead |
| **Peer group relevance** | Medium | Medium | Smart clustering with normalization factors; disclose peer group definitions | Analytics Lead |
| **Scope creep** | Medium | High | Strict enforcement of "supervisory" vs. "operational" boundary; weekly scope reviews | All Leads |
| **Dashboard complexity** | Medium | Medium | Focus on core views first; polish later; time-box UI work | Frontend Lead |
| **Validation data availability** | Medium | High | Generate comprehensive synthetic test cases; design validation harness early | Validation Lead |
| **Team availability** | Low | High | Cross-train team members; document progress continuously | Project Lead |
| **Demo timing** | Low | Medium | Rehearse extensively; prepare fallback demo scenarios | All Leads |

---

## 8. Success Metrics

### Functional Completeness

- [ ] All 8 signal groups implemented and producing findings
- [ ] Signal fusion generating supervisory cases
- [ ] Evidence tracing operational for all finding types
- [ ] Dashboard with all 9 conceptual views
- [ ] Report export (HTML, PDF) functional

### Technical Quality

- [ ] 85%+ test coverage across all modules
- [ ] Pipeline completes in <30 minutes for 50 entities
- [ ] No critical bugs in production path
- [ ] Offline deployment packaged and tested

### Validation Performance

- [ ] Coverage ≥ 70% (proportion of manual findings detected)
- [ ] Precision ≥ 60% (proportion of findings judged worthy of review)
- [ ] Examiner alignment score ≥ 0.7 (correlation with expert judgment)

### Demo Quality

- [ ] 2-minute demo executed smoothly
- [ ] All key innovations demonstrated
- [ ] Q&A preparation complete
- [ ] Presentation materials polished

---

## 9. Weekly Cadence

| Day | Activity |
|-----|----------|
| Monday | Sprint planning; task assignment |
| Tuesday-Thursday | Development; daily standups |
| Friday | Integration testing; demo prep; milestone review |
| Weekend | Buffer for catch-up; documentation |

---

## 10. Definition of Done

A task is considered complete when:

1. Code is implemented and tested
2. Unit tests pass with ≥85% coverage
3. Code is reviewed by at least one other team member
4. Documentation is updated (README, inline comments, API docs)
5. Feature is demonstrated working on sample data
6. No critical or high-severity bugs remain

---

## 11. Out of Scope (Enforced)

The following are explicitly out of scope and will not be added:

- Real-time SOC monitoring or alerting
- SIEM correlation or live event processing
- Network packet capture or analysis
- Customer data or PII processing
- Cloud deployment or SaaS features
- External API integrations
- Generic chatbot or LLM wrapper
- Compliance scoring or certification

Scope additions require explicit team consensus and SIH requirement validation.

---

## 12. Key Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| [TBD] | Python backend with FastAPI | Offline-compatible, auditability, team familiarity |
| [TBD] | PostgreSQL + JSONB | Structured data with flexible schema evolution |
| [TBD] | React frontend | Component-based, good drill-down support |
| [TBD] | Scikit-learn for ML (optional) | Lightweight, offline-capable, explainable |
| [TBD] | Docker for deployment | Air-gap friendly, reproducible |
| [TBD] | 8 signal groups | Comprehensive coverage of supervisory signals |
| [TBD] | Signal fusion architecture | Reduces false positives, increases confidence |
| [TBD] | Hybrid deterministic + statistical approach | Balances auditability with analytical sophistication |

---

## 13. Open Questions

1. **Validation data:** Will NCIIPC provide historical manual review findings for blind validation?
2. **Peer group data:** What metadata is available for peer grouping (sector, size, capabilities)?
3. **Sample data format:** What do actual CSE submissions look like? (We have assumed structure)
4. **Threshold calibration:** Who defines acceptable false positive rates for production use?
5. **Deployment environment:** What are NCIIPC's specific hardware and OS constraints?

---

## 14. Next Steps

1. Finalize team roles and responsibilities
2. Set up development environment and repository
3. Create initial project structure (see README Section 18)
4. Begin Sprint 1: Data ingestion and normalization
5. Generate comprehensive synthetic sample data
6. Schedule weekly standups and milestone reviews

---

*Last updated: 2026-08-22*  
*Status: Planning Complete — Ready for Sprint 1*
