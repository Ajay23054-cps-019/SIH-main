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
