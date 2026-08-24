"""Tests for the supervisory signal engine.

Unit tests drive individual signals through handcrafted SignalContexts so
threshold logic is pinned exactly. Integration tests run the full 18-signal
engine over the demo dataset and assert every seeded weakness is detected —
plus that no *clean* CSE earns a HIGH-severity finding.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.analytics import behavioral_anomalies as ba
from src.analytics import execution_gaps as eg
from src.analytics import negative_space as ns
from src.analytics import peer_deviation as pd_dev
from src.analytics.finding import (
    DEFAULT_THRESHOLDS,
    STANDARD_CAVEAT,
    load_thresholds,
    margin_above,
    margin_below,
)
from src.analytics.profiles import BehavioralProfile, PERIOD_ALL
from src.analytics.signal_common import SignalContext
from src.analytics.signal_engine import (
    SIGNAL_REGISTRY,
    build_contexts,
    clear_findings,
    load_findings,
    run_context,
    store_findings,
)

DEMO_DIR = Path("data/samples/demo_dataset")
ENTITY_TYPES = ("cse_metadata", "alerts", "investigations",
                "escalations", "cases", "assets")

# Canonical expectations live next to the generator (single source of truth
# shared with scripts/run_pipeline.py).
from src.analytics.sample_data import expected_seed_signals  # noqa: E402

EXPECTED_SEED_SIGNALS = expected_seed_signals()
SEEDED = set(EXPECTED_SEED_SIGNALS)


# ---------------------------------------------------------------------------
# Context builders
# ---------------------------------------------------------------------------


def _profile(cse_id="CSE-T01", period="2024-Q4", **metrics):
    return BehavioralProfile(
        cse_id=cse_id, period=period, metrics=metrics,
        warnings=["synthetic warning"] if metrics.get("_warn") else [],
        n_alerts=int(metrics.get("alert_volume_total", 0)),
    )


def _empty_frames():
    return {name: pd.DataFrame() for name in ENTITY_TYPES}


def _ctx(cse_id="CSE-T01", profiles=None, cse_frames=None, frames=None,
         peer_stats=None, quality_score=1.0, thresholds=None):
    return SignalContext(
        cse_id=cse_id,
        profiles=profiles or [],
        cse_frames=cse_frames if cse_frames is not None else _empty_frames(),
        frames=frames if frames is not None else _empty_frames(),
        peer_stats=peer_stats or {},
        quality_score=quality_score,
        thresholds=thresholds or load_thresholds(),
    )


def _alert_rows(rows, cse_id="CSE-T01"):
    base = {"alert_id": None, "cse_id": cse_id, "timestamp": None,
            "severity": "HIGH", "category": "malware", "asset_id": "A-1",
            "status": "closed", "closure_timestamp": None, "description": None}
    return pd.DataFrame([{**base, **r} for r in rows])


def _inv_rows(rows, cse_id="CSE-T01"):
    base = {"investigation_id": None, "alert_id": None, "cse_id": cse_id,
            "timestamp_open": None, "timestamp_close": None,
            "evidence_entries": 0, "assigned_to": None, "notes": "note",
            "depth_score": None}
    return pd.DataFrame([{**base, **r} for r in rows])


def _esc_rows(rows, cse_id="CSE-T01"):
    base = {"escalation_id": None, "investigation_id": None, "cse_id": cse_id,
            "timestamp": None, "decision": "escalated", "has_followup": True,
            "recipient": "CSO", "rationale": None}
    return pd.DataFrame([{**base, **r} for r in rows])


def _asset_rows(rows, cse_id="CSE-T01"):
    base = {"asset_id": None, "cse_id": cse_id, "asset_type": "endpoint",
            "criticality": "HIGH", "environment": "production",
            "monitoring_status": "monitored"}
    return pd.DataFrame([{**base, **r} for r in rows])


def ts(day=15, month=1, hour=9, minute=0):
    return pd.Timestamp(f"2024-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:00")


# ---------------------------------------------------------------------------
# Configuration & helpers
# ---------------------------------------------------------------------------


class TestThresholdConfig:
    def test_defaults_load_without_file(self, tmp_path):
        cfg = load_thresholds(tmp_path / "missing.json")
        assert cfg["peer"]["outlier_z"] == DEFAULT_THRESHOLDS["peer"]["outlier_z"]

    def test_json_override_deep_merges(self, tmp_path):
        p = tmp_path / "thresholds.json"
        p.write_text(json.dumps({"peer": {"outlier_z": 9.9}}))
        cfg = load_thresholds(p)
        assert cfg["peer"]["outlier_z"] == 9.9
        assert cfg["peer"]["min_group_size"] == \
            DEFAULT_THRESHOLDS["peer"]["min_group_size"]


class TestMarginHelpers:
    def test_margin_above(self):
        assert margin_above(0.9, 0.7, 1.0) == pytest.approx(2 / 3)
        assert margin_above(1.2, 0.7, 1.0) == 1.0      # saturates
        assert margin_above(0.5, 0.7, 1.0) == 0.0      # not past threshold

    def test_margin_below(self):
        assert margin_below(0.6, 2.0, floor=0.25) == pytest.approx(0.8)
        assert margin_below(0.1, 2.0, floor=0.25) == 1.0
        assert margin_below(3.0, 2.0, floor=0.25) == 0.0


class TestFindingStructure:
    def test_standard_caveat_always_present(self):
        prof = _profile(alert_volume_total=100)
        ctx = _ctx(profiles=[prof])
        f = eg.detect_quality_degradation(ctx)
        assert f is None  # no data -> no finding

    def test_finding_id_deterministic(self):
        from src.analytics.finding import finding_id
        assert finding_id("CSE-1", "sig") == finding_id("CSE-1", "sig")
        assert finding_id("CSE-1", "sig") != finding_id("CSE-2", "sig")


# ---------------------------------------------------------------------------
# Execution-gap signals
# ---------------------------------------------------------------------------


class TestSuperficialClosure:
    def _frames(self, velocity_h, depth_entries):
        alerts = _alert_rows([
            {"alert_id": f"AL-{i}", "timestamp": ts(hour=8),
             "closure_timestamp": ts(hour=8 + max(velocity_h, 1))}
            for i in range(40)
        ])
        investigations = _inv_rows([
            {"investigation_id": f"INV-{i}", "alert_id": f"AL-{i}",
             "timestamp_open": ts(hour=9), "timestamp_close": ts(hour=10),
             "evidence_entries": depth_entries}
            for i in range(40)
        ])
        return {"alerts": alerts, "investigations": investigations}

    def test_fires_on_fast_and_shallow(self):
        prof = _profile(closure_velocity_median_h=0.5, inv_depth_median=1.0,
                        alert_volume_total=100)
        f = eg.detect_superficial_closure(_ctx(profiles=[prof]))
        assert f is not None and f.period == "2024-Q4"
        assert f.severity in ("HIGH", "MEDIUM")

    def test_healthy_quarter_stays_silent(self):
        prof = _profile(closure_velocity_median_h=150.0, inv_depth_median=5.0,
                        alert_volume_total=100)
        assert eg.detect_superficial_closure(_ctx(profiles=[prof])) is None

    def test_small_sample_stays_silent(self):
        prof = _profile(closure_velocity_median_h=0.5, inv_depth_median=1.0,
                        alert_volume_total=5)
        assert eg.detect_superficial_closure(_ctx(profiles=[prof])) is None


class TestQualityDegradation:
    def test_declining_series_fires_on_last_period(self):
        profiles = [
            _profile(period=p, inv_depth_mean=v)
            for p, v in [("2024-Q1", 5.0), ("2024-Q2", 4.5),
                         ("2024-Q3", 3.0), ("2024-Q4", 1.5)]
        ]
        f = eg.detect_quality_degradation(_ctx(profiles=profiles))
        assert f is not None
        assert f.period == "2024-Q4"
        assert f.evidence["decline_frac_first_to_last"] == pytest.approx(0.7)
        assert f.severity == "HIGH"

    def test_flat_series_silent(self):
        profiles = [_profile(period=f"2024-Q{i}", inv_depth_mean=5.0)
                    for i in range(1, 5)]
        assert eg.detect_quality_degradation(_ctx(profiles=profiles)) is None

    def test_too_few_quarters_silent(self):
        profiles = [_profile(period="2024-Q1", inv_depth_mean=5.0),
                    _profile(period="2024-Q2", inv_depth_mean=1.0)]
        assert eg.detect_quality_degradation(_ctx(profiles=profiles)) is None


class TestTemplateInvestigation:
    def test_templated_notes_fire(self):
        inv = _inv_rows([
            {"investigation_id": f"INV-{i}", "notes": "Routine check, no issue"}
            for i in range(50)
        ])
        f = eg.detect_template_investigation(_ctx(cse_frames={"investigations": inv}))
        assert f is not None
        assert f.evidence["n_unique_notes"] == 1
        assert f.confidence > 0.8
        assert len(f.contributing_record_ids) > 0

    def test_diverse_notes_silent(self):
        inv = _inv_rows([
            {"investigation_id": f"INV-{i}", "notes": f"Distinct narrative {i}"}
            for i in range(50)
        ])
        assert eg.detect_template_investigation(
            _ctx(cse_frames={"investigations": inv})) is None


# ---------------------------------------------------------------------------
# Negative-space signals
# ---------------------------------------------------------------------------


class TestMissingInvestigations:
    def test_mostly_uninvestigated_high_sev_fires(self):
        alerts = _alert_rows([
            {"alert_id": f"AL-{i}", "severity": "CRITICAL"} for i in range(30)
        ])
        inv = _inv_rows([
            {"investigation_id": "INV-1", "alert_id": "AL-0"}
        ])
        f = ns.detect_missing_investigations(
            _ctx(cse_frames={"alerts": alerts, "investigations": inv}))
        assert f is not None
        assert f.evidence["missing_rate"] == pytest.approx(29 / 30, abs=1e-2)
        assert len(f.contributing_record_ids) == 25  # capped

    def test_well_investigated_silent(self):
        alerts = _alert_rows([
            {"alert_id": f"AL-{i}", "severity": "HIGH"} for i in range(25)
        ])
        inv = _inv_rows([
            {"investigation_id": f"INV-{i}", "alert_id": f"AL-{i}"}
            for i in range(25)
        ])
        assert ns.detect_missing_investigations(
            _ctx(cse_frames={"alerts": alerts, "investigations": inv})) is None


class TestMissingCategories:
    def test_absent_category_shared_by_all_peers_fires(self):
        own = _alert_rows([{"alert_id": f"A-{i}", "category": "malware"}
                           for i in range(60)])
        portfolio = [
            own,
            _alert_rows([{"alert_id": f"B-{i}", "cse_id": "CSE-B",
                          "category": c} for i in range(10)
                         for c in ("malware", "network")]),
            _alert_rows([{"alert_id": f"C-{i}", "cse_id": "CSE-C",
                          "category": c} for i in range(10)
                         for c in ("malware", "network")]),
        ]
        frames = {"alerts": pd.concat(portfolio, ignore_index=True)}
        f = ns.detect_missing_alert_categories(
            _ctx(cse_frames={"alerts": own}, frames=frames))
        assert f is not None
        assert f.evidence["categories_expected_but_absent"] == ["network"]

    def test_all_categories_present_silent(self):
        own = _alert_rows([
            {"alert_id": f"T-{i}", "category": c}
            for i in range(30) for c in ("malware", "network")
        ])
        other = _alert_rows([
            {"alert_id": f"O-{i}", "cse_id": "CSE-O", "category": c}
            for i in range(5) for c in ("malware", "network")
        ], )
        alerts = pd.concat([own, other], ignore_index=True)
        ctx = _ctx(cse_frames={"alerts": alerts[alerts.cse_id == "CSE-T01"]},
                   frames={"alerts": alerts})
        assert ns.detect_missing_alert_categories(ctx) is None


class TestTelemetryAbsence:
    def test_silent_asset_group_fires_with_ids(self):
        alerts = _alert_rows([
            {"alert_id": f"A-{i}", "asset_id": f"SRV-{i}"} for i in range(20)
        ])
        assets = pd.concat([
            _asset_rows([{"asset_id": f"SRV-{i}", "asset_type": "server"}
                         for i in range(20)]),
            _asset_rows([{"asset_id": f"EP-{i}", "asset_type": "endpoint"}
                         for i in range(15)]),
        ], ignore_index=True)
        f = ns.detect_telemetry_absence(
            _ctx(cse_frames={"alerts": alerts, "assets": assets}))
        assert f is not None
        assert f.evidence["worst_group"] == "endpoint"
        assert len(f.contributing_record_ids) == 15

    def test_full_coverage_silent(self):
        alerts = _alert_rows([
            {"alert_id": f"A-{i}", "asset_id": f"EP-{i % 10}"} for i in range(40)
        ])
        assets = _asset_rows([{"asset_id": f"EP-{i}"} for i in range(10)])
        assert ns.detect_telemetry_absence(
            _ctx(cse_frames={"alerts": alerts, "assets": assets})) is None


class TestEscalationAbsence:
    def test_critical_alerts_never_escalated(self):
        n = 12
        alerts = _alert_rows([
            {"alert_id": f"AL-{i}", "severity": "CRITICAL"} for i in range(n)
        ])
        inv = _inv_rows([
            {"investigation_id": f"INV-{i}", "alert_id": f"AL-{i}"}
            for i in range(n)
        ])
        f = ns.detect_escalation_absence(
            _ctx(cse_frames={"alerts": alerts, "investigations": inv}))
        assert f is not None
        assert "zero_escalations_from_critical" in f.evidence["subchecks_fired"]
        assert f.severity == "HIGH"

    def test_weekend_criticals_without_weekend_escalations(self):
        sat = ts(day=20)  # Saturday
        alerts = _alert_rows([
            {"alert_id": f"AL-{i}", "severity": "CRITICAL", "timestamp": sat}
            for i in range(6)
        ])
        inv = _inv_rows([
            {"investigation_id": f"INV-{i}", "alert_id": f"AL-{i}"}
            for i in range(6)
        ])
        esc = _esc_rows([
            {"escalation_id": f"ES-{i}", "investigation_id": f"INV-{i}",
             "timestamp": ts(day=22), "has_followup": True}       # Mondays
            for i in range(6)
        ])
        f = ns.detect_escalation_absence(_ctx(cse_frames={
            "alerts": alerts, "investigations": inv, "escalations": esc}))
        assert f is not None
        assert "no_weekend_escalations_despite_weekend_criticals" in \
            f.evidence["subchecks_fired"]
        assert f.severity == "MEDIUM"


# ---------------------------------------------------------------------------
# Behavioral-anomaly signals
# ---------------------------------------------------------------------------


class TestTemporalDrift:
    def test_step_drop_detected(self):
        profiles = [_profile(period=p, inv_depth_mean=v)
                    for p, v in [("2024-Q1", 5.0), ("2024-Q2", 5.0),
                                 ("2024-Q3", 2.0), ("2024-Q4", 2.0)]]
        f = ba.detect_temporal_drift(_ctx(profiles=profiles))
        assert f is not None
        assert (f.evidence["from_period"], f.evidence["to_period"]) == \
            ("2024-Q2", "2024-Q3")


class TestQuietPeriod:
    def test_blackout_gap_fires(self):
        prof = _profile(period=PERIOD_ALL, max_gap_hours=200.0,
                        quiet_period_count=0)
        alerts = _alert_rows([{"alert_id": "AL-1", "timestamp": ts()}])
        f = ba.detect_unusual_quiet_period(
            _ctx(profiles=[prof], cse_frames={"alerts": alerts}))
        assert f is not None
        assert "blackout_gap" in f.evidence["triggers_fired"]

    def test_bursty_but_active_feed_silent(self):
        # Clean-envelope numbers observed across the baseline portfolio.
        prof = _profile(period=PERIOD_ALL, max_gap_hours=97.0,
                        quiet_period_count=15)
        stamps = pd.date_range("2024-01-01", periods=500, freq="17h")
        alerts = _alert_rows([
            {"alert_id": f"AL-{i}", "timestamp": t} for i, t in enumerate(stamps)
        ])
        assert ba.detect_unusual_quiet_period(
            _ctx(profiles=[prof], cse_frames={"alerts": alerts})) is None


class TestBulkClosure:
    def test_single_day_mass_closure_fires(self):
        rows = []
        n = 0
        for i in range(12):                      # 11 quiet days
            for j in range(5):
                rows.append({"alert_id": f"AL-{n}", "timestamp": ts(month=1),
                             "closure_timestamp": ts(day=1 + i, month=1)})
                n += 1
        for j in range(60):                      # one burst day
            rows.append({"alert_id": f"AL-{n}",
                         "timestamp": ts(month=3),
                         "closure_timestamp": ts(day=28, month=3)})
            n += 1
        alerts = _alert_rows(rows)
        f = ba.detect_bulk_closure_pattern(
            _ctx(cse_frames={"alerts": alerts}))
        assert f is not None
        assert f.evidence["peak_closures"] == 60

    def test_even_spread_silent(self):
        rows = [{"alert_id": f"AL-{n}",
                 "timestamp": ts(month=1),
                 "closure_timestamp": ts(day=1 + (n // 5), month=1)}
                for n in range(55)]
        assert ba.detect_bulk_closure_pattern(
            _ctx(cse_frames={"alerts": _alert_rows(rows)})) is None


class TestShiftVariance:
    def test_night_shift_shallower_fires(self):
        rows = []
        for i in range(25):  # day shift: deep
            rows.append({"investigation_id": f"D-{i}",
                         "timestamp_open": ts(hour=10),
                         "evidence_entries": 8, "notes": f"d{i}"})
        for i in range(25):  # night shift: shallow
            rows.append({"investigation_id": f"N-{i}",
                         "timestamp_open": ts(hour=2),
                         "evidence_entries": 2, "notes": f"n{i}"})
        joined = _inv_rows(rows)
        f = ba.detect_shift_variance(_ctx(cse_frames={"investigations": joined}))
        assert f is not None
        assert f.evidence["strongest_shift"] == "day"
        assert f.evidence["weakest_shift"] == "night"


class TestRecurringIncident:
    def test_repeating_unclosed_pattern_fires(self):
        rows = []
        n = 0
        for i in range(10):
            status = "open" if i < 6 else "closed"
            rows.append({"alert_id": f"AL-{n}", "asset_id": "HOST-X",
                         "category": "malware", "status": status})
            n += 1
        rows += [{"alert_id": f"AL-{n+i}", "asset_id": f"H{i}",
                  "category": "network", "status": "closed"} for i in range(10)]
        f = ba.detect_recurring_incident(
            _ctx(cse_frames={"alerts": _alert_rows(rows)}))
        assert f is not None
        assert f.evidence["asset_id"] == "HOST-X"
        assert f.evidence["occurrences"] == 10


# ---------------------------------------------------------------------------
# Peer-deviation signals
# ---------------------------------------------------------------------------


def _portfolio_profiles(depths):
    return [
        _profile(cse_id=cid, period=PERIOD_ALL, inv_depth_mean=d)
        for cid, d in depths.items()
    ]


class TestPeerDeviation:
    def test_modified_z_math(self):
        # Zero spread -> z undefined (None); signals must stay silent.
        degenerate = pd_dev._summarize([10.0, 10.0, 10.0, 10.0])
        assert pd_dev.modified_z(99.0, degenerate) is None
        # MAD=0 but std>0 -> std fallback path.
        stat = pd_dev._summarize([10.0, 10.0, 14.0])       # median 10, mad 0
        assert pd_dev.modified_z(16.0, stat) > 2.5
        # Normal path via MAD.
        mad_stat = pd_dev._summarize([8.0, 10.0, 12.0, 14.0, 10.0])
        assert pd_dev.modified_z(10.0, mad_stat) == pytest.approx(0.0, abs=1e-9)

    def test_extreme_low_depth_flags(self):
        depths = {"CSE-A": 4.8, "CSE-B": 5.0, "CSE-C": 5.2, "CSE-D": 5.4,
                  "CSE-T01": 0.1}
        all_profiles = _portfolio_profiles(depths)
        stats = pd_dev.build_peer_stats(all_profiles)
        own = [p for p in all_profiles if p.cse_id == "CSE-T01"]
        f = pd_dev.detect_investigation_depth_outlier(
            _ctx(profiles=own, peer_stats=stats))
        assert f is not None
        assert f.evidence["modified_z"] < -2.5

    def test_small_peer_group_returns_none(self):
        # Only one peer -> below min_group_size; the guard must fire.
        depths = {"CSE-A": 5.0, "CSE-T01": 0.1}
        stats = pd_dev.build_peer_stats(_portfolio_profiles(depths))
        own = [p for p in _portfolio_profiles(depths) if p.cse_id == "CSE-T01"]
        f = pd_dev.detect_investigation_depth_outlier(
            _ctx(profiles=own, peer_stats=stats))
        assert f is None

    def test_identical_peers_no_outliers(self):
        depths = {f"CSE-{i}": 5.0 for i in range(6)}
        depths["CSE-T01"] = 5.0
        stats = pd_dev.build_peer_stats(_portfolio_profiles(depths))
        f = pd_dev.detect_investigation_depth_outlier(
            _ctx(profiles=[p for p in _portfolio_profiles(depths)
                           if p.cse_id == "CSE-T01"],
                 peer_stats=stats))
        assert f is None


# ---------------------------------------------------------------------------
# Engine behaviour
# ---------------------------------------------------------------------------


class TestEngineMechanics:
    def test_registry_has_18_signals_in_four_categories(self):
        assert len(SIGNAL_REGISTRY) == 18
        cats = {cat for cat, _ in SIGNAL_REGISTRY.values()}
        assert cats == {"execution_gap", "negative_space",
                        "behavioral_anomaly", "peer_deviation"}

    def test_all_signals_survive_empty_data(self):
        ctx = _ctx()
        for name, (_, fn) in SIGNAL_REGISTRY.items():
            try:
                assert fn(ctx) is None, f"{name} should stay silent"
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"{name} crashed on empty data: {exc}")

    def test_quality_gate_appends_note_not_crash(self):
        prof = _profile(closure_velocity_median_h=0.5, inv_depth_median=1.0,
                        alert_volume_total=100)
        ctx = _ctx(profiles=[prof], quality_score=0.3)
        findings = run_context(ctx, only=["superficial_closure"])
        assert len(findings) == 1
        assert any("below gate" in n for n in
                   findings[0].data_quality_notes)

    def test_store_clear_load_roundtrip(self, tmp_path):
        db = tmp_path / "f.db"
        prof_a = _profile(cse_id="CSE-A", closure_velocity_median_h=0.5,
                          inv_depth_median=1.0, alert_volume_total=100)
        prof_b = _profile(cse_id="CSE-B", closure_velocity_median_h=0.5,
                          inv_depth_median=1.0, alert_volume_total=100)
        fa = run_context(_ctx(cse_id="CSE-A", profiles=[prof_a]),
                         only=["superficial_closure"])
        fb = run_context(_ctx(cse_id="CSE-B", profiles=[prof_b]),
                         only=["superficial_closure"])
        store_findings(fa + fb, db)
        assert len(load_findings(db)) == 2

        clear_findings(db, cse_id="CSE-A")
        left = load_findings(db)
        assert list(left.cse_id) == ["CSE-B"]

    def test_run_signals_end_to_end_on_tiny_db(self, tmp_path):
        """Full pipeline over a 6-CSE synthetic portfolio stored in SQLite."""
        from src.analytics.profiler import compute_all_profiles, store_profiles
        from src.analytics.sample_data import generate_dataset
        from src.analytics.signal_engine import run_signals
        from src.storage.db import save_frames

        frames = generate_dataset(seed=42, n_cses=6)
        db = tmp_path / "tiny.db"
        save_frames(frames, db)
        store_profiles(compute_all_profiles(frames), db)

        findings = run_signals(db)
        assert isinstance(findings, list)
        rows = load_findings(db)
        assert len(rows) == len(findings)
        # Idempotent re-run must not accumulate rows.
        run_signals(db)
        assert len(load_findings(db)) == len(rows)

    def test_clear_findings_by_category_spares_others(self, tmp_path):
        from src.analytics.finding import Finding

        def _f(cse_id, cat):
            return Finding(
                finding_id=f"{cse_id}:{cat}", cse_id=cse_id,
                signal_type=f"sig_{cat}", signal_category=cat, period="ALL",
                severity="LOW", confidence=0.5, evidence={},
                created_at=None,
            )

        db = tmp_path / "scope.db"
        store_findings([_f("CSE-A", "execution_gap"),
                        _f("CSE-A", "negative_space")], db)
        clear_findings(db, category="execution_gap")
        left = load_findings(db)
        assert list(left.signal_category) == ["negative_space"]


# ---------------------------------------------------------------------------
# Full-portfolio integration (demo dataset)
# ---------------------------------------------------------------------------


def _load_demo():
    readers = {
        "alerts": {"parse_dates": ["timestamp", "closure_timestamp"]},
        "investigations": {"parse_dates": ["timestamp_open", "timestamp_close"]},
        "escalations": {"parse_dates": ["timestamp"]},
    }
    return {name: pd.read_csv(DEMO_DIR / f"{name}.csv", **readers.get(name, {}))
            for name in ENTITY_TYPES}


@pytest.fixture(scope="module")
def demo_findings():
    from src.analytics.profiler import compute_all_profiles

    frames = _load_demo()
    profiles = compute_all_profiles(frames)
    contexts = build_contexts(frames, profiles)
    findings = []
    for ctx in contexts.values():
        findings.extend(run_context(ctx))
    return findings


class TestSeededWeaknessDetection:
    def test_every_seeded_weakness_detected_by_expected_signal(self,
                                                               demo_findings):
        by_pair = {(f.cse_id, f.signal_type) for f in demo_findings}
        for cse_id, signals in EXPECTED_SEED_SIGNALS.items():
            for sig in signals:
                assert (cse_id, sig) in by_pair, \
                    f"{cse_id}: expected {sig} to fire"

    def test_all_eight_seeded_cses_flagged(self, demo_findings):
        flagged = {f.cse_id for f in demo_findings}
        assert SEEDED <= flagged

    def test_no_clean_cse_earns_high_severity(self, demo_findings):
        offenders = {
            f.cse_id for f in demo_findings
            if f.severity == "HIGH" and f.cse_id not in SEEDED
        }
        assert not offenders, f"false-positive HIGH findings: {offenders}"

    def test_findings_are_fully_documented(self, demo_findings):
        assert demo_findings, "engine produced nothing"
        for f in demo_findings:
            assert f.confidence == pytest.approx(f.confidence, abs=1e-9)
            assert 0.0 <= f.confidence <= 1.0
            assert f.severity in ("HIGH", "MEDIUM", "LOW")
            cat = SIGNAL_REGISTRY[f.signal_type][0]
            assert f.signal_category == cat
            assert isinstance(f.evidence, dict) and f.evidence
            assert f.detection_logic
            assert STANDARD_CAVEAT in f.caveats
            assert f.recommended_actions
