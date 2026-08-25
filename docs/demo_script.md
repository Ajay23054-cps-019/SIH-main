# SAT-SA — 2-Minute Demo Script

**Setup (before judges arrive, one command):**

```bash
./venv/bin/python scripts/load_demo_data.py     # ~45 s, regenerates data/sat_sa.db
make run                                        # serves http://localhost:8000
```

Open `http://localhost:8000/dashboard/` in a maximized browser window.
Everything runs locally — no internet needed at any point.

---

## [0:00–0:10] Problem

> "NCIIPC supervises dozens of critical-sector SOCs. Quarterly KPI dashboards
> show alert volumes and closure times — all green. But they can't show
> whether investigations are getting *shallower*, or whether an entity
> simply stopped sending evidence. SAT-SA reads the raw SOC records and
> finds what KPIs miss."

**Screen:** Portfolio overview — 50 CSEs ranked.

## [0:10–0:30] Portfolio view

> "Fifty CSEs from telecom, financial services, and power, analyzed as one
> portfolio. Every entity gets a Supervisory Attention Priority — explicitly
> *not* a risk or compliance score; it just orders where an examiner's next
> hour goes. The top of this queue is dominated by seeded weak SOCs our
> team injected into the data beforehand.
>
> Number one is CSE-042 — seven findings, which the fusion layer has
> combined into a single supervisory case. Let's see why."

**Screen:** Point at the ranked table (CSE-042 #1 at 89.1, CSE-031 #2 at
88.5). Click the **CSE-042** row → entity view.

## [0:30–0:50] Execution gap

> "Investigation depth fell from **4.8 evidence entries per investigation**
> in Q1 to **1.5 in Q4** — a 69% decline. Same period, closures got
> *faster* — 2.6 hours down to 1.3. SAT-SA has a named signal for exactly
> this pairing: **kpi_divergence**. Reported speed improving while review
> depth drains is the metric-gaming pattern — the thing a KPI dashboard can
> never see about itself. And a second signal dates the break: depth held
> near **4.7 entries** through 2024-Q2, then stepped down to **1.9** —
> the decline starts at **2024-Q3**. A decline with a start date is a
> question you can ask: *what changed that quarter?*"

**Screen:** Entity view — the amber **Supervisory Case** banner first
("7 findings across 3 categories, joint confidence 1.00"), then profile
cards + findings list. Click `changepoint_drift` → finding view.

## [0:50–1:10] Evidence drill-down

> "Every finding carries its full evidence chain — finding, signal, metric,
> down to individual records. This one states its own threshold *and* the
> quarter it dates the break to, with the before/after levels and how much
> of the variance that split explains. An examiner can audit the analytics
> itself, not just the conclusion."

**Screen:** Finding view for `changepoint_drift` — rationale, evidence
table (`change_quarter`, `mean_before`, `mean_after`, `explained_share`).

## [1:10–1:25] Negative space

> "Back in the queue — CSE-089 manages **217 endpoint assets**, and peers
> report endpoint alerts universally. CSE-089's endpoint alert count?
> **Zero**, out of 2,669 alerts. That's negative space: expected evidence
> that is absent. Broken EDR, disabled monitoring, or unsubmitted data —
> either way, it's NCIIPC's question to ask."

**Screen:** Navigate to `/dashboard/entity/CSE-089` (or use browser back +
table). Show the missing_alert_categories finding.

## [1:25–1:45] Peer context

> "Findings also come with peer context. CSE-042 sits in the
> Telecom-Large group. Peer mean investigation depth: **4.9 entries**.
> CSE-042: **3.3** — double-digit standard deviations below, far past the
> |z| > 2.5 outlier gate. Not borderline; a clear deviation worth a letter,
> not a phone call."

**Screen:** Entity view peer-comparison chart (bottom panel).

## [1:45–2:00] Close

> "SAT-SA doesn't replace examiners — it extends their reach: raw SOC data
> through profiling, signal detection, peer benchmarking, into an
> evidence-backed, prioritized review queue. Validation on our seeded
> dataset: eight of eight weaknesses detected, zero high-severity false
> alarms across forty-two clean entities — and exactly four supervisory
> cases formed, every one a seeded weak entity. The system identifies. The
> examiner decides."

**Screen:** Back to portfolio overview for the closing frame.

---

## Rehearsal checklist

- [ ] Full run timed at ≤ 2:00 (three consecutive clean takes)
- [ ] Each team member can explain any finding in < 30 s
- [ ] `load_demo_data.py` run fresh before the demo (deterministic seed 42)
- [ ] Browser zoom 125%, no bookmarks bar, no notifications
- [ ] Offline verified: disconnect network, reload page, charts still render
      (Chart.js is bundled at `/dashboard/static/js/lib/chart.umd.min.js`)

## Fallbacks

| Failure | Recovery |
|---------|----------|
| Live demo won't boot | Screenshots in `docs/demo_screenshots/` (capture guide inside) |
| Single page slow | Re-run pipeline during Q&A; rankings rebuild in ~45 s |
| Judge asks a number you don't remember | Open `/docs` (Swagger) and call the live endpoint — every number on screen comes from the API |
