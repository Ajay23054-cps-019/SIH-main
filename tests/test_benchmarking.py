"""Tests for Phase 7 peer benchmarking (groups, z-scores, percentiles)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.analytics.benchmarking import (
    DEFAULT_BENCHMARKING,
    BENCHMARKS_TABLE_SQL,
    CSEBenchmark,
    MetricBenchmark,
    _slug,
    benchmark_cse,
    benchmark_metric,
    build_all_benchmarks,
    build_peer_groups,
    group_label,
    load_benchmarks,
    normalize_metadata,
    percentile_rank,
    store_benchmarks,
)
from src.analytics.finding import load_thresholds
from src.analytics.profiles import PERIOD_ALL, BehavioralProfile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prof(cse_id, period=PERIOD_ALL, **metrics):
    return BehavioralProfile(cse_id=cse_id, period=period,
                             metrics=dict(metrics), warnings=[],
                             n_alerts=int(metrics.get("alert_volume_total", 0)))


TELECOM_LARGE = {"CSE-A": ("Telecom", "Large"), "CSE-B": ("Telecom", "Large"),
                 "CSE-C": ("Telecom", "Large"), "CSE-D": ("Telecom", "Large")}


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


class TestGrouping:
    def test_slug_normalises_sector_names(self):
        assert _slug("Power & Energy") == "Power_Energy"
        assert _slug("Telecom") == "Telecom"

    def test_slug_degrades_blank_and_nan_to_unknown(self):
        assert _slug(None) == "Unknown"
        assert _slug("") == "Unknown"
        assert _slug(np.nan) == "Unknown"
        assert _slug("///") == "Unknown"

    def test_group_label_composition(self):
        assert group_label("Power & Energy", "Medium") == "Power_Energy_Medium"
        assert group_label(None, "Small") == "Unknown_Small"

    def test_build_peer_groups_from_dataframe(self):
        df = pd.DataFrame([
            {"cse_id": "T1", "sector": "Telecom", "size_band": "Large"},
            {"cse_id": "T2", "sector": "Telecom", "size_band": "Large"},
            {"cse_id": "P1", "sector": "Power & Energy", "size_band": "Small"},
        ])
        groups = build_peer_groups(df)
        assert groups["Telecom_Large"] == ["T1", "T2"]
        assert groups["Power_Energy_Small"] == ["P1"]

    def test_missing_metadata_lands_in_unknown_group(self):
        df = pd.DataFrame([{"cse_id": "X1", "sector": np.nan,
                            "size_band": None}])
        groups = build_peer_groups(df)
        assert groups == {"Unknown_Unknown": ["X1"]}

    def test_mapping_input_accepted(self):
        groups = build_peer_groups({"A": ("Telecom", "Large"),
                                    "B": ("Telecom", "Large")})
        assert groups == {"Telecom_Large": ["A", "B"]}

    def test_bad_input_type_raises(self):
        with pytest.raises(TypeError):
            normalize_metadata(["not", "a", "mapping"])

    def test_generator_quota_table_guarantees_populated_cells(self):
        from src.analytics.sample_data import COMBO_TARGETS, _assign_entities

        specs = _assign_entities(np.random.default_rng(123))
        counts: dict = {}
        for s in specs:
            counts[(s.sector, s.size_band)] = \
                counts.get((s.sector, s.size_band), 0) + 1
        assert counts == {(sec, band): n
                          for sec, bands in COMBO_TARGETS.items()
                          for band, n in bands.items()}
        assert min(counts.values()) >= 3


# ---------------------------------------------------------------------------
# Percentile ranks
# ---------------------------------------------------------------------------


class TestPercentileRank:
    def test_exact_rank(self):
        # value absent from list: 3 of [1,2,3,4] lie strictly below 3.5
        assert percentile_rank(3.5, [1, 2, 3, 4]) == pytest.approx(75.0)
        # value present: it ties with itself -> half a rank
        assert percentile_rank(3.0, [1, 2, 3, 4]) == pytest.approx(62.5)

    def test_ties_split_the_difference(self):
        # [1,2,2,3], value 2 -> 1 below, 2 tied -> (1+1)/4 = 50th
        assert percentile_rank(2.0, [1, 2, 2, 3]) == pytest.approx(50.0)

    def test_extremes(self):
        assert percentile_rank(1.0, [1, 2, 3]) == pytest.approx(
            100 * 0.5 / 3)
        assert percentile_rank(3.0, [1, 2, 3]) == pytest.approx(
            100 * (2 + 0.5) / 3)


# ---------------------------------------------------------------------------
# Per-metric benchmark
# ---------------------------------------------------------------------------


class TestBenchmarkMetric:
    def test_exact_stats_and_z(self):
        mb = benchmark_metric("inv_depth_mean", 6.0, [2.0, 4.0, 6.0])
        assert mb.peer_mean == pytest.approx(4.0)
        assert mb.peer_median == pytest.approx(4.0)
        assert mb.peer_std == pytest.approx(np.std([2, 4, 6]), abs=1e-5)
        assert mb.z_score == pytest.approx((6 - 4) / np.std([2, 4, 6]),
                                           abs=1e-3)
        # pooled [2,4,6,6]: 2 below, 2 tied -> 75th
        assert mb.percentile == pytest.approx(75.0)
        assert not mb.is_outlier

    def test_outlier_flagged_with_enough_support(self):
        peers = [9.9, 10.0, 10.1, 9.8, 10.2]
        mb = benchmark_metric("m", 12.0, peers, outlier_z=2.5)
        assert mb.is_outlier
        assert mb.z_score > 2.5

    def test_flag_suppressed_without_peer_support(self):
        mb = benchmark_metric("m", 12.0, [10.0, 10.1])   # only 2 peers
        assert mb.z_score is not None and abs(mb.z_score) > 2.5
        assert not mb.is_outlier
        assert "suppressed" in mb.note

    def test_zero_variance_yields_no_z_but_keeps_percentile(self):
        mb = benchmark_metric("m", 5.0, [5.0, 5.0, 5.0])
        assert mb.z_score is None
        assert not mb.is_outlier
        assert mb.percentile == pytest.approx(50.0)
        assert "zero variance" in mb.note

    def test_zero_variance_with_divergent_value(self):
        mb = benchmark_metric("m", 9.0, [5.0, 5.0, 5.0])
        assert mb.z_score is None
        assert mb.percentile == pytest.approx(87.5)

    def test_fewer_than_two_peers_returns_none(self):
        assert benchmark_metric("m", 1.0, [2.0]) is None
        assert benchmark_metric("m", 1.0, []) is None


# ---------------------------------------------------------------------------
# Per-CSE benchmark
# ---------------------------------------------------------------------------


class TestBenchmarkCSE:
    def _profiles(self):
        profs = [_prof("CSE-A", inv_depth_mean=1.0,
                       closure_velocity_median_h=2.45, esc_rate=0.12)]
        for cid, depth in (("CSE-B", 4.85), ("CSE-C", 4.90),
                           ("CSE-D", 4.95)):
            profs.append(_prof(cid, inv_depth_mean=depth,
                               closure_velocity_median_h=2.45,
                               esc_rate=0.12))
        return profs

    def test_shallow_cse_flagged_against_its_group(self):
        bench = benchmark_cse("CSE-A", self._profiles(), TELECOM_LARGE)
        assert bench.usable
        assert bench.group_label == "Telecom_Large"
        assert sorted(bench.peer_ids) == ["CSE-B", "CSE-C", "CSE-D"]
        depth = next(b for b in bench.benchmarks
                     if b.metric == "inv_depth_mean")
        assert depth.is_outlier and depth.z_score < 0

    def test_group_definition_discloses_membership(self):
        bench = benchmark_cse("CSE-A", self._profiles(), TELECOM_LARGE)
        text = bench.group_definition
        for cid in ("CSE-A", "CSE-B", "CSE-C", "CSE-D"):
            assert cid in text
        assert "(3 peers + self" in text

    def test_summary_matches_spec_shape(self):
        bench = benchmark_cse("CSE-A", self._profiles(), TELECOM_LARGE)
        text = bench.summary()
        assert text.startswith(f"CSE CSE-A — Peer group")
        assert "Metric: inv_depth_mean" in text
        assert "← OUTLIER" in text
        assert "Peer mean:" in text and "Peer std:" in text

    def test_small_group_scores_but_notes_noise(self):
        meta = {k: v for k, v in TELECOM_LARGE.items() if k != "CSE-D"}
        bench = benchmark_cse("CSE-A", self._profiles(), meta)
        assert bench.usable                      # 3 members >= min_group_size
        assert bench.n_peers == 2
        depth = next(b for b in bench.benchmarks
                     if b.metric == "inv_depth_mean")
        assert "small peer set" in depth.note
        # |z| would be extreme, but two peers cannot support a flag
        assert not depth.is_outlier

    def test_metric_skipped_when_peers_do_not_report_it(self):
        profs = self._profiles()
        del profs[1].metrics["esc_rate"]         # CSE-B loses the metric
        del profs[2].metrics["esc_rate"]         # CSE-C too
        bench = benchmark_cse("CSE-A", profs, TELECOM_LARGE)
        assert "esc_rate" in bench.skipped
        assert "peer(s)" in bench.skipped["esc_rate"]

    def test_single_member_group_not_scored(self):
        bench = benchmark_cse("CSE-Z", [_prof("CSE-Z", inv_depth_mean=3.0)],
                              {"CSE-Z": ("Telecom", "Large")})
        assert not bench.usable
        assert "too small" in bench.skipped["__all__"]

    def test_missing_profile_reported_not_raised(self):
        bench = benchmark_cse("Ghost", [], TELECOM_LARGE)
        assert not bench.usable
        assert "no profile" in bench.skipped["__all__"]

    def test_periods_do_not_leak(self):
        # Peers exist only in quarterly profiles; ALL window stands alone.
        profs = [_prof("CSE-A", period="2024-Q1", inv_depth_mean=1.0),
                 _prof("CSE-B", period="2024-Q2", inv_depth_mean=4.9),
                 _prof("CSE-C", period="2024-Q3", inv_depth_mean=4.9)]
        bench = benchmark_cse("CSE-A", profs, TELECOM_LARGE,
                              period="2024-Q1")
        assert not bench.usable
        assert bench.peer_ids == []

    def test_nested_metrics_are_ignored(self):
        profs = self._profiles()
        profs[0].metrics["category_distribution"] = {"malware": 5}
        bench = benchmark_cse("CSE-A", profs, TELECOM_LARGE)
        assert all(b.metric != "category_distribution" for b in bench.benchmarks)

    def test_unknown_metadata_defaults_to_unknown_group(self):
        profs = self._profiles()
        bench = benchmark_cse("CSE-A", profs, {})   # no metadata at all
        assert bench.group_label == "Unknown_Unknown"
        assert not bench.usable

    def test_config_overrides_apply(self):
        thr = {"benchmarking": {"min_group_size": 99}}
        bench = benchmark_cse("CSE-A", self._profiles(), TELECOM_LARGE,
                              thresholds=thr)
        assert not bench.usable     # even a 4-member cell fails min=99


class TestBuildAllBenchmarks:
    def test_every_profiled_cse_gets_one_entry_per_period(self):
        profs = []
        for cid in ("A", "B", "C", "D"):
            profs.append(_prof(cid, inv_depth_mean=4.9))
        meta = {c: ("Telecom", "Large") for c in "ABCD"}
        benches = build_all_benchmarks(profs, meta)
        assert [b.cse_id for b in benches] == ["A", "B", "C", "D"]
        assert all(b.period == PERIOD_ALL for b in benches)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestStorage:
    def _benches(self):
        profs = TestBenchmarkCSE._profiles(TestBenchmarkCSE())
        return [benchmark_cse("CSE-A", profs, TELECOM_LARGE)]

    def test_roundtrip_and_filters(self, tmp_path):
        db = tmp_path / "bench.db"
        benches = self._benches()
        assert store_benchmarks(benches, db) == len(benches[0].benchmarks)

        rows = load_benchmarks(db)
        assert len(rows) == len(benches[0].benchmarks)
        assert set(rows["cse_id"]) == {"CSE-A"}
        depth = rows[rows.metric == "inv_depth_mean"].iloc[0]
        assert bool(depth["is_outlier"])
        members = eval(depth["peer_members_json"])  # noqa: S307 (test data)
        assert sorted(members) == ["CSE-A", "CSE-B", "CSE-C", "CSE-D"]
        assert depth["created_at"]

        assert len(load_benchmarks(db, outliers_only=True)) == \
            len(benches[0].outliers)
        assert len(load_benchmarks(db, period="2024-Q1")) == 0

    def test_restore_is_idempotent(self, tmp_path):
        db = tmp_path / "bench.db"
        benches = self._benches()
        first = store_benchmarks(benches, db)
        assert store_benchmarks(benches, db) == first
        assert len(load_benchmarks(db)) == first

    def test_load_before_any_store_is_empty_frame(self, tmp_path):
        empty = load_benchmarks(tmp_path / "nothing.db")
        assert isinstance(empty, pd.DataFrame) and empty.empty


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.fixture()
def cli_db(tmp_path):
    from src.analytics.profiler import store_profiles
    from src.storage.db import save_frames

    db = tmp_path / "cli.db"
    meta = pd.DataFrame([{"cse_id": cid, "sector": sec, "size_band": band}
                         for cid, (sec, band) in TELECOM_LARGE.items()])
    save_frames({"cse_metadata": meta}, db)
    store_profiles(TestBenchmarkCSE._profiles(TestBenchmarkCSE()), db)
    return db


class TestCLI:
    def test_run_single_cse_prints_group_and_flags(self, cli_db, capsys):
        from src.analytics.benchmarking import main

        rc = main(["run", "--cse-id", "CSE-A", "--db", str(cli_db)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Peer group 'Telecom_Large'" in out
        assert "← OUTLIER" in out

    def test_run_unknown_cse_returns_one(self, cli_db, capsys):
        from src.analytics.benchmarking import main

        rc = main(["run", "--cse-id", "NOPE", "--db", str(cli_db)])
        assert rc == 1
        assert "No profile" in capsys.readouterr().out

    def test_portfolio_mode_stores_rows(self, cli_db, capsys):
        from src.analytics.benchmarking import main

        rc = main(["run", "--db", str(cli_db)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Benchmarked 4 CSEs" in out
        assert len(load_benchmarks(cli_db)) > 0


# ---------------------------------------------------------------------------
# Full-portfolio integration (demo dataset; mirrors test_signal_engine)
# ---------------------------------------------------------------------------

DEMO_DIR = Path("data/samples/demo_dataset")


@pytest.fixture(scope="module")
def demo_benches():
    pytest.importorskip("pandas")
    if not DEMO_DIR.exists():
        pytest.skip("demo dataset not generated")

    from src.analytics.profiler import compute_all_profiles

    readers = {
        "alerts": {"parse_dates": ["timestamp", "closure_timestamp"]},
        "investigations": {"parse_dates": ["timestamp_open",
                                           "timestamp_close"]},
        "escalations": {"parse_dates": ["timestamp"]},
    }
    frames = {name: pd.read_csv(DEMO_DIR / f"{name}.csv", **kw)
              for name, kw in readers.items()}
    frames["cse_metadata"] = pd.read_csv(DEMO_DIR / "cse_metadata.csv")
    profiles = compute_all_profiles(frames)
    return build_all_benchmarks(profiles, frames["cse_metadata"])


class TestDemoPortfolio:
    def test_peer_groups_built_for_all_50_cses(self, demo_benches):
        assert len(demo_benches) == 50
        assert all(b.period == PERIOD_ALL for b in demo_benches)

    def test_every_cell_meets_min_group_size(self, demo_benches):
        unusable = [b for b in demo_benches if not b.usable]
        assert not unusable, f"groups below minimum: " \
                             f"{[b.group_label for b in unusable]}"

    def test_seeded_weak_cses_flag_on_expected_metrics(self, demo_benches):
        by_id = {b.cse_id: b for b in demo_benches}

        def flags(cse):
            return {b.metric for b in by_id[cse].outliers}

        assert "inv_depth_mean" in flags("CSE-042")
        assert flags("CSE-042") <= {
            "closure_velocity_median_h", "inv_depth_mean", "inv_depth_median",
            "inv_depth_p75", "inv_duration_mean_h", "inv_duration_p50_h",
            "inv_duration_p90_h",
        }
        assert "closure_velocity_median_h" in flags("CSE-017")
        assert "inv_depth_mean" in flags("CSE-031")

    def test_shallow_seeded_cses_rank_lowest_on_depth(self, demo_benches):
        def depth(b):
            return next(o.value for o in b.benchmarks
                        if o.metric == "inv_depth_mean")
        bottom4 = {b.cse_id for b in sorted(demo_benches, key=depth)[:4]}
        assert bottom4 == {"CSE-017", "CSE-061", "CSE-042", "CSE-031"}

    def test_baseline_tail_flags_stay_isolated(self, demo_benches):
        """~36 metrics x 50 CSEs guarantees some |z|>2.5 tails among
        baselines — acceptable in a descriptive table as long as no clean
        CSE lights up on both core process metrics at once."""
        shallow_or_fast = {"CSE-017", "CSE-061", "CSE-042", "CSE-031",
                           "CSE-055"}
        core = {"inv_depth_mean", "closure_velocity_median_h"}
        offenders = []
        for b in demo_benches:
            if b.cse_id in shallow_or_fast:
                continue
            hit = core & {o.metric for o in b.outliers}
            if len(hit) > 1:
                offenders.append((b.cse_id, sorted(hit)))
        assert not offenders, f"dual core flags on baselines: {offenders}"

    def test_labels_follow_metadata(self, demo_benches):
        by_id = {b.cse_id: b for b in demo_benches}
        assert by_id["CSE-042"].group_label == "Telecom_Large"
        assert by_id["CSE-089"].group_label == "Power_Energy_Large"
        assert by_id["CSE-019"].group_label == "Telecom_Small"

    def test_stored_rows_carry_peer_context(self, demo_benches, tmp_path):
        db = tmp_path / "demo.db"
        written = store_benchmarks(demo_benches, db)
        rows = load_benchmarks(db)
        assert len(rows) == written
        sample = rows[rows.cse_id == "CSE-042"].iloc[0]
        members = eval(sample["peer_members_json"])  # noqa: S307
        assert "CSE-042" in members and len(members) >= 4
        assert sample["z_score"] is not None or "zero variance" in \
            str(sample["note"])
