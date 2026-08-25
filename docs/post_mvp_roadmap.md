# SAT-SA — Post-MVP Roadmap

The MVP (Phases 0–14) is complete and demo-ready. This document separates
**what we deliberately did not build yet** from the MVP, so judges can see
the trajectory without mistaking roadmap for reality. Everything below is
unimplemented as of today unless explicitly marked otherwise.

> Framing invariant that carries forward: every future capability outputs
> *potential supervisory concerns* and review prioritization — never
> compliance determinations, never risk scores.

---

## Capability Table

| # | Capability | Priority | Effort | Status | What it adds |
|---|------------|----------|--------|--------|--------------|
| 1 | **KPI–Reality Divergence** | High | ~3 days | **Shipped 2026-08-25** | Flags metric gaming: closure velocity improves while investigation depth declines over the same window (`kpi_divergence` execution-gap signal; fires on CSE-042 only, HIGH/1.0, zero clean-CSE firings — thresholds set at 2× measured clean-portfolio slope noise) |
| 2 | **Signal Fusion Engine** | High | 1–2 wks | — | Combine multiple weak signals into one high-confidence supervisory case with joint evidence; today corroboration is visible (a CSE with 5 findings) but not scored jointly |
| 3 | **Temporal Drift v2 (change-point detection)** | High | 1 wk | — | Replace the current linear-slope drift test with CUSUM/PELT change-point estimation → names the quarter the decline started (demo script already narrates this manually) |
| 4 | **Full Expected Evidence Model** | High | 2–3 wks | — | Bayesian expected-vs-observed per (sector, size, asset mix) with uncertainty bands — generalizes negative-space beyond "category absent" to "evidence thinner than expected" |
| 5 | **Investigation Quality NLP** | Medium | 2 wks | Partial¹ | Upgrade template detection from exact-match boilerplate to text-similarity clustering (TF-IDF/embedding), catching paraphrased templating |
| 6 | **Clustering-Based Peer Grouping** | Medium | 1 wk | — | K-means/DBSCAN behavioral peer groups alongside the rule-based (sector, size) groups; disagreement between the two groupings is itself a signal |
| 7 | **Examiner Feedback Loop** | Medium | 1 wk | — | Examiner dispositions (worthwhile / not worthwhile) stored per finding, feeding threshold calibration and attention-weight tuning |
| 8 | **Multi-Period Portfolio Trends** | Low | 1 wk | — | Portfolio-wide quarter-over-quarter dashboards (is depth declining everywhere, or only at CSE-042?) |
| 9 | **PDF Report Export** | Low | 1 wk | — | Printable per-entity examiner brief: findings, chains, peer context, recommended questions |
| 10 | **Advanced Data Quality** | Low | 1 wk | — | Statistical outlier detection on submissions (impossible timestamps, duplicated records) feeding the existing quality gate |
| 11 | **Graph Analytics** | Low | 2 wks | — | Asset–alert–investigation–case relationship mapping; recurring-asset weak points |
| 12 | **Streaming Ingestion** | Low | 3 wks | — | Near-real-time feeds; changes the supervision cadence, not the analytics |
| 13 | **PostgreSQL Migration** | Low | 1 wk | — | Production-scale store behind the existing SQLAlchemy layer |

¹ *Partial: the MVP's `template_investigation` signal already detects exact
boilerplate notes (CSE-019, confidence 0.987). NLP extends this to
paraphrased templating.*

## Deliberately Out of Scope (never building)

- Real-time SOC monitoring or alerting
- SIEM correlation / threat detection
- Network packet analysis
- Cloud deployment (NCIIPC target is air-gapped)
- External API integrations
- Generic AI chatbot
- Compliance certification or scoring

## Sequencing (post-SIH)

- **Month 1–2:** #1 KPI–Reality Divergence → #2 Signal Fusion → #3 change-point drift
- **Month 3–4:** #5 Investigation NLP → #6 clustering peer groups
- **Month 5–6:** #7 examiner feedback loop → first real-data validation alongside NCIIPC examiners
- **Month 7–12:** production hardening (#9–#13) under NCIIPC deployment

---

## What the MVP already demonstrates of each theme

Judges may ask how much of the roadmap is "already there". Honest answers:

- **Divergence (1):** shipped as the `kpi_divergence` signal — the demo
  narrative's "closures faster, depth declining" pattern is now a single
  self-contained detector with its own evidence chain.
- **Fusion (2):** attention priority already aggregates findings per CSE, but
  treats them as independent; #2 models their joint evidential weight.
- **Negative space (4):** `missing_alert_categories` and
  `missing_investigations` implement absence detection with peer-presence
  gating; #4 replaces binary absence with calibrated expectation.
- **Feedback (7):** thresholds are already externalized in
  `data/config/thresholds.json`; #7 adds the loop that tunes them.
