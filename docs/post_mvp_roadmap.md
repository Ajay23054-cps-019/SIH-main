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
| 2 | **Signal Fusion Engine** | High | 1–2 wks | **Shipped 2026-08-25** | Per-CSE findings that clear the fusion gates (≥2 findings across ≥2 categories) become a **supervisory case** with noisy-OR joint confidence, max severity, an independence caveat, and a member-finding index (`src/analytics/fusion.py`, `supervisory_cases` table, `/api/cases`, entity-page case banner). On the demo portfolio exactly 4 cases form — all on seeded weak CSEs; clean CSEs (1 finding each) stay case-free |
| 3 | **Temporal Drift v2 (change-point detection)** | High | 1 wk | **Shipped 2026-08-25** | `changepoint_drift` behavioral signal: exhaustive single-change-point search on quarterly depth (both segments ≥2 quarters, two-level model must explain ≥60% of window variance) → names the quarter the decline started. CSE-042: onset 2024-Q3, 4.75 → 1.86 entries, 97% of variance explained; zero clean-CSE firings |
| 4 | **Full Expected Evidence Model** | High | 2–3 wks | **Shipped 2026-08-25** | `src/analytics/expected_evidence.py`: per-CSE expected-vs-observed across four evidence dimensions (alerts, investigations, evidence entries, escalations), every baseline estimated **leave-self-out** and conditioned on the CSE's own size band / severity mix, with 3σ negative-binomial uncertainty bands (`/api/evidence-model/{cse_id}`). The `evidence_deficit` signal fires only when a dimension clears BOTH its calibrated ratio gate AND the band's lower edge — generalizing negative space from "category absent" to "quantitatively thin". Demo portfolio: CSE-017 at 30% of expected entries (2,370 vs 7,878) — fires on exactly the 4 seeded thin CSEs, zero clean |
| 5 | **Investigation Quality NLP** | Medium | 2 wks | Partial¹ | Upgrade template detection from exact-match boilerplate to text-similarity clustering (TF-IDF/embedding), catching paraphrased templating |
| 6 | **Clustering-Based Peer Grouping** | Medium | 1 wk | — | K-means/DBSCAN behavioral peer groups alongside the rule-based (sector, size) groups; disagreement between the two groupings is itself a signal |
| 7 | **Examiner Feedback Loop** | Medium | 1 wk | **Shipped 2026-08-25** | One disposition per finding (worthwhile / not_worthwhile / uncertain, latest wins) stored in `examiner_feedback`; `/api/feedback/summary` joins dispositions to signal types and emits **advisory-only** calibration notes once a signal has ≥5 dispositions (e.g. "consider tightening…" below a 30% worthwhile rate) — recommendations are never auto-applied to thresholds or rankings; disposition buttons live on each finding page |
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

- **Month 1–2:** #1 KPI–Reality Divergence → #2 Signal Fusion → #3 change-point drift → #4 expected evidence model *(all four shipped 2026-08-25)*
- **Month 3–4:** #5 Investigation NLP → #6 clustering peer groups
- **Month 5–6:** #7 examiner feedback loop *(shipped 2026-08-25)* → first real-data validation alongside NCIIPC examiners
- **Month 7–12:** production hardening (#9–#13) under NCIIPC deployment

---

## What the MVP already demonstrates of each theme

Judges may ask how much of the roadmap is "already there". Honest answers:

- **Divergence (1):** shipped as the `kpi_divergence` signal — the demo
  narrative's "closures faster, depth declining" pattern is now a single
  self-contained detector with its own evidence chain.
- **Fusion (2):** shipped as `src/analytics/fusion.py` — cross-category
  findings fuse into supervisory cases with joint confidence; attention
  priority itself still treats findings independently (deliberate: fusion
  informs review, it does not reweight the queue).
- **Change-point (3):** shipped as the `changepoint_drift` signal — the
  onset quarter is now detected, dated, and carried in the evidence chain.
- **Expected evidence (4):** shipped as `src/analytics/expected_evidence.py`
  + the `evidence_deficit` signal — expectations condition on size band and
  severity mix (the composition that actually drives evidence volume);
  asset-mix conditioning for telemetry remains where it already was
  (`alert_volume_gap`, peer benchmarks), and sector is carried as context
  rather than a baseline dimension.
- **Negative space (4):** `missing_alert_categories` and
  `missing_investigations` implement absence detection with peer-presence
  gating; #4 replaces binary absence with calibrated expectation.
- **Feedback (7):** shipped as `src/feedback.py` + the finding-page
  disposition buttons — dispositions are stored and summarized into
  advisory calibration notes; the loop informs the examiner, it does not
  tune thresholds by itself (deliberate: a human applies any change).
