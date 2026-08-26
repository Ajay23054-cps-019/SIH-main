# SAT-SA — Final Demo Checklist

**Last updated:** 2026-08-26  
**Status:** Ready for SIH judging

---

## One-Command Demo

```bash
python scripts/demo.py
```

This regenerates data, runs the full pipeline, prints validation, and starts the server. Dashboard: `http://localhost:8000/dashboard/`

---

## Pre-Demo Setup (5 minutes before judges arrive)

- [ ] Run `python scripts/demo.py` (takes ~2 minutes)
- [ ] Open `http://localhost:8000/dashboard/` in a maximized browser
- [ ] Set browser zoom to 125%
- [ ] Hide bookmarks bar, disable notifications
- [ ] Verify offline: disconnect network, reload page, charts still render

---

## 2-Minute Demo Flow

| Time | What | Key Message |
|------|------|-------------|
| 0:00-0:10 | Problem | "KPIs look green while investigations get shallower" |
| 0:10-0:30 | Portfolio | 50 CSEs ranked, CSE-042 #1 with 8 findings |
| 0:30-0:50 | Execution gap | CSE-042: depth 4.8→1.5, velocity 2.6h→1.3h, change at Q3 |
| 0:50-1:10 | Evidence | Full chain: finding → signal → metric → records |
| 1:10-1:30 | Negative space | CSE-089: 0 endpoint alerts / 2669 total; CSE-017: 2370 vs 7878 expected |
| 1:30-1:45 | Peer context | CSE-042: z=-115 vs peer mean, not borderline |
| 1:45-2:00 | Close | 8/8 seeded detected, 0 false positives, examiner decides |

---

## Verified Numbers (from latest pipeline run)

| Claim | Actual | Source |
|-------|--------|--------|
| CSE-042 Q1 depth | 4.82 | behavioral_profiles metrics_json |
| CSE-042 Q4 depth | 1.48 | behavioral_profiles metrics_json |
| CSE-042 decline | 69% | (4.82-1.48)/4.82 |
| CSE-042 change quarter | 2024-Q3 | findings evidence_json |
| CSE-089 endpoint alerts | 0 of 2669 | alerts table |
| CSE-017 evidence entries | 2370 | investigations table |
| CSE-017 expected evidence | 7878 | findings evidence_json |
| CSE-042 peer mean depth | 4.88 | peer_benchmarks table |
| CSE-042 z-score | -115.3 | peer_benchmarks table |
| Coverage | 100% (8/8) | validation harness |
| Precision | 100% | validation harness |
| False-positive rate | 0% | validation harness |
| Examiner alignment | 0.909 | validation harness |

---

## Fallbacks

| Failure | Recovery |
|---------|----------|
| Live demo won't boot | Screenshots in `docs/demo_screenshots/` |
| Single page slow | Re-run pipeline during Q&A (~45s) |
| Judge asks unfamiliar number | Open `/docs` (Swagger), call live endpoint |
| Browser crash | `python scripts/demo.py` restarts in ~2 min |

---

## Key Files for Judges

| File | What it shows |
|------|--------------|
| `docs/demo_script.md` | Full 2-minute script with timing |
| `docs/validation_report.md` | Detection performance metrics |
| `docs/demo_screenshots/` | Backup screenshots of all views |
| `docs/canonical_schema.md` | Data model documentation |
| `docs/post_mvp_roadmap.md` | Future capabilities |

---

## Team Talking Points

- **What is SAT-SA?** A supervisory analytics tool that reads SOC records and finds what KPIs miss.
- **What makes it different?** Evidence-backed findings with full traceability, not black-box scores.
- **How does it handle missing data?** Data quality assessment runs first; missing data generates warnings, not findings.
- **Why is the LLM optional?** The analytical engine is deterministic/statistical; the LLM only generates explanations.
- **How does it run offline?** All dependencies are local Python packages; no cloud, no external APIs.
- **What's the minimum demo?** Load data → run analytics → show rankings → drill into findings → show evidence.
- **What's novel?** Execution gap detection, negative space detection, evidence chain tracing, supervisory attention prioritization.
