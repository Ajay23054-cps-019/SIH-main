# SAT-SA Product Document

**Product:** SAT-SA — Supervisory Analytics Tool for SOC Assessment  
**Organisation:** National Critical Information Infrastructure Protection Centre (NCIIPC)  
**Market:** Supervisory assurance for Critical Sector Entities (CSEs)  
**Status:** Prototype — SIH26157

---

## 1. Product Vision

SAT-SA exists to solve a specific, high-stakes supervision problem: **how does a government supervisory authority maintain credible oversight of security operations across dozens of critical infrastructure entities when manual review cannot scale?**

The vision is a future where NCIIPC supervisors can:
- Maintain **portfolio-wide visibility** into SOC operational effectiveness
- Detect **execution gaps and negative-space conditions** that self-reported metrics miss
- **Prioritise scarce examiner time** on the highest-risk entities and operational areas
- Preserve the **depth, rigour, and defensibility** of expert human examination at scale

SAT-SA is not a product for SOCs. It is a product for **supervisors of SOCs**.

---

## 2. Product Mission

To transform periodic CSE operational submissions into **evidence-backed supervisory findings** that direct human examiners to the highest-priority operational weaknesses, enabling NCIIPC to supervise a growing portfolio of Critical Sector Entities without sacrificing the quality of supervisory assurance.

---

## 3. Target Users & Personas

### Primary User: NCIIPC Supervisor / Examiner

**Persona:** Senior cybersecurity examiner with 10+ years of SOC audit and supervisory experience. Responsible for reviewing operational evidence from 30-80 CSEs. Time-constrained. Needs to make defensible supervisory decisions with incomplete information.

**Goals:**
- Identify CSEs whose SOCs are not operating effectively
- Detect operational weaknesses that policies and self-reports miss
- Prioritise limited review time on highest-risk entities
- Produce audit-ready findings with clear rationale and evidence
- Maintain credibility and defensibility of supervisory conclusions

**Frustrations:**
- Manual review is thorough but cannot cover all entities
- KPIs and dashboards show "green" while operational quality degrades
- Absence of evidence is invisible until an incident reveals it
- Peer comparisons are misleading because entities are heterogeneous
- Black-box risk scores are difficult to explain to senior management

**How SAT-SA Helps:**
- Surfaces entities and operational areas warranting examination
- Provides evidence-backed findings, not just risk scores
- Traces every finding to specific records for independent validation
- Explains detection logic, confidence, and caveats
- Respects examiner authority — system informs, does not decide

### Secondary User: NCIIPC Management

**Persona:** Director or Joint Secretary responsible for portfolio-level supervisory strategy. Needs aggregated views, trend analysis, and resource allocation insights.

**Goals:**
- Understand portfolio-wide supervisory posture
- Identify sector-wide patterns and systemic weaknesses
- Allocate examiner resources efficiently
- Report to senior government stakeholders with credible evidence

**How SAT-SA Helps:**
- Portfolio overview with entity rankings and finding summaries
- Sector-level aggregation and trend analysis
- Evidence-backed reports suitable for senior management briefings

### Tertiary User: CSE SOC Manager (Indirect)

**Persona:** SOC manager at a Critical Sector Entity who submits periodic data to NCIIPC.

**Goals:**
- Understand what operational evidence NCIIPC examines
- Identify gaps in their own SOC's documentation and evidence generation
- Improve SOC operational maturity

**How SAT-SA Helps (Indirectly):**
- Expected-evidence model makes explicit what "good" looks like
- Findings shared with CSEs (at NCIIPC discretion) highlight improvement areas
- Peer benchmarking provides context for self-assessment

---

## 4. Core User Problems

### Problem 1: Execution Gaps Are Invisible in Reports

**User Story:** As an NCIIPC examiner, I need to detect when a SOC's reported metrics (SLA compliance, closure rates) diverge from actual operational quality (investigation depth, escalation legitimacy), because this divergence indicates an execution gap that self-reports miss.

**Current State:** SOCs report "99% alert response SLA." Examiner samples 10 alerts and finds shallow, template-driven investigations. The KPI looked healthy; the reality was not.

**SAT-SA Solution:** Compare operational evidence against expected patterns. Flag cases where closure velocity improved while investigation depth declined. Surface the divergence with specific record evidence.

### Problem 2: Negative Space Is Invisible in Dashboards

**User Story:** As an NCIIPC examiner, I need to detect when expected evidence is absent (missing telemetry, missing investigations, missing alert categories), because absence of evidence is a supervisory signal that conventional dashboards cannot show.

**Current State:** CSE claims 2,000 endpoints under EDR monitoring. Dashboard shows "EDR deployed." Examiner has no way to know that zero endpoint alerts were generated last quarter unless they manually check.

**SAT-SA Solution:** Build CSE-specific expected-evidence models based on claims and asset inventory. Compare observed vs. expected. Flag significant gaps with confidence assessment.

### Problem 3: Peer Context Is Missing

**User Story:** As an NCIIPC examiner, I need to understand whether a CSE's operational behavior is normal or anomalous, because raw metrics without context are difficult to interpret.

**Current State:** CSE closes critical alerts in 18 minutes. Is that fast because they're efficient, or because they're cutting corners? No benchmark to compare against.

**SAT-SA Solution:** Normalized peer benchmarking controlling for sector, size, alert mix, and claimed capabilities. "This CSE is at the 3rd percentile for critical-alert closure velocity among 8 comparable telecom SOCs."

### Problem 4: Manual Review Cannot Scale

**User Story:** As an NCIIPC supervisor, I need to prioritise scarce examiner time across 50+ CSEs, because I cannot conduct deep review of every entity every quarter.

**Current State:** 50 CSEs, 5 examiners, quarterly review cycle. Each examiner can deeply review 2-3 CSEs per quarter. 40+ CSEs receive only superficial coverage.

**SAT-SA Solution:** Supervisory Attention Score aggregates multiple signals into entity-level priority ranking. Examiners focus deep review on top 5-10 entities; rest receive baseline monitoring.

### Problem 5: Findings Are Not Traceable or Explainable

**User Story:** As an NCIIPC examiner, I need every finding to trace to specific source records with clear detection rationale, because I must be able to defend supervisory conclusions to auditees and oversight bodies.

**Current State:** Generic anomaly detection system flags "CSE-042 is anomalous." Examiner asks: "Why? Which records? What threshold? What's the alternative explanation?" System cannot answer.

**SAT-SA Solution:** Every finding includes: signal type, contributing record IDs, detection logic, confidence, peer context, recommended review actions, and caveats. Examiner can drill to individual records and validate independently.

---

## 5. Product Features

### 5.1 Data Ingestion & Normalisation

**What it does:** Accepts structured submissions from CSEs in CSV, JSON, or database export formats. Validates against a unified schema. Normalises to a common analytical model. Computes data quality scores.

**User value:** Eliminates the need to manually parse heterogeneous CSE submissions. Ensures consistent data quality across the portfolio.

**MVP status:** Implemented

### 5.2 Behavioral Profiling

**What it does:** Computes per-CSE behavioral profiles across 10+ dimensions: alert volume, severity distribution, investigation depth, closure velocity, escalation rate, evidence completeness, temporal patterns, and quality trends.

**User value:** Transforms raw operational data into meaningful supervisory metrics that examiners understand and trust.

**MVP status:** Implemented (6 core dimensions)

### 5.3 Execution Gap Engine

**What it does:** Detects patterns where operational evidence contradicts claimed capability. MVP implements 3 signals: superficial closures, escalation without action, and investigation quality degradation.

**User value:** Surfaces the "illusion of maturity" — SOCs that look compliant on paper but are not performing meaningful operational work.

**MVP status:** Implemented (3 of 8 planned signals)

### 5.4 Negative Space Engine

**What it does:** Identifies expected evidence that is absent. MVP implements 2 signals: alert volume gaps and missing investigations for high-severity alerts.

**User value:** Makes absence of evidence visible. Detects monitoring blind spots, dead sensors, and undocumented processes.

**MVP status:** Implemented (2 of 7 planned signals)

### 5.5 Peer Benchmarking

**What it does:** Groups CSEs by sector and size. Computes z-scores and percentiles for key metrics. Flags statistical outliers.

**User value:** Provides context for raw metrics. Helps examiners distinguish "different" from "concerning."

**MVP status:** Implemented (basic grouping)

### 5.6 Supervisory Attention Score

**What it does:** Aggregates detected signals into an entity-level priority score. Ranks CSEs for manual review.

**User value:** Directs limited examiner time to highest-priority entities. Quantifies "where should we look first?"

**MVP status:** Implemented

### 5.7 Finding Generation & Evidence Tracing

**What it does:** Generates structured findings with signal type, severity, confidence, contributing records, detection rationale, and recommended review actions. Enables drill-down to individual records.

**User value:** Provides examiners with auditable, explainable findings that trace directly to source evidence.

**MVP status:** Implemented (basic)

### 5.8 Dashboard

**What it does:** Three interactive views: portfolio overview, entity deep-dive, and finding detail with evidence drill-down.

**User value:** Provides intuitive, decision-ready interface for examiners. No SQL or data science skills required.

**MVP status:** Implemented (3 core views)

### 5.9 Signal Fusion (Post-MVP)

**What it does:** Combines multiple weak signals into higher-confidence supervisory cases through correlation and Bayesian aggregation.

**User value:** Reduces false positives. Increases confidence when multiple indicators point to the same underlying issue.

**MVP status:** Planned

### 5.10 Explainability Engine (Post-MVP)

**What it does:** Generates comprehensive rationale for every finding, including alternative explanations, caveats, and detection method documentation.

**User value:** Ensures findings are defensible to auditees and oversight bodies. Supports examiner judgment, not replaces it.

**MVP status:** Partial (basic rationale)

---

## 6. User Experience Flows

### Flow 1: Portfolio Review

```
Examiner logs in
    ↓
Views portfolio overview (50 CSEs ranked by Supervisory Attention Score)
    ↓
Filters by sector, size, finding severity
    ↓
Identifies top 5 entities requiring attention
    ↓
Clicks on CSE-042 for deep dive
```

**Time:** 2-3 minutes

### Flow 2: Entity Investigation

```
Examiner views CSE-042 profile
    ↓
Reviews behavioral metrics: alert volume, investigation depth, closure velocity
    ↓
Sees 3 findings listed with severity and confidence
    ↓
Clicks on execution gap finding
    ↓
Views finding explanation, contributing records, peer comparison
    ↓
Drills into specific investigation record (ID: 042-8821)
    ↓
Reviews investigation notes, timestamps, evidence entries
    ↓
Compares to Q1 baseline (same alert type, higher quality)
    ↓
Forms supervisory judgment: "Quality decline is real and significant"
    ↓
Documents finding in NCIIPC review system
```

**Time:** 10-15 minutes per entity (vs. 2-3 hours for manual-only review)

### Flow 3: Finding Validation

```
Examiner receives SAT-SA finding: "CSE-089: 0 endpoint alerts despite claimed EDR"
    ↓
Reviews finding explanation and detection rationale
    ↓
Checks caveats: "Could be data reporting gap vs. actual monitoring failure"
    ↓
Drills into alert source distribution: confirms no endpoint-based alerts in any quarter
    ↓
Compares to peer baseline: peers generate 380+ endpoint alerts/month
    ↓
Forms supervisory judgment: "Likely EDR monitoring gap. Recommend on-site verification."
    ↓
Adds to review queue for CSE-089
```

**Time:** 5-10 minutes per finding

---

## 7. Business Value Proposition

### For NCIIPC

**Operational Efficiency:**
- Reduces manual review effort by 60-70% while maintaining coverage
- Enables supervision of 50+ CSEs with 5 examiners (vs. current 15-20 CSE capacity)
- Cuts quarterly review cycle from 3 weeks to 1 week

**Supervisory Quality:**
- Detects execution gaps and negative space that manual sampling misses
- Provides evidence-backed findings that are defensible to auditees and oversight
- Standardises detection logic across examiners (reduces variability)

**Strategic Insight:**
- Portfolio-wide trend analysis reveals sector-wide patterns
- Peer benchmarking identifies best practices and systemic weaknesses
- Expected-evidence model makes explicit what "good supervision" looks like

### For CSEs (Indirect)

**Operational Improvement:**
- Expected-evidence model provides implicit benchmark for SOC maturity
- Findings (when shared) highlight specific improvement areas
- Peer context enables self-assessment against comparable entities

**Transparency:**
- Clear detection rationale reduces "surprise findings"
- Evidence-backed conclusions are easier to act on

### For Indian Critical Infrastructure

**National Security:**
- Earlier detection of SOC operational weaknesses reduces risk of undetected attacks
- Portfolio-wide supervision ensures no critical entity falls through cracks
- Evidence-based oversight strengthens national cyber resilience

---

## 8. Competitive Positioning

### What SAT-SA Is NOT

| Product Category | Why SAT-SA Is Not It |
|------------------|---------------------|
| **SIEM** | SAT-SA does not monitor networks, generate alerts, or respond to incidents in real time |
| **SOC Platform** | SAT-SA does not aggregate operational control of multiple SOCs |
| **KPI Dashboard** | SAT-SA does not display SLA compliance charts or closure rate gauges |
| **Compliance Tool** | SAT-SA does not score compliance or issue certificates |
| **Generic AI Analytics** | SAT-SA is not a black-box ML model generating "insights" |
| **Audit Management System** | SAT-SA does not manage audit workflows or track remediation |

### What SAT-SA IS

| Product Category | Why SAT-SA Is Unique |
|------------------|---------------------|
| **Supervisory Analytics** | Only product designed for government supervisors, not SOC operators |
| **Evidence-Integrity Analysis** | Models SOC operations as workflows; detects broken evidence chains |
| **Expected-Value Comparison** | Builds CSE-specific models of "what should be observed" |
| **Negative-Space Detection** | Systematically identifies absent evidence as a supervisory signal |
| **Signal Fusion** | Combines weak signals into high-confidence supervisory cases |
| **Explainable Findings** | Every finding traces to source records with clear rationale |

### Competitive Alternatives (and why they don't solve the problem)

| Alternative | Limitation |
|-------------|-----------|
| **Manual review + sampling** | Does not scale; coverage gaps as portfolio grows |
| **Generic BI dashboard** | Shows what happened; does not model what should have happened |
| **Anomaly detection platform** | Flags outliers without supervisory context or evidence tracing |
| **Audit/compliance tool** | Focuses on policy conformance, not operational effectiveness |
| **SIEM correlation rules** | Operational, not supervisory; requires real-time data feed |
| **ChatGPT wrapper** | No evidence tracing, no reproducibility, no auditability |

---

## 9. Product Principles

These principles guide every product decision:

### 1. Supervisor-First Design

SAT-SA is designed for NCIIPC examiners, not SOC analysts. Every feature, metric, and finding is framed in supervisory terms: "Is the SOC operating effectively?" not "What threats were detected?"

### 2. Evidence Over Opinion

Every finding must trace to specific source records. No finding without evidence. No evidence without traceability. No traceability without explainability.

### 3. Preserve Human Authority

The system identifies. The examiner decides. SAT-SA never makes compliance determinations or supervisory conclusions. It surfaces conditions warranting examination.

### 4. Explainability Is Non-Negotiable

A finding that cannot be explained to an examiner in 30 seconds is rejected. Black-box scores are unacceptable. Every detection method, threshold, and confidence level is documented.

### 5. Transparency About Limitations

The system states what it cannot detect, where false positives are likely, and what alternative explanations exist. Honesty about limitations builds trust with examiners.

### 6. Offline-First, Air-Gap-Ready

NCIIPC operates in air-gapped environments. SAT-SA never depends on cloud services, external APIs, or runtime Internet connectivity.

### 7. Deterministic Core, Augmented Analytics

Prefer rule-based and statistical methods over ML for primary detection. Use ML only where it provides measurable value beyond deterministic methods. All ML is local, explainable, and optional.

---

## 10. Product Roadmap

### Phase 1: MVP (Weeks 1-5)

**Goal:** Demonstrate core value proposition with 5 detection signals and 3 dashboard views.

**Key Features:**
- Sample data generation (50 CSEs, 4 quarters)
- Data ingestion and normalization
- Behavioral profiling
- 3 execution gap signals
- 2 negative space signals
- Peer benchmarking
- Supervisory Attention Score
- Finding generation with evidence tracing
- Dashboard (portfolio, entity, finding views)
- 2-minute demo

**Success Criteria:**
- All seeded weaknesses detected
- Supervisory Attention Score ranks weak entities in top 10
- Demo executes smoothly in ≤2 minutes

### Phase 2: Enhanced Analytics (Weeks 6-8)

**Goal:** Implement remaining signal groups and signal fusion.

**Key Features:**
- Signal fusion engine (combine weak signals into supervisory cases)
- Remaining 5 execution gap signals
- Remaining 5 negative space signals
- KPI-reality divergence detection
- Temporal drift detection (change-point)
- Cyclical/temporal anomalies
- Investigation quality heuristics (rule-based)
- Enhanced explainability (alternative explanations, caveats)

**Success Criteria:**
- All 8 signal groups implemented
- Signal fusion produces supervisory cases
- Precision and recall measured on synthetic data

### Phase 3: Validation & Calibration (Weeks 9-10)

**Goal:** Validate detection performance against expert judgment.

**Key Features:**
- Validation harness
- Precision/recall measurement
- Examiner agreement scoring
- Threshold calibration
- False positive analysis

**Success Criteria:**
- Coverage ≥ 70% (manual findings detected)
- Precision ≥ 60% (findings judged worthy of review)
- Examiner alignment score ≥ 0.7

### Phase 4: Polish & Deployment (Weeks 11-12)

**Goal:** Production-ready prototype for SIH submission.

**Key Features:**
- Dashboard UX polish
- Report export (HTML, PDF)
- Offline deployment packaging (Docker)
- Complete documentation
- SIH presentation and demo

**Success Criteria:**
- Runnable in air-gapped environment
- All documentation complete
- Demo and presentation ready

### Post-SIH Roadmap

| Phase | Timeline | Deliverable |
|-------|----------|-------------|
| **Real Data Integration** | 1-2 months | Replace synthetic data with actual CSE submissions; adapt schema to real formats |
| **Advanced Peer Grouping** | 2-3 months | Clustering-based peer groups with multiple normalization factors |
| **ML Components** | 3-4 months | NLP for investigation notes, anomaly detection, trend forecasting |
| **Examiner Feedback Loop** | 4-6 months | Examiner ratings of findings feed back into threshold calibration |
| **Production Deployment** | 6-12 months | Deploy in NCIIPC environment; integrate with existing data pipelines |
| **Portfolio Expansion** | Ongoing | Scale to 100+ CSEs; add new sectors and asset types |

---

## 11. Key Product Metrics

### Detection Performance

- **Coverage:** Proportion of manual supervisory findings that SAT-SA detects (target: ≥70%)
- **Precision:** Proportion of SAT-SA findings that examiners judge worthy of review (target: ≥60%)
- **False Positive Rate:** Proportion of flagged items that are not genuine concerns (target: <40%)
- **Examiner Alignment:** Correlation between SAT-SA priority ranking and examiner judgment (target: ≥0.7)

### Operational Efficiency

- **Review Time Reduction:** Time to identify high-priority entities (target: <5 minutes vs. current 2+ hours)
- **Coverage Improvement:** Proportion of portfolio receiving meaningful review (target: 100% vs. current 30-40%)
- **Finding Quality:** Proportion of findings that lead to productive examiner investigation (target: ≥80%)

### System Performance

- **Pipeline Runtime:** Time to process full portfolio (target: <30 minutes for 50 CSEs)
- **Dashboard Load Time:** Time to render portfolio overview (target: <3 seconds)
- **Uptime:** System availability during review periods (target: 99%+)

### User Satisfaction

- **Examiner Satisfaction:** Post-review survey of SAT-SA usefulness (target: ≥4/5)
- **Explainability Score:** Proportion of findings examiner can explain without developer assistance (target: ≥90%)
- **Recommendation Rate:** Proportion of examiners who would recommend SAT-SA to colleagues (target: ≥80%)

---

## 12. Product Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|-----------|
| **Data quality issues reduce detection** | High | High | Quality scoring; flag low-confidence findings; robust synthetic data for MVP |
| **False positives erode examiner trust** | High | Medium | Signal fusion; peer context; iterative threshold calibration; transparent caveats |
| **Peer grouping is misleading** | Medium | Medium | Disclose peer group definitions; normalize for heterogeneity; conservative outlier thresholds |
| **Scope creep dilutes focus** | High | Medium | Strict scope enforcement; weekly product reviews; "supervisory" vs. "operational" boundary |
| **Judges don't understand the value** | High | Low | Focus demo on examiner experience, not algorithms; clear problem-solution framing |
| **Real data doesn't match synthetic patterns** | Medium | Medium | Flexible schema; adaptive detection logic; post-MVP calibration with real data |

---

## 13. Product Documentation

| Document | Purpose | Audience |
|----------|---------|----------|
| **README.md** | Project overview, architecture, SIH alignment | Judges, developers, technical stakeholders |
| **plan.md** | 12-week implementation plan with tasks and milestones | Development team, project managers |
| **MVP.md** | MVP scope, tasks, and acceptance criteria | Development team, product owner |
| **Product.md** | Product vision, users, features, roadmap | Product team, stakeholders, judges |
| **Architecture.md** | Technical architecture and design decisions | Developers, system architects |
| **API.md** | API documentation | Frontend developers, integrators |
| **User Guide** | How examiners use SAT-SA | NCIIPC examiners (post-MVP) |

---

## 14. Product Principles in Practice

### Principle 1: Supervisor-First Design

**Example:** Instead of showing "1000 alerts/sec" (operational metric), SAT-SA shows "Investigation depth declining 30% while alert volume constant" (supervisory insight).

### Principle 2: Evidence Over Opinion

**Example:** Every finding lists specific alert IDs, investigation records, and timestamps. Examiner can verify independently. No finding without traceable evidence.

### Principle 3: Preserve Human Authority

**Example:** Finding says "Potential investigation effectiveness gap — examiner should verify." Finding does NOT say "CSE-042 is non-compliant." System identifies; examiner decides.

### Principle 4: Explainability Is Non-Negotiable

**Example:** Finding includes: detection method ("closure velocity < 25th percentile AND investigation depth < 25th percentile"), threshold values, confidence calculation, and alternative explanations.

### Principle 5: Transparency About Limitations

**Example:** Finding includes caveats: "Peer comparison assumes comparable alert severity mix. Change-point detection requires 4+ data points; earlier periods unavailable."

### Principle 6: Offline-First, Air-Gap-Ready

**Example:** No external API calls in runtime. All analytics run locally. Docker deployment enables air-gapped installation.

### Principle 7: Deterministic Core, Augmented Analytics

**Example:** Primary detection uses rule-based logic (if X and Y, then flag). Optional ML (NLP, clustering) runs locally and is explainable. No black-box models.

---

## 15. Product-Market Fit

### Why NCIIPC Needs This Now

1. **Portfolio growth:** CSE portfolio expanding beyond manual review capacity
2. **Sophisticated adversaries:** Attacks becoming more stealthy; operational gaps more dangerous
3. **Accountability pressure:** Government stakeholders demanding evidence of supervisory effectiveness
4. **Resource constraints:** Examiner headcount not growing proportionally to portfolio
5. **Technology availability:** CSEs now generate structured operational data that can be analysed

### Why Now Is the Right Time for SAT-SA

- **Data availability:** CSEs are increasingly submitting structured operational data
- **Computational feasibility:** Portfolio-wide analysis is now tractable with modern hardware
- **Methodological maturity:** Supervisory analytics methodology is ready for prototype
- **Government priority:** Cyber resilience of critical infrastructure is a national priority
- **SIH platform:** Smart India Hackathon provides ideal venue to prototype and validate

### Adoption Path

1. **SIH 2026:** Prototype developed and demonstrated
2. **Pilot (6 months):** Deploy with 5-10 volunteer CSEs; refine based on examiner feedback
3. **Expansion (12 months):** Scale to 20-30 CSEs; implement full analytics suite
4. **Production (18 months):** Deploy across full NCIIPC portfolio; integrate with existing workflows
5. **National rollout (24+ months):** Potential adoption by other national supervisory authorities

---

## 16. Product Pricing & Licensing

**Licensing:** SAT-SA is developed for NCIIPC as a government supervisory tool. It is not a commercial product.

**Distribution:**
- Source code available to NCIIPC for audit and modification
- No external dependencies or SaaS components
- Air-gap deployment package provided

**Support:**
- Development team provides documentation and training
- NCIIPC IT team maintains deployment
- Ongoing development funded through subsequent government programs

---

## 17. Product Team

| Role | Responsibility | SIH Role |
|------|---------------|----------|
| **Product Owner** | Vision, scope, priorities, stakeholder management | Team lead |
| **Backend Lead** | Ingestion, analytics, APIs, database | Developer |
| **Analytics Lead** | Detection engines, signal design, validation | Developer |
| **Frontend Lead** | Dashboard, UX, visualization | Developer |
| **Validation Lead** | Test design, precision/recall, examiner coordination | Developer |
| **Subject Matter Expert** | NCIIPC supervisory methodology, validation | Advisor (NCIIPC) |

---

## 18. Product Glossary

| Term | Definition |
|------|-----------|
| **CSE** | Critical Sector Entity — organisation operating in a critical infrastructure sector under NCIIPC supervision |
| **SOC** | Security Operations Centre — team responsible for monitoring, detection, investigation, and response |
| **Execution Gap** | Divergence between reported SOC capability and actual operational behavior |
| **Negative Space** | Absence of expected evidence that should be present if the SOC were operating effectively |
| **Supervisory Attention Score** | Weighted aggregation of detected signals into entity-level priority ranking |
| **Supervisory Case** | Collection of correlated signals indicating the same underlying operational weakness |
| **Peer Benchmarking** | Comparison of entity metrics against normalized peer baselines |
| **Expected-Evidence Model** | CSE-specific prediction of what evidence should be observed given claims, assets, and history |
| **Finding** | Structured observation with rationale, evidence, and recommended review action |
| **Examiner** | NCIIPC supervisor responsible for reviewing findings and making supervisory judgments |

---

## 19. Product One-Pager (For Judges)

**Problem:** NCIIPC supervises 50+ critical infrastructure entities by manually reviewing SOC evidence. Manual review doesn't scale. KPIs and dashboards miss execution gaps and negative space.

**Solution:** SAT-SA applies supervisory analytics to periodic CSE submissions, detecting operational weaknesses and evidence gaps that conventional tools miss.

**Key Innovation:** Evidence-Integrity Analysis through Expected-Value Comparison and Signal Fusion — modeling SOC operations as workflows, comparing observed evidence against expected, and fusing weak signals into high-confidence findings.

**Demo:** 2-minute demo showing portfolio overview, execution gap detection, negative space detection, peer benchmarking, and evidence drill-down.

**Impact:** Enables NCIIPC to supervise 50+ CSEs with 5 examiners while maintaining depth and rigour of expert human examination.

**Status:** MVP prototype ready for SIH26157 evaluation.

---

*Last updated: 2026-08-22*  
*Status: Product Definition Complete — Aligned with MVP and Full Plan*
