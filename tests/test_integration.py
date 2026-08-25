"""End-to-end integration tests (Phase 12).

Exercises scripts.run_pipeline.run_pipeline — the same entry point as
``python scripts/run_pipeline.py`` — against a temp DB, then verifies the
results through the REST API the dashboard consumes.

The full-portfolio test reuses the on-disk demo CSVs (one ~45s pipeline
pass, module-scoped); everything else is a fast 6-CSE hermetic run.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app

DEMO_DIR = Path("data/samples/demo_dataset")
SEEDED = {"CSE-042", "CSE-017", "CSE-089", "CSE-031",
          "CSE-055", "CSE-073", "CSE-019", "CSE-061"}


def _run(tmp_path: Path, n_cses: int = 6):
    from scripts.run_pipeline import run_pipeline

    db = tmp_path / f"pipe{n_cses}.db"
    dataset = tmp_path / f"data{n_cses}"
    return run_pipeline(db, dataset, seed=42, n_cses=n_cses), db


# ---------------------------------------------------------------------------
# Fast hermetic end-to-end (small portfolio)
# ---------------------------------------------------------------------------


class TestPipelineSmall:
    @pytest.fixture(scope="class")
    def small(self, tmp_path_factory):
        return _run(tmp_path_factory.mktemp("small"))[0]

    def test_runs_and_produces_all_layers(self, small):
        s = small
        assert s["records"] > 0
        assert s["profiles"] == 6 * 5          # x5 periods
        # CSE-001..006 are healthy baselines -> zero findings is the correct
        # result here; the engine must not invent concerns on clean data.
        assert s["findings"] == 0
        assert s["flagged_cses"] == 0
        assert s["scores_stored"] == 6         # every CSE ranked anyway
        assert 0.0 <= s["quality"] <= 1.0

    def test_checks_only_cover_present_cses(self, small):
        strict = [c for c in small["checks"] if "expected" in c]
        top10 = next(c for c in small["checks"]
                     if c.get("check") == "seeded_cses_in_top10")
        # 6-CSE subset is CSE-001..006 — no seeded CSEs apply.
        assert strict == []
        assert top10["applicable"] == 0 and top10["ok"]

    def test_results_are_stored_in_sqlite(self, tmp_path):
        from sqlalchemy import create_engine, text

        summary, db = _run(tmp_path)
        with create_engine(f"sqlite:///{db}").connect() as conn:
            stored = {t: conn.execute(
                text(f"SELECT COUNT(*) FROM {t}")).scalar()
                for t in ("findings", "behavioral_profiles",
                          "attention_scores")}
        # Clean baselines -> empty findings table is correct; profiles and
        # scores must still be fully persisted.
        assert stored["findings"] == summary["findings"] == 0
        assert stored["behavioral_profiles"] == summary["profiles"]
        assert stored["attention_scores"] == summary["scores_stored"]


class TestIdempotency:
    def test_second_run_does_not_duplicate(self, tmp_path):
        from sqlalchemy import create_engine, text

        first, db = _run(tmp_path)
        second, _ = _run(tmp_path)           # dataset dir now populated
        for key in ("findings", "profiles", "scores_stored",
                    "benchmark_rows"):
            assert second[key] == first[key], key

        with create_engine(f"sqlite:///{db}").connect() as conn:
            counts = {t: conn.execute(
                text(f"SELECT COUNT(*) FROM {t}")).scalar()
                for t in ("findings", "attention_scores")}
        assert counts["findings"] == first["findings"]
        assert counts["attention_scores"] == first["scores_stored"]


# ---------------------------------------------------------------------------
# Full portfolio: demo dataset -> pipeline -> API/dashboard contract
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def full(tmp_path_factory):
    from scripts.run_pipeline import run_pipeline

    db = tmp_path_factory.mktemp("full") / "sat_sa.db"
    summary = run_pipeline(db, DEMO_DIR, seed=42)
    return summary, db


class TestFullPortfolio:
    def test_all_eight_seeded_weaknesses_detected(self, full):
        summary, _ = full
        strict = [c for c in summary["checks"] if "expected" in c]
        assert len(strict) == 8
        failed = [c for c in strict if not c["ok"]]
        assert not failed, f"undetected seeds: {failed}"

    def test_seeded_cses_rank_in_top_ten(self, full):
        summary, _ = full
        check = next(c for c in summary["checks"]
                     if c.get("check") == "seeded_cses_in_top10")
        assert check["applicable"] == 8
        assert set(check["found"]) == SEEDED

    def test_summary_counts(self, full):
        summary, _ = full
        assert summary["profiles"] == 250
        assert summary["scores_stored"] == 50
        assert summary["benchmark_rows"] > 0

    def test_fusion_cases_match_the_gate_rule(self, full):
        """Cases form exactly for CSEs with 2+ findings across 2+ categories.

        On the seeded portfolio that is the four multi-signal seeded CSEs;
        clean CSEs carry one finding each and must stay case-free.
        """
        summary, db = full
        from collections import defaultdict

        from src.analytics.fusion import load_cases

        from src.evidence.findings import load_findings_as_objects

        by_cse = defaultdict(list)
        for f in load_findings_as_objects(db):
            by_cse[f.cse_id].append(f)
        expected = {c for c, fs in by_cse.items()
                    if len(fs) >= 2
                    and len({x.signal_category for x in fs}) >= 2}
        rows = load_cases(db)
        assert {r["cse_id"] for r in rows} == expected
        assert summary["supervisory_cases"] == len(rows)
        # the flagship case: every member linked, joint confidence saturated
        case = next(r for r in rows if r["cse_id"] == "CSE-042")
        assert case["case_id"] == "CASE-CSE-042"
        assert case["n_findings"] == 8
        assert len(case["finding_ids"]) == 8
        assert len(case["categories"]) >= 2
        assert case["joint_confidence"] == pytest.approx(1.0)


class TestApiServesPipelineResults:
    """The dashboard renders exclusively from these endpoints."""

    def test_rankings_endpoint_lists_full_portfolio(self, full):
        summary, db = full
        client = TestClient(create_app(db))
        body = client.get("/api/portfolio/rankings")
        assert body.status_code == 200
        rows = body.json()["data"]
        assert len(rows) == 50                     # all CSEs incl. quiet
        assert all(r["priority"] >= rows[-1]["priority"] for r in rows)
        top_ids = {r["cse_id"] for r in rows[:10]}
        assert SEEDED <= top_ids
        # context columns the dashboard table needs
        seeded_row = next(r for r in rows if r["cse_id"] == "CSE-042")
        assert seeded_row["sector"] and seeded_row["size_band"]
        # top_signal must be CSE-042's highest severity/confidence finding
        # per the findings endpoint (cross-endpoint consistency).
        mine = client.get("/api/findings",
                          params={"cse_id": "CSE-042"}).json()["data"]
        rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        best = max(mine, key=lambda f: (rank[f["severity"]],
                                        f["confidence"]))
        assert seeded_row["top_signal"] == best["signal_type"]
        assert seeded_row["top_signal_severity"] == best["severity"]

    def test_dashboard_pages_render_over_pipeline_db(self, full):
        _, db = full
        client = TestClient(create_app(db))
        page = client.get("/dashboard/")
        assert page.status_code == 200
        entity = client.get("/dashboard/entity/CSE-042")
        assert entity.status_code == 200

    def test_seeded_finding_has_evidence_chain_via_api(self, full):
        _, db = full
        client = TestClient(create_app(db))
        # missing_investigations is record-level: 25 contributing alert IDs.
        data = client.get(
            "/api/findings/CSE-031:missing_investigations/explain"
        ).json()["data"]
        assert data["chain"]["depth"] >= 3
        assert len(data["chain"]["records"]) == 25
        assert data["narrative"] is None           # LLM off by default

    def test_metric_level_finding_reports_no_records(self, full):
        """superficial_closure is metric-level: chain has metrics, no rows."""
        _, db = full
        client = TestClient(create_app(db))
        data = client.get(
            "/api/findings/CSE-017:superficial_closure/explain").json()["data"]
        assert data["finding"]["contributing_record_ids"] == []
        assert data["chain"] is not None
        assert data["chain"]["metrics"], "metric-level finding lost metrics"

    def test_quantitative_signals_show_numbers_in_their_chains(self, full):
        """changepoint_drift / kpi_divergence keys must be tracer-registered,
        else the finding page renders no metric steps (chain depth < 3)."""
        _, db = full
        client = TestClient(create_app(db))
        cp = client.get(
            "/api/findings/CSE-042:changepoint_drift/explain").json()["data"]
        assert cp["chain"]["depth"] >= 3
        names = {m["metric_name"] for m in cp["chain"]["metrics"]}
        assert {"mean_before", "mean_after", "drop",
                "explained_share"} <= names
        assert cp["chain"]["metrics"][0]["calculation"]
        kpi = client.get(
            "/api/findings/CSE-042:kpi_divergence/explain").json()["data"]
        assert kpi["chain"]["depth"] >= 3
        knames = {m["metric_name"] for m in kpi["chain"]["metrics"]}
        assert {"depth_slope_per_quarter",
                "velocity_slope_per_quarter"} <= knames

    def test_evidence_deficit_fires_only_on_seeded_thin_cses(self, full):
        """The expected-evidence model must separate cleanly: the four
        seeded thin CSEs fire, no clean CSE does."""
        _, db = full
        from src.evidence.findings import load_findings_as_objects

        fired = {f.cse_id for f in load_findings_as_objects(db)
                 if f.signal_type == "evidence_deficit"}
        assert fired == {"CSE-017", "CSE-031", "CSE-042", "CSE-061"}
        assert fired <= SEEDED                    # zero clean firings

    def test_evidence_deficit_chain_carries_the_model(self, full):
        _, db = full
        client = TestClient(create_app(db))
        data = client.get(
            "/api/findings/CSE-042:evidence_deficit/explain").json()["data"]
        assert data["chain"]["depth"] >= 3
        names = {m["metric_name"] for m in data["chain"]["metrics"]}
        assert {"headline_observed", "headline_expected", "headline_ratio",
                "min_ratio_applied"} <= names
        ev = data["finding"]["evidence"]
        assert ev["headline_dimension"] == "evidence_entries"
        assert ev["headline_ratio"] < 0.9         # genuinely thin
        assert ev["headline_band_low"] > ev["headline_observed"]

    def test_evidence_model_endpoint_contract(self, full):
        _, db = full
        client = TestClient(create_app(db))
        body = client.get("/api/evidence-model/CSE-042")
        assert body.status_code == 200
        payload = body.json()["data"]
        assert set(payload["dimensions"]) == {
            "alerts", "investigations", "evidence_entries", "escalations"}
        entries = payload["dimensions"]["evidence_entries"]
        assert entries["ratio"] < 1.0
        assert entries["band_low"] <= entries["expected"] <= entries["band_high"]
        assert "leave-self-out" in body.json()["meta"]["note"]
        # a clean CSE models as healthy on every dimension
        clean = client.get("/api/evidence-model/CSE-001").json()["data"]
        assert all(d["ratio"] > 0.9 or d["ratio"] is None
                   for d in clean["dimensions"].values())
        assert client.get("/api/evidence-model/CSE-NOWHERE").status_code == 404

    def test_every_finding_has_a_deep_evidence_chain(self, full):
        """Systemic guard: no signal may emit only unregistered evidence keys
        (the finding page would render an empty metric panel)."""
        _, db = full
        from src.evidence.findings import load_findings_as_objects
        from src.evidence.tracer import EvidenceTracer

        tracer = EvidenceTracer(db)
        shallow = []
        for f in load_findings_as_objects(db):
            chain = tracer.trace(f.finding_id)
            if chain is None or chain.depth < 3 or not chain.metrics:
                shallow.append(f.finding_id)
        assert not shallow, f"findings without metric steps: {shallow}"

    def test_cases_api_contract(self, full):
        _, db = full
        client = TestClient(create_app(db))
        body = client.get("/api/cases")
        assert body.status_code == 200
        rows = body.json()["data"]
        assert {r["case_id"] for r in rows} == {
            "CASE-CSE-017", "CASE-CSE-031", "CASE-CSE-042", "CASE-CSE-061"}
        detail = client.get("/api/cases/CASE-CSE-042")
        assert detail.status_code == 200
        payload = detail.json()["data"]
        assert payload["case"]["n_findings"] == 8
        assert len(payload["member_findings"]) == 8
        assert all("evidence" not in m for m in payload["member_findings"])
        # unknown case -> structured 404
        assert client.get("/api/cases/CASE-NOWHERE").status_code == 404
        # cse filter narrows to that CSE's case only
        filtered = client.get("/api/cases", params={"cse_id": "CSE-017"})
        assert [r["case_id"] for r in filtered.json()["data"]] == \
            ["CASE-CSE-017"]
