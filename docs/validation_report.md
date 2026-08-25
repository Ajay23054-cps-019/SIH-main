# SAT-SA Validation Report

Dataset: `data/samples/demo_dataset` · ground truth: `scripts/design_test_cases.py`

> Findings are potential supervisory concerns, not determinations of non-compliance. Attention Priority orders review; it is not a risk or compliance score.

## Headline metrics

| Metric | Definition | Result | Target | Status |
|--------|------------|-------:|--------|--------|
| Coverage (recall) | oracle cases fully detected / 8 | 100% (8/8) | >= 70% | PASS |
| Precision (signal level) | required detections / (required + HIGH on clean) | 100% | >= 60% | PASS |
| False-positive rate | HIGH findings on clean CSEs / total | 0% | < 40% | PASS |
| Examiner alignment | Spearman(priority, oracle order), n=8 + clean | 0.909 | >= 0.70 | PASS |

Secondary framing — precision counting every finding on a seeded CSE as true: **93%** (both framings exceed target; definitions differ only in how corroborating signals on already-flagged CSEs are treated).

## Case-by-case results

### CSE-042 — degrading_depth [PASS]

Investigation depth declines quarter over quarter (quality degradation with temporal drift)

- ✅ `quality_degradation` fired (confidence 0.990)
- ✅ `temporal_drift` fired (confidence 0.935)
- ℹ️ additional signals: `changepoint_drift`, `closure_velocity_outlier`, `investigation_depth_outlier`, `kpi_divergence`, `superficial_closure` (corroborating; not required by the oracle)

### CSE-017 — superficial_closures [PASS]

Alerts closed fast and shallow — superficial closure pattern

- ✅ `superficial_closure` fired (confidence 0.758)
- ℹ️ additional signals: `closure_velocity_outlier`, `escalation_absence`, `escalation_rate_outlier`, `investigation_depth_outlier` (corroborating; not required by the oracle)

### CSE-089 — missing_telemetry [PASS]

Entire alert category absent while peers report it (telemetry gap)

- ✅ `missing_alert_categories` fired (confidence 0.600)

### CSE-031 — missing_investigations [PASS]

Most critical alerts never receive an investigation

- ✅ `missing_investigations` fired (confidence 1.000)
- ℹ️ additional signals: `closure_velocity_outlier`, `escalation_rate_outlier`, `investigation_depth_outlier`, `severity_mismatch` (corroborating; not required by the oracle)

### CSE-055 — fast_closure_outlier [PASS]

Closure velocity far outside the peer group

- ✅ `closure_velocity_outlier` fired (confidence 1.000)

### CSE-073 — weekend_escalation_gap [PASS]

Weekend critical alerts but zero weekend escalations

- ✅ `escalation_absence` fired (confidence 0.900)

### CSE-019 — templated_investigations [PASS]

Investigation notes drawn from boilerplate templates

- ✅ `template_investigation` fired (confidence 0.987)

### CSE-061 — combined_weak [PASS]

Combined weak SOC: shallow depth far below peers

- ✅ `investigation_depth_outlier` fired (confidence 1.000)
- ℹ️ additional signals: `closure_velocity_outlier`, `escalation_rate_outlier`, `escalation_without_action`, `superficial_closure` (corroborating; not required by the oracle)

## Portfolio-level observations

- 28 findings across the portfolio (21 HIGH, 3 LOW, 4 MEDIUM).
- HIGH-severity findings on non-seeded CSEs: **0**.
- LOW/MEDIUM informational findings on clean CSEs: **2** — isolated metric tails reviewed during tuning: `investigation_depth_outlier` on CSE-024; `closure_velocity_outlier` on CSE-032.

## Limitations (read before quoting these numbers)

- Ground truth is the injection map of a *synthetic* generator; results demonstrate detection capability on known patterns, not field performance.
- Absence-style (negative space) signals carry capped confidence by design; their thresholds in the oracle reflect that evidence asymmetry rather than detector quality.
- A few clean CSEs earn single LOW informational findings from isolated statistical tails (multiple comparisons across ~36 metrics x 50 CSEs); they surface at the bottom of the queue and never at HIGH severity.
- Examiner alignment uses one synthetic ranking oracle; human examiner correlation is future work.
