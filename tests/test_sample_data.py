"""Tests for the synthetic dataset generator and its seeded weaknesses.

The full demo dataset is generated once per session (or loaded from the
CSVs produced by scripts/generate_sample_data.py). Each seeded weakness has
a regression test asserting it is *detectable from the data* — the same way
the analytics engines will see it.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.analytics.sample_data import SEEDED_SCENARIOS, generate_dataset

DEMO_DIR = Path("data/samples/demo_dataset")
ENTITY_TYPES = (
    "cse_metadata", "alerts", "investigations",
    "escalations", "cases", "assets",
)


def _load_or_generate() -> dict[str, pd.DataFrame]:
    paths = {name: DEMO_DIR / f"{name}.csv" for name in ENTITY_TYPES}
    if all(p.exists() for p in paths.values()):
        return {
            name: pd.read_csv(
                p,
                parse_dates=_date_cols(name),
            )
            for name, p in paths.items()
        }
    return generate_dataset(seed=42)


def _date_cols(entity: str) -> list[str] | None:
    cols = {
        "alerts": ["timestamp", "closure_timestamp"],
        "investigations": ["timestamp_open", "timestamp_close"],
        "escalations": ["timestamp"],
        "cases": ["closure_time"],
        "cse_metadata": ["submitted_at"],
    }
    return cols.get(entity)


@pytest.fixture(scope="session")
def data() -> dict[str, pd.DataFrame]:
    return _load_or_generate()


@pytest.fixture(scope="session")
def inv_with_alerts(data) -> pd.DataFrame:
    """Investigations joined to alert severity/quarter."""
    ia = data["investigations"].merge(
        data["alerts"][["alert_id", "severity"]], on="alert_id"
    )
    ia["dur_h"] = (
        ia.timestamp_close - ia.timestamp_open
    ).dt.total_seconds() / 3600
    return ia


# ---------------------------------------------------------------------------
# Structural integrity
# ---------------------------------------------------------------------------


class TestStructure:
    def test_all_six_entity_types_present(self, data):
        for name in ENTITY_TYPES:
            assert name in data and len(data[name]) > 0

    def test_50_cses(self, data):
        assert data["cse_metadata"].cse_id.nunique() == 50
        assert set(SEEDED_SCENARIOS).issubset(set(data["cse_metadata"].cse_id))

    def test_required_ids_not_null(self, data):
        assert data["alerts"].alert_id.notna().all()
        assert data["investigations"].investigation_id.notna().all()
        assert data["escalations"].escalation_id.notna().all()
        assert data["assets"].asset_id.notna().all()

    def test_referential_integrity(self, data):
        alert_ids = set(data["alerts"].alert_id)
        inv_ids = set(data["investigations"].investigation_id)
        asset_ids = set(data["assets"].asset_id)

        assert set(data["investigations"].alert_id).issubset(alert_ids)
        assert set(data["escalations"].investigation_id).issubset(inv_ids)
        assert set(data["alerts"].asset_id).issubset(asset_ids)
        assert set(data["assets"].cse_id).issubset(set(data["cse_metadata"].cse_id))

    def test_timestamps_ordered(self, data):
        al = data["alerts"].dropna(subset=["closure_timestamp"])
        assert (al.closure_timestamp >= al.timestamp).all()
        iv = data["investigations"].dropna(subset=["timestamp_close"])
        assert (iv.timestamp_close >= iv.timestamp_open).all()

    def test_severity_vocabulary(self, data):
        assert set(data["alerts"].severity).issubset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})


class TestReproducibility:
    def test_same_seed_identical_output(self):
        f1 = generate_dataset(seed=7, n_cses=3)
        f2 = generate_dataset(seed=7, n_cses=3)
        for name in ENTITY_TYPES:
            pd.testing.assert_frame_equal(f1[name], f2[name])

    def test_different_seed_different_output(self):
        f1 = generate_dataset(seed=7, n_cses=3)
        f2 = generate_dataset(seed=8, n_cses=3)
        assert not f1["alerts"].alert_id.equals(f2["alerts"].alert_id)


# ---------------------------------------------------------------------------
# Seeded weaknesses (ground truth oracle for validation)
# ---------------------------------------------------------------------------


class TestSeededWeaknesses:
    def test_cse042_depth_degradation(self, inv_with_alerts):
        d = inv_with_alerts[inv_with_alerts.cse_id == "CSE-042"]
        by_q = d.groupby(d.timestamp_open.dt.quarter).evidence_entries.mean()
        decline = (by_q.loc[1] - by_q.loc[4]) / by_q.loc[1]
        assert decline >= 0.60, f"expected ≥60% depth decline, got {decline:.0%}"

    def test_cse017_superficial_closures_no_critical_escalation(
        self, data, inv_with_alerts
    ):
        c17 = inv_with_alerts[inv_with_alerts.cse_id == "CSE-017"]
        peers = inv_with_alerts[inv_with_alerts.cse_id != "CSE-017"]
        assert c17.evidence_entries.mean() < 0.5 * peers.evidence_entries.mean()
        assert c17.dur_h.median() < 0.5 * peers.dur_h.median()

        crit_ids = set(
            data["alerts"][
                (data["alerts"].cse_id == "CSE-017")
                & (data["alerts"].severity == "CRITICAL")
            ].alert_id
        )
        e = data["escalations"]
        esc_for_crit = e[e.investigation_id.isin(
            c17[c17.alert_id.isin(crit_ids)].investigation_id
        )]
        assert len(esc_for_crit) == 0

    def test_cse089_zero_endpoint_alerts_despite_endpoints(self, data):
        ep_assets = data["assets"][
            (data["assets"].cse_id == "CSE-089")
            & (data["assets"].asset_type == "endpoint")
        ]
        ep_alerts = data["alerts"][
            (data["alerts"].cse_id == "CSE-089")
            & (data["alerts"].category == "endpoint")
        ]
        assert len(ep_assets) > 100
        assert len(ep_alerts) == 0

    def test_cse031_missing_investigations_on_high_severity(self, data):
        hi = data["alerts"][
            (data["alerts"].cse_id == "CSE-031")
            & data["alerts"].severity.isin(["HIGH", "CRITICAL"])
        ]
        missing = (~hi.alert_id.isin(set(data["investigations"].alert_id))).mean()
        assert missing >= 0.80

    def test_cse055_closure_velocity_outlier(self, inv_with_alerts):
        med_min = inv_with_alerts.groupby("cse_id").dur_h.median() * 60
        rest = med_min.drop("CSE-055")
        z = (med_min["CSE-055"] - rest.mean()) / rest.std()
        assert z <= -2.5, f"CSE-055 should be a ≤−2.5σ outlier, got z={z:.1f}"

    def test_cse073_no_weekend_escalations(self, data):
        w = data["escalations"][data["escalations"].cse_id == "CSE-073"]
        assert len(w) > 50  # enough escalations for the gap to be meaningful
        assert (w.timestamp.dt.weekday < 5).all()

    def test_cse019_templated_notes(self, data):
        notes = data["investigations"][
            data["investigations"].cse_id == "CSE-019"
        ].notes
        assert len(notes) > 200
        assert notes.duplicated().mean() >= 0.90

    def test_cse061_combined_weaknesses(self, inv_with_alerts, data):
        c61 = inv_with_alerts[inv_with_alerts.cse_id == "CSE-061"]
        peers = inv_with_alerts[inv_with_alerts.cse_id != "CSE-061"]
        assert c61.evidence_entries.mean() < 0.6 * peers.evidence_entries.mean()
        assert c61.dur_h.median() < 0.6 * peers.dur_h.median()

        fu = data["escalations"][
            data["escalations"].investigation_id.isin(c61.investigation_id)
        ]
        no_followup = (~fu.has_followup).mean()
        assert no_followup >= 0.30


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
