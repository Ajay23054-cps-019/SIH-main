"""Optional browser-level smoke tests for the dashboard.

These catch what shell/API tests cannot: client-side fetch rendering
(app.js populating the DOM). They run only when a Chrome/Chromium binary
is available and skip silently otherwise, so CI and air-gapped machines
are unaffected.

    pytest tests/test_dashboard_browser.py -v
"""
from __future__ import annotations

import shutil
import subprocess
import urllib.parse
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not shutil.which("google-chrome") and not shutil.which("chromium"),
    reason="no headless Chrome/Chromium binary on PATH")

CHROME = shutil.which("google-chrome") or shutil.which("chromium")


def _render(url: str, wait_ms: int = 8000) -> str:
    """Return the JS-executed DOM for ``url`` (virtual time budget = wait)."""
    result = subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
         "--virtual-time-budget=" + str(wait_ms), "--dump-dom", url],
        capture_output=True, text=True, timeout=90, check=True)
    return result.stdout


@pytest.fixture(scope="module")
def live_server(tmp_path_factory):
    """Real uvicorn process; headless Chrome cannot reach TestClient."""
    import os
    import socket
    import time

    from src.analytics.profiler import compute_all_profiles, store_profiles
    from src.analytics.sample_data import generate_dataset
    from src.analytics.signal_engine import run_signals
    from src.storage.db import save_frames

    db_path = tmp_path_factory.mktemp("browser") / "sat_sa.db"
    frames = generate_dataset(seed=42, n_cses=8)
    save_frames(frames, db_path)
    store_profiles(compute_all_profiles(frames), db_path)
    run_signals(db_path)

    # Deterministic record-level finding so the finding-page render test
    # doesn't depend on what the all-baseline subset happens to fire.
    from src.analytics.finding import Finding, STANDARD_CAVEAT
    from src.analytics.signal_engine import store_findings

    store_findings([Finding(
        finding_id="CSE-001:probe_high", cse_id="CSE-001",
        signal_type="probe_high", signal_category="execution_gap",
        period="ALL", severity="HIGH", confidence=0.95,
        evidence={"probe": True},
        contributing_record_ids=["AL-GHOST-1"],
        detection_logic="seeded for browser tests",
        caveats=[STANDARD_CAVEAT],
    )], db_path)

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = dict(os.environ, SAT_SA_DB=str(db_path))
    proc = subprocess.Popen(
        ["./venv/bin/uvicorn", "src.api.main:app", "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            import urllib.request

            urllib.request.urlopen(base + "/health", timeout=1)
            break
        except Exception:
            time.sleep(0.3)
    yield base
    proc.terminate()
    proc.wait(timeout=10)


class TestClientSideRendering:
    def test_portfolio_table_populated_by_js(self, live_server):
        dom = _render(live_server + "/dashboard/")
        assert dom.count("data-cse=") >= 8, "rankings rows did not render"
        assert "Loading" not in dom.split("rankings-body")[1][:200]

    def test_summary_cards_show_numbers(self, live_server):
        dom = _render(live_server + "/dashboard/")
        for anchor in ("total-cses", "high-priority", "critical-signals"):
            segment = dom.split(f'id="{anchor}"')[1][:40]
            value = segment.split(">")[1].split("<")[0]
            assert value not in ("–", "", "!"), f"{anchor}={value!r}"

    def test_entity_profile_cards_populated(self, live_server):
        dom = _render(live_server + "/dashboard/entity/CSE-001")
        segment = dom.split('id="m-inv_depth_mean"')[1][:40]
        value = segment.split(">")[1].split("<")[0]
        assert value not in ("–", "!", ""), "profile metrics did not render"

    def test_finding_evidence_table_populated(self, live_server):
        dom = _render(live_server + "/dashboard/finding/" +
                      urllib.parse.quote("CSE-001:probe_high"))
        assert "Loading" not in dom.split('id="rationale"')[1][:300]
        # the probe references a nonexistent record -> must surface as missing
        assert "AL-GHOST-1" in dom.split("missing-records")[1][:400]
