"""Dashboard integration tests (Phase 11).

The pages are thin Jinja2 shells — the tests verify they render, reference
only locally-served assets (offline acceptance criterion), and that the
static bundle + enriched rankings endpoint behave over HTTP.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app

CDN_MARKERS = ("http://", "https://", "//cdn.", "unpkg.com",
               "jsdelivr", "googleapis")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from src.analytics.profiler import compute_all_profiles, store_profiles
    from src.analytics.sample_data import generate_dataset
    from src.analytics.signal_engine import run_signals
    from src.storage.db import save_frames

    db_path = tmp_path_factory.mktemp("dash") / "sat_sa.db"
    frames = generate_dataset(seed=42, n_cses=8)
    save_frames(frames, db_path)
    store_profiles(compute_all_profiles(frames), db_path)
    run_signals(db_path)
    return TestClient(create_app(db_path))


class TestPages:
    def test_portfolio_page_renders_shell(self, client):
        resp = client.get("/dashboard/")
        assert resp.status_code == 200
        html = resp.text
        assert "SAT-SA Portfolio Overview" in html
        for anchor in ("total-cses", "high-priority", "critical-signals"):
            assert f'id="{anchor}"' in html
        assert 'id="rankings-table"' in html
        assert 'id="rankings-body"' in html
        for column in ("Rank", "CSE ID", "Sector",
                       "Attention Priority", "Findings", "Top Signal"):
            assert f"<th>{column}</th>" in html

    def test_entity_page_renders_shell(self, client):
        resp = client.get("/dashboard/entity/CSE-001")
        assert resp.status_code == 200
        assert "CSE-001" in resp.text
        for key in ("m-alert_volume_total", "m-inv_depth_mean",
                    "m-closure_velocity_median_h", "m-esc_rate"):
            assert f'id="{key}"' in resp.text
        # fused-case banner slot exists (hidden until a case is fetched)
        assert 'id="case-banner"' in resp.text
        assert "/api/cases" in client.get(
            "/dashboard/static/js/app.js").text
        assert ".case-banner" in client.get(
            "/dashboard/static/css/style.css").text

    def test_finding_page_keeps_colon_in_id(self, client):
        fid = "CSE-001:some_signal"
        resp = client.get(f"/dashboard/finding/{fid}")
        assert resp.status_code == 200
        assert fid in resp.text          # :path converter preserved it
        # examiner feedback loop UI is part of the shell
        assert 'id="feedback-panel"' in resp.text
        for disposition in ("worthwhile", "not_worthwhile", "uncertain"):
            assert f'data-disposition="{disposition}"' in resp.text
        js = client.get("/dashboard/static/js/app.js").text
        assert "/feedback" in js
        assert ".fb-btn" in client.get(
            "/dashboard/static/css/style.css").text


class TestOfflineAssets:
    def test_no_cdn_references_anywhere(self, client):
        for page in ("/dashboard/", "/dashboard/entity/CSE-001",
                     "/dashboard/finding/CSE-001:x"):
            html = client.get(page).text.lower()
            for marker in CDN_MARKERS:
                assert marker not in html, \
                    f"{marker} found in {page} — breaks offline criterion"

    def test_static_assets_served(self, client):
        css = client.get("/dashboard/static/css/style.css")
        js = client.get("/dashboard/static/js/app.js")
        chart = client.get("/dashboard/static/js/lib/chart.umd.min.js")
        assert css.status_code == 200 and ".badge.high" in css.text
        assert js.status_code == 200 and "fetchJSON" in js.text
        assert chart.status_code == 200
        assert len(chart.content) > 100_000      # real Chart.js bundle

    def test_pages_reference_only_local_assets(self, client):
        html = client.get("/dashboard/").text
        assert "/dashboard/static/css/style.css" in html
        assert "/dashboard/static/js/lib/chart.umd.min.js" in html
        assert "/dashboard/static/js/app.js" in html


class TestRankingsForTable:
    """The portfolio table's Sector / Top Signal columns are server truth."""

    def test_every_row_carries_context(self, client):
        data = client.get("/api/portfolio/rankings").json()["data"]
        assert len(data) == 8                 # all CSEs listed, incl. quiet
        priorities = [d["priority"] for d in data]
        assert priorities == sorted(priorities, reverse=True)
        for row in data:
            assert {"sector", "size_band", "top_signal"} <= set(row)
            if row["n_findings"]:
                assert row["top_signal"]
                assert row["sector"]

    def test_top_signal_is_real_finding_of_that_cse(self, client):
        findings = client.get("/api/findings").json()["data"]
        by_cse = {}
        rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        for f in findings:
            cur = by_cse.get(f["cse_id"])
            key = (rank[f["severity"]], f["confidence"])
            if cur is None or key > (rank[cur["severity"]],
                                     cur["confidence"]):
                by_cse[f["cse_id"]] = f
        rows = {d["cse_id"]: d for d in
                client.get("/api/portfolio/rankings").json()["data"]}
        for cse_id, expected in by_cse.items():
            assert rows[cse_id]["top_signal"] == expected["signal_type"]
            assert rows[cse_id]["top_signal_severity"] == \
                expected["severity"]
