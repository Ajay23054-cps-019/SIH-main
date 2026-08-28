"""Integration tests for the FastAPI backend (Phase 10).

A 6-CSE synthetic portfolio is stored to a temp SQLite DB and served
through ``create_app(db_path)``; every endpoint is exercised over HTTP.
"""
from __future__ import annotations

import io
import time
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_db(db_path: Path, n_cses: int = 6) -> None:
    from src.analytics.profiler import compute_all_profiles, store_profiles
    from src.analytics.sample_data import generate_dataset
    from src.analytics.signal_engine import run_signals
    from src.storage.db import save_frames

    frames = generate_dataset(seed=42, n_cses=n_cses)
    save_frames(frames, db_path)
    store_profiles(compute_all_profiles(frames), db_path)
    run_signals(db_path)


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("api") / "sat_sa.db"
    _build_db(db_path)
    # Seed one deterministic HIGH finding so detail/explain/filter tests
    # don't depend on what the (all-baseline) 6-CSE subset happens to fire.
    from src.analytics.finding import Finding, STANDARD_CAVEAT
    from src.analytics.signal_engine import store_findings

    probe = Finding(
        finding_id="CSE-001:probe_high", cse_id="CSE-001",
        signal_type="probe_high", signal_category="execution_gap",
        period="ALL", severity="HIGH", confidence=0.95,
        evidence={"probe": True},
        contributing_record_ids=["AL-GHOST-1"],
        detection_logic="seeded for API tests",
        caveats=[STANDARD_CAVEAT],
    )
    store_findings([probe], db_path)
    client = TestClient(create_app(db_path))
    client.db_path = db_path
    return client


def _envelope_ok(payload):
    assert set(payload) >= {"data", "meta", "errors"}
    assert payload["errors"] == []
    assert payload["meta"]["generated_at"]


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


class TestSystem:
    def test_health_envelope(self, api):
        resp = api.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        _envelope_ok(body)
        assert body["data"]["status"] == "ok"
        assert body["data"]["table_counts"]["alerts"] > 0

    def test_openapi_docs_served(self, api):
        assert api.get("/docs").status_code == 200
        spec = api.get("/openapi.json").json()
        for path in ("/api/findings", "/api/portfolio/rankings",
                     "/api/peers/{cse_id}", "/api/analytics/run"):
            assert path in spec["paths"], f"{path} missing from OpenAPI"

    def test_unknown_route_is_structured_404(self, api):
        resp = api.get("/api/nope")
        assert resp.status_code == 404
        body = resp.json()
        assert body["data"] is None
        assert body["errors"][0]["code"] == "http_error"

    def test_validation_error_is_structured(self, api):
        resp = api.get("/api/profiles/compare")   # missing cse_ids
        assert resp.status_code == 422
        assert resp.json()["errors"][0]["code"] == "validation_error"


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


class TestIngestion:
    def _mini_api(self, tmp_path):
        from src.storage.db import save_frames

        db_path = tmp_path / "ingest.db"
        meta = pd.DataFrame([{"cse_id": "CSE-U1", "sector": "Telecom",
                              "size_band": "Large"}])
        save_frames({"cse_metadata": meta}, db_path)
        return TestClient(create_app(db_path))

    def test_upload_append_and_status_and_quality(self, tmp_path):
        api = self._mini_api(tmp_path)
        csv = ("alert_id,cse_id,timestamp,severity,category,asset_id,status,"
               "closure_timestamp,description\n"
               "AL-1,CSE-U1,2024-01-01T08:00:00,HIGH,malware,A-1,closed,,x\n"
               "AL-2,CSE-U1,2024-01-01T09:00:00,LOW,network,A-2,open,,y\n")
        resp = api.post("/api/ingest/upload",
                        files={"file": ("alerts.csv",
                                        io.BytesIO(csv.encode()))})
        assert resp.status_code == 200
        assert resp.json()["data"]["rows_written"] == 2

        status = api.get("/api/ingest/status/CSE-U1").json()["data"]
        assert status["counts"]["alerts"] == 2

        quality = api.get("/api/ingest/quality/CSE-U1").json()["data"]
        score = quality["quality"]["overall_score"]
        assert 0.0 <= score <= 1.0
        # AL-1 is closed without closure_timestamp -> must be warned about
        assert any("closure" in w for w in quality["quality"]["warnings"])

    def test_upload_rejects_unknown_entity(self, api):
        resp = api.post("/api/ingest/upload",
                        files={"file": ("stuff.csv", io.BytesIO(b"a,b\n1,2"))})
        assert resp.status_code == 422
        assert resp.json()["errors"][0]["code"] == "unknown_entity"

    def test_upload_rejects_unreadable_csv(self, api):
        resp = api.post("/api/ingest/upload",
                        files={"file": ("alerts.csv", io.BytesIO(b"\xff\xfe"))})
        assert resp.status_code == 422
        assert resp.json()["errors"][0]["code"] == "bad_csv"

    def test_upload_logs_derives_alerts(self, tmp_path):
        db_path = tmp_path / "ingest.db"
        api = self._mini_api(tmp_path)
        log_text = (
            "2024-06-01T10:00:00.123Z host-5 malware: ransomware payload observed\n"
            "2024-06-01 10:05:00 [WARN] host-3 auth: failed password for root\n"
            "2024-06-01 11:00:00 CRITICAL host-2 network: lateral movement detected\n"
        )
        resp = api.post("/api/ingest/upload",
                        files={"file": ("logs.txt",
                                        io.BytesIO(log_text.encode()))},
                        data={"cse_id": "CSE-LOGX"})
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["entity"] == "logs"
        assert body["rows_written"] == 3
        assert body["rows_rejected"] == 0

        from src.storage.db import load_table
        alerts = load_table("alerts", db_path, cse_id="CSE-LOGX")
        assert len(alerts) == 3
        sev = set(alerts["severity"])
        assert "CRITICAL" in sev
        # category + asset_id derived from log content
        assert "malware" in set(alerts["category"])
        assert "host-5" in set(alerts["asset_id"])
        # recommended solution captured in the description
        assert any("RECOMMENDED" in d for d in alerts["description"].tolist())
        # cse_metadata auto-created so the CSE shows in portfolio
        meta = load_table("cse_metadata", db_path, cse_id="CSE-LOGX")
        assert len(meta) == 1
        assert meta.iloc[0]["size_band"] == "Medium"

    def test_upload_json_with_entity_param(self, tmp_path):
        import json

        api = self._mini_api(tmp_path)
        payload = json.dumps([
            {"alert_id": "J-1", "cse_id": "J-CSE",
             "timestamp": "2024-01-01T10:00:00", "severity": "HIGH",
             "category": "malware", "asset_id": "A1", "status": "closed"},
        ])
        # Non-standard filename: entity supplied explicitly.
        resp = api.post("/api/ingest/upload",
                        files={"file": ("weird_name.json",
                                        io.BytesIO(payload.encode()))},
                        data={"entity": "alerts", "cse_id": "J-CSE"})
        assert resp.status_code == 200
        assert resp.json()["data"]["rows_written"] == 1

    def test_status_unknown_cse_404(self, api):
        resp = api.get("/api/ingest/status/CSE-GHOST")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


class TestProfiles:
    def test_detail_lists_all_periods(self, api):
        data = api.get("/api/profiles/CSE-001").json()["data"]
        periods = {p["period"] for p in data}
        assert "ALL" in periods and any(p.startswith("2024-Q") for p in periods)

    def test_period_filter(self, api):
        data = api.get("/api/profiles/CSE-001",
                       params={"period": "ALL"}).json()["data"]
        assert len(data) == 1 and data[0]["period"] == "ALL"
        assert data[0]["metrics"]

    def test_trends_with_alias(self, api):
        data = api.get("/api/profiles/CSE-001/trends",
                       params={"metric": "investigation_depth"}).json()["data"]
        assert data["metric"] == "inv_depth_mean"
        values = [s["value"] for s in data["series"]]
        assert values and all(v is not None for v in values)

    def test_compare_reports_missing(self, api):
        body = api.get("/api/profiles/compare",
                       params={"cse_ids": "CSE-001,CSE-NOPE",
                               "period": "ALL"}).json()
        ids = {p["cse_id"] for p in body["data"]}
        assert "CSE-001" in ids
        assert body["meta"]["missing_cse_ids"] == ["CSE-NOPE"]

    def test_unknown_profile_404(self, api):
        assert api.get("/api/profiles/CSE-GHOST").status_code == 404


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


class TestFindings:
    def test_list_filters_by_severity_sorted(self, api):
        data = api.get("/api/findings",
                       params={"severity": "HIGH"}).json()["data"]
        assert any(f["finding_id"] == "CSE-001:probe_high" for f in data)
        assert all(f["severity"] == "HIGH" for f in data)
        # sorted: HIGH findings first, confidence-descending within tier
        rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        full = api.get("/api/findings").json()["data"]
        tiers = [rank[f["severity"]] for f in full]
        assert tiers == sorted(tiers, reverse=True)

    def test_category_slug_endpoints(self, api):
        for slug in ("execution-gaps",):
            body = api.get(f"/api/findings/{slug}").json()
            assert body["meta"]["category"] == "execution_gap"
            assert all(f["signal_category"] == "execution_gap"
                       for f in body["data"])
            assert any(f["finding_id"] == "CSE-001:probe_high"
                       for f in body["data"])

    def test_unknown_slug_lists_valid_ones(self, api):
        resp = api.get("/api/findings/not-a-slug")
        assert resp.status_code == 404
        assert "execution-gaps" in resp.json()["errors"][0]["detail"]

    def test_detail_carries_evidence_and_chain(self, api):
        data = api.get("/api/findings/CSE-001:probe_high").json()["data"]
        assert data["finding"]["evidence"] == {"probe": True}
        assert data["chain"]["depth"] >= 3

    def test_explain_chain_and_narrative_gate(self, api):
        data = api.get(
            "/api/findings/CSE-001:probe_high/explain").json()["data"]
        assert data["chain"]["depth"] >= 3
        # the probe references a record that does not exist -> flagged
        assert any(m["record_id"] == "AL-GHOST-1"
                   for m in data["chain"]["missing_records"])
        # LLM disabled by default -> narrative explicitly null, never fake
        assert data["narrative"] is None

    def test_unknown_finding_404(self, api):
        assert api.get("/api/findings/NOPE:sig").status_code == 404


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


class TestPortfolio:
    def test_rankings_shape_and_order(self, api):
        body = api.get("/api/portfolio/rankings")
        assert body.status_code == 200
        data = body.json()["data"]
        assert len(data) == 6
        priorities = [d["priority"] for d in data]
        assert priorities == sorted(priorities, reverse=True)
        assert all("explanation" in d for d in data)
        assert "NOT a risk or compliance score"
        assert "risk" in body.json()["meta"]["disclaimer"].lower()

    def test_summary_counts_consistent(self, api):
        data = api.get("/api/portfolio/summary").json()["data"]
        listed = api.get("/api/findings").json()["meta"]["count"]
        assert data["n_findings"] == listed
        assert sum(data["findings_by_severity"].values()) == listed
        assert len(data["top5"]) <= 5


# ---------------------------------------------------------------------------
# Peers
# ---------------------------------------------------------------------------


class TestPeers:
    def test_peer_benchmark_context(self, api):
        data = api.get("/api/peers/CSE-001").json()["data"]
        assert data["group_label"]
        assert data["cse_id"] in data["group_definition"]
        assert len(data["peer_ids"]) >= 1
        if data["benchmarks"]:
            sample = data["benchmarks"][0]
            for key in ("metric", "value", "peer_mean", "z_score",
                        "percentile", "is_outlier"):
                assert key in sample

    def test_compare_two_cses(self, api):
        data = api.get("/api/peers/compare",
                       params={"cse_ids": "CSE-001,CSE-002"}).json()["data"]
        assert [b["cse_id"] for b in data] == ["CSE-001", "CSE-002"]

    def test_unknown_cse_peers_404(self, api):
        assert api.get("/api/peers/CSE-GHOST").status_code == 404


# ---------------------------------------------------------------------------
# On-demand analytics jobs
# ---------------------------------------------------------------------------


class TestAnalyticsJobs:
    def test_full_run_job_lifecycle(self, tmp_path):
        from src.analytics.sample_data import generate_dataset
        from src.storage.db import save_frames

        db_path = tmp_path / "jobs.db"
        save_frames(generate_dataset(seed=42, n_cses=4), db_path)
        api = TestClient(create_app(db_path))

        started = api.post("/api/analytics/run", json={})
        assert started.status_code == 200
        job_id = started.json()["data"]["job_id"]

        deadline = time.time() + 180
        while time.time() < deadline:
            job = api.get(f"/api/analytics/status/{job_id}").json()["data"]
            if job["state"] in ("done", "failed"):
                break
            time.sleep(0.5)
        assert job["state"] == "done", job.get("error")
        assert "signals" in job["steps"]
        assert job["result"]["findings"] > 0
        # 4 CSEs land in cells below the min peer group, so zero benchmark
        # rows is the *correct* outcome here — the key must exist regardless.
        assert "benchmark_rows" in job["result"]
        assert job["result"]["scores_stored"] > 0

    def test_unknown_job_404(self, api):
        assert api.get("/api/analytics/status/nope").status_code == 404


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


class TestCors:
    def test_preflight_allows_local_origin(self, api):
        resp = api.options(
            "/health",
            headers={"Origin": "http://localhost:5173",
                     "Access-Control-Request-Method": "GET"})
        assert resp.status_code in (200, 204)
        assert resp.headers.get("access-control-allow-origin") == "*"
