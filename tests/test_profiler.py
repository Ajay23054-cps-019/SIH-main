"""Tests for the behavioral profiler.

Unit tests use tiny handcrafted frames with exact-value assertions so the
metric math is pinned down; the integration suite runs the profiler over the
full demo dataset and checks structural acceptance criteria plus one seeded
weakness (CSE-042 degrading depth) seen through profile metrics alone.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.analytics.profiles import PERIOD_ALL
from src.analytics.profiler import (
    compute_all_profiles,
    compute_profile,
    load_profiles,
    store_profiles,
    _pct_change,
)
from src.analytics.sample_data import generate_dataset

DEMO_DIR = Path("data/samples/demo_dataset")
ENTITY_TYPES = (
    "cse_metadata", "alerts", "investigations",
    "escalations", "cases", "assets",
)


# ---------------------------------------------------------------------------
# Frame builders
# ---------------------------------------------------------------------------


def _alerts(rows):
    base = {
        "alert_id": None, "cse_id": "CSE-T01", "timestamp": None,
        "severity": "HIGH", "category": "malware", "asset_id": "A-1",
        "status": "closed", "closure_timestamp": None, "description": None,
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def _investigations(rows):
    base = {
        "investigation_id": None, "alert_id": None, "cse_id": "CSE-T01",
        "timestamp_open": None, "timestamp_close": None,
        "evidence_entries": 0, "assigned_to": None, "notes": "note",
        "depth_score": None,
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def _escalations(rows):
    base = {
        "escalation_id": None, "investigation_id": None,
        "cse_id": "CSE-T01", "timestamp": None, "decision": "escalated",
        "has_followup": True, "recipient": "CSO", "rationale": None,
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def _assets(n=3):
    return pd.DataFrame([
        {"asset_id": f"A-{i}", "cse_id": "CSE-T01", "asset_type": "server",
         "criticality": "HIGH", "environment": "production",
         "monitoring_status": "monitored" if i else "unmonitored"}
        for i in range(n)
    ])


def ts(hour, day=15, month=1, minute=0):
    return pd.Timestamp(f"2024-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:00")


def _profile(alerts, investigations=None, escalations=None, assets=None,
             period="2024-Q1", previous=None):
    return compute_profile(
        "CSE-T01", period,
        alerts,
        investigations if investigations is not None else pd.DataFrame(),
        escalations if escalations is not None else pd.DataFrame(),
        assets if assets is not None else _assets(),
        previous=previous,
    )


# ---------------------------------------------------------------------------
# Helper math
# ---------------------------------------------------------------------------


class TestPctChange:
    def test_basic(self):
        assert _pct_change(1.5, 1.0) == pytest.approx(0.5)

    def test_decrease_uses_abs_denominator(self):
        # 1.0 from a previous of 4.0 -> +25%, sign from numerator only.
        assert _pct_change(1.0, -4.0) == pytest.approx(1.25)

    def test_none_propagates(self):
        assert _pct_change(None, 1.0) is None
        assert _pct_change(1.0, None) is None

    def test_zero_previous_is_none(self):
        assert _pct_change(1.0, 0) is None


# ---------------------------------------------------------------------------
# Metric computation — exact values
# ---------------------------------------------------------------------------


class TestAlertMetrics:
    def test_volume_and_severity_split(self):
        alerts = _alerts([
            {"alert_id": "AL-1", "timestamp": ts(9), "severity": "CRITICAL",
             "closure_timestamp": ts(11)},
            {"alert_id": "AL-2", "timestamp": ts(10), "severity": "CRITICAL"},
            {"alert_id": "AL-3", "timestamp": ts(10, day=16), "severity": "LOW"},
        ])
        m = _profile(alerts).metrics
        assert m["alert_volume_total"] == 3
        assert m["sev_critical_count"] == 2
        assert m["sev_critical_pct"] == pytest.approx(2 / 3, abs=1e-3)
        assert m["sev_low_pct"] == pytest.approx(1 / 3, abs=1e-3)

    def test_closure_velocity_median(self):
        alerts = _alerts([
            {"alert_id": "AL-1", "timestamp": ts(9),
             "closure_timestamp": ts(11)},   # 2h
            {"alert_id": "AL-2", "timestamp": ts(9, day=16),
             "closure_timestamp": ts(13, day=16)},  # 4h
        ])
        assert _profile(alerts).metrics["closure_velocity_median_h"] == 3.0

    def test_after_hours_share(self):
        alerts = _alerts([
            {"alert_id": "AL-1", "timestamp": ts(9)},    # business
            {"alert_id": "AL-2", "timestamp": ts(23)},   # after hours
        ])
        assert _profile(alerts).metrics["after_hours_alert_share"] == 0.5

    def test_weekend_share(self):
        # 2024-01-20 is a Saturday.
        alerts = _alerts([
            {"alert_id": "AL-1", "timestamp": ts(9)},
            {"alert_id": "AL-2", "timestamp": ts(9, day=20)},
        ])
        assert _profile(alerts).metrics["weekend_alert_share"] == 0.5


class TestInvestigationMetrics:
    def _fixture(self):
        alerts = _alerts([
            {"alert_id": "AL-1", "timestamp": ts(9), "severity": "CRITICAL",
             "closure_timestamp": ts(12)},
            {"alert_id": "AL-2", "timestamp": ts(10), "severity": "HIGH"},
            {"alert_id": "AL-3", "timestamp": ts(10), "severity": "LOW"},
            {"alert_id": "AL-4", "timestamp": ts(10), "severity": "MEDIUM"},
        ])
        invs = _investigations([
            {"investigation_id": "INV-1", "alert_id": "AL-1",
             "timestamp_open": ts(9, minute=30), "timestamp_close": ts(11),
             "evidence_entries": 3},
            {"investigation_id": "INV-2", "alert_id": "AL-2",
             "timestamp_open": ts(10, minute=30), "timestamp_close": ts(14),
             "evidence_entries": 5},
            # Orphan: points at an alert that does not exist.
            {"investigation_id": "INV-3", "alert_id": "AL-GHOST",
             "timestamp_open": ts(11), "timestamp_close": ts(12),
             "evidence_entries": 9},
        ])
        return alerts, invs

    def test_rate_depth_orphans(self):
        alerts, invs = self._fixture()
        p = _profile(alerts, invs)
        m = p.metrics
        assert m["investigation_rate"] == 0.5          # 2 linked / 4 alerts
        assert m["inv_depth_mean"] == 4.0              # (3 + 5) / 2
        assert m["orphan_investigations"] == 1
        # Orphans must not pollute depth statistics.
        assert m["inv_depth_p75"] == 4.5

    def test_duration_stats(self):
        alerts, invs = self._fixture()
        m = _profile(alerts, invs).metrics
        assert m["inv_duration_p50_h"] == 2.5          # durations 1.5h and 3.5h
        assert m["inv_duration_mean_h"] == 2.5

    def test_severity_attribution_from_alert(self):
        alerts, invs = self._fixture()
        m = _profile(alerts, invs).metrics
        assert m["inv_depth_by_severity"]["CRITICAL"] == 3.0
        assert m["inv_depth_by_severity"]["HIGH"] == 5.0

    def test_triage_only_high_sev(self):
        alerts, invs = self._fixture()
        # AL-5: CRITICAL, closed, but never investigated -> triage-only closure.
        extra = _alerts([{"alert_id": "AL-5", "timestamp": ts(12),
                          "severity": "CRITICAL"}])
        alerts = pd.concat([alerts, extra], ignore_index=True)
        # Denominator: AL-1, AL-2, AL-5 (closed AND high-severity).
        # Investigated set covers AL-1 and AL-2; only AL-5 is triage-only.
        m = _profile(alerts, invs).metrics
        assert m["triage_only_high_sev_rate"] == pytest.approx(1 / 3, abs=1e-3)


class TestEscalationMetrics:
    def _fixture(self):
        alerts = _alerts([
            {"alert_id": "AL-1", "timestamp": ts(9), "severity": "CRITICAL",
             "status": "closed", "closure_timestamp": ts(12)},
            {"alert_id": "AL-2", "timestamp": ts(10), "severity": "CRITICAL"},
        ])
        invs = _investigations([
            {"investigation_id": "INV-1", "alert_id": "AL-1",
             "timestamp_open": ts(9), "timestamp_close": ts(11),
             "evidence_entries": 4},
            {"investigation_id": "INV-2", "alert_id": "AL-2",
             "timestamp_open": ts(10), "timestamp_close": ts(12),
             "evidence_entries": 6},
        ])
        escs = _escalations([
            {"escalation_id": "ES-1", "investigation_id": "INV-1",
             "timestamp": ts(11), "has_followup": True},
            {"escalation_id": "ES-2", "investigation_id": "INV-GHOST",
             "timestamp": ts(12), "has_followup": False},
        ])
        return alerts, invs, escs

    def test_rates(self):
        alerts, invs, escs = self._fixture()
        m = _profile(alerts, invs, escs).metrics
        assert m["esc_rate"] == 0.5                    # 1 linked / 2 investigations
        assert m["esc_orphan_count"] == 1
        assert m["esc_followthrough_rate"] == 1.0      # the linked one had followup

    def test_missing_escalations_warns_but_survives(self):
        alerts, invs, _ = self._fixture()
        p = _profile(alerts, invs, escalations=pd.DataFrame())
        assert p.metrics["esc_rate"] is None
        assert any("no escalation" in w.lower() for w in p.warnings)


# ---------------------------------------------------------------------------
# Missing-data graceful degradation
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    def test_no_investigations_warns_not_crashes(self):
        alerts = _alerts([{"alert_id": "AL-1", "timestamp": ts(9)}])
        p = _profile(alerts)
        assert p.metrics["investigation_rate"] is None
        assert p.metrics["inv_depth_mean"] is None
        assert any("no investigation" in w.lower() for w in p.warnings)

    def test_no_alerts_minimal_profile(self):
        p = _profile(_alerts([]))
        assert p.n_alerts == 0
        assert p.metrics["alert_volume_total"] == 0
        assert any("no alert records" in w.lower() for w in p.warnings)

    def test_scalar_metrics_are_numeric_only(self):
        alerts = _alerts([{"alert_id": "AL-1", "timestamp": ts(9)}])
        p = _profile(alerts)
        # Nested distributions must be excluded from scalar view.
        assert "category_distribution" not in p.scalar_metrics
        assert all(isinstance(v, (int, float)) for v in p.scalar_metrics.values())


# ---------------------------------------------------------------------------
# Period filtering & trends
# ---------------------------------------------------------------------------


class TestPeriodsAndTrends:
    def _two_quarters(self):
        alerts = _alerts([
            {"alert_id": "AL-1", "timestamp": ts(9, month=1),
             "closure_timestamp": ts(10, month=1)},
            {"alert_id": "AL-2", "timestamp": ts(9, month=4)},
        ])
        invs_q1 = _investigations([
            {"investigation_id": "INV-1", "alert_id": "AL-1",
             "timestamp_open": ts(9, month=1), "timestamp_close": ts(10, month=1),
             "evidence_entries": 8},
        ])
        invs_q2 = _investigations([
            {"investigation_id": "INV-2", "alert_id": "AL-2",
             "timestamp_open": ts(9, month=4), "timestamp_close": ts(10, month=4),
             "evidence_entries": 4},
        ])
        return alerts, pd.concat([invs_q1, invs_q2], ignore_index=True)

    def test_period_filter_counts_only_requested_quarter(self):
        alerts, _ = self._two_quarters()
        p = _profile(alerts, period="2024-Q1")
        assert p.metrics["alert_volume_total"] == 1
        p2 = _profile(alerts, period="2024-Q2")
        assert p2.metrics["alert_volume_total"] == 1

    def test_first_quarter_trends_none_second_computed(self):
        alerts, invs = self._two_quarters()
        q1 = _profile(alerts, invs, period="2024-Q1")
        assert q1.metrics["depth_trend_qoq_pct"] is None

        q2 = _profile(
            alerts, invs, period="2024-Q2",
            previous={"inv_depth_mean": q1.metrics["inv_depth_mean"],
                      "closure_velocity_median_h": None, "esc_rate": None},
        )
        expected = (4 - 8) / 8
        assert q2.metrics["depth_trend_qoq_pct"] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Full-pipeline integration (demo dataset)
# ---------------------------------------------------------------------------


def _load_or_generate() -> dict[str, pd.DataFrame]:
    paths = {name: DEMO_DIR / f"{name}.csv" for name in ENTITY_TYPES}
    if all(p.exists() for p in paths.values()):
        readers = {
            "alerts": {"parse_dates": ["timestamp", "closure_timestamp"]},
            "investigations": {"parse_dates": ["timestamp_open", "timestamp_close"]},
            "escalations": {"parse_dates": ["timestamp"]},
        }
        return {
            name: pd.read_csv(p, **readers.get(name, {}))
            for name, p in paths.items()
        }
    return generate_dataset(seed=42)


@pytest.fixture(scope="module")
def demo():
    return _load_or_generate()


@pytest.fixture(scope="module")
def profiles(demo):
    return compute_all_profiles(demo)


class TestIntegration:
    def test_200_quarterly_plus_50_full_window(self, profiles):
        by_period = {}
        for p in profiles:
            key = "ALL" if p.period == PERIOD_ALL else "quarter"
            by_period[key] = by_period.get(key, 0) + 1
        assert by_period["quarter"] == 200   # 50 CSEs x 4 quarters
        assert by_period["ALL"] == 50

    def test_every_profile_has_20plus_scalar_metrics(self, profiles):
        thin = [p for p in profiles if len(p.scalar_metrics) < 20]
        assert not thin, f"{len(thin)} profiles below 20 scalar metrics"

    def test_no_crash_on_empty_slices(self, profiles):
        # Every profile computed without exception is itself the assertion;
        # spot-check that metrics dicts are non-empty.
        assert all(p.metrics for p in profiles)

    def test_cse042_depth_declines_across_quarters(self, profiles):
        """Seeded weakness 'degrading_depth' must be visible in profiles."""
        depths = [
            p.metrics["inv_depth_mean"]
            for p in profiles
            if p.cse_id == "CSE-042" and p.period != PERIOD_ALL
        ]
        assert len(depths) == 4
        assert all(a > b for a, b in zip(depths, depths[1:])), \
            f"expected strict decline, got {depths}"
        assert depths[-1] < 0.5 * depths[0]

    def test_store_and_load_roundtrip(self, profiles, tmp_path):
        db = tmp_path / "profiles.db"
        n = store_profiles(profiles[:5], db)
        assert n == 5
        loaded = load_profiles(db, cse_id=profiles[0].cse_id)
        row = loaded.iloc[0]
        assert isinstance(row["metrics"], dict)
        assert row["metrics"]["alert_volume_total"] >= 0
        # Upsert idempotence: storing twice doesn't duplicate rows.
        store_profiles(profiles[:5], db)
        assert len(load_profiles(db)) == 5
