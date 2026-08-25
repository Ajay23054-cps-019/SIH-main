# Backup Screenshots — Capture Guide

The demo machine must capture these PNGs itself (screenshots are
machine-specific renders of the live dashboard, so they are not committed).
Capture at 1920×1080, browser zoom 125%, after a fresh pipeline run.

```bash
./venv/bin/python scripts/load_demo_data.py && make run
# then screenshot each URL below (F12 device toolbar off; full window)
```

| File name | URL | Shows |
|-----------|-----|-------|
| `01_portfolio.png` | `/dashboard/` | Ranked table, summary cards |
| `02_entity_cse042.png` | `/dashboard/entity/CSE-042` | Profile cards, findings list, peer chart |
| `03_finding_quality_degradation.png` | `/dashboard/finding/CSE-042:quality_degradation` | Rationale + evidence chain, one record row expanded |
| `04_entity_cse089_negative_space.png` | `/dashboard/entity/CSE-089` | missing_alert_categories finding (zero endpoint alerts vs 217 endpoint assets) |
| `05_swagger.png` | `/docs` | Live API contract (for "every number comes from the API") |
| `06_finding_changepoint.png` | `/dashboard/finding/CSE-042:changepoint_drift` | Change-point finding: onset quarter, before/after depth means, explained variance in the metric chain |
| `07_finding_evidence_deficit.png` | `/dashboard/finding/CSE-017:evidence_deficit` | Expected-evidence model: observed vs leave-self-out expected counts with the 3σ band |

Naming matters: in the fallback walkthrough the presenter types only
`01_`, `02_`, … and narrates from `docs/demo_script.md`.

**Verify before demo day:** every PNG opens on a machine with no dev
tools, and the numbers visible match the current `docs/demo_script.md`
(regenerate screenshots whenever the dataset is regenerated with a new
seed).
