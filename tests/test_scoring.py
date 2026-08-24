"""Tests for Phase 8 supervisory attention scoring."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.analytics.finding import Finding
from src.analytics.scoring import (
    DEFAULT_SCORING,
    SEVERITY_POINTS,
    AttentionScore,
    compute_attention_scores,
    load_scores,
    main,
    rank_scores,
    store_scores,
)


def _finding(cse_id="CSE-T01", signal_type="superficial_closure",
             category="execution_gap", severity="HIGH", confidence=0.9):
    return Finding(
        finding_id=f"{cse_id}:{signal_type}", cse_id=cse_id,
        signal_type=signal_type, signal_category=category, period="ALL",
        severity=severity, confidence=confidence, evidence={"k": 1},
        detection_logic="test fixture",
    )


# ---------------------------------------------------------------------------
# Severity mapping and config
# ---------------------------------------------------------------------------


class TestConfigAndMapping:
    def test_severity_points_match_spec(self):
        assert SEVERITY_POINTS == {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}

    def test_unknown_severity_scores_as_low(self):
        scores = compute_attention_scores(
            [_finding(severity="WEIRD", confidence=0.5)])
        assert scores[0].avg_severity == pytest.approx(0.3)

    def test_defaults_match_spec_formula(self):
        assert DEFAULT_SCORING == {
            "confidence_weight": 0.4, "severity_weight": 0.3,
            "breadth_weight": 0.3, "signal_count_target": 10,
            "max_diversity_categories": 4, "scale": 100,
        }

    def test_thresholds_file_overrides_apply(self):
        from src.analytics.finding import load_thresholds

        cfg_section = load_thresholds().get("scoring")
        assert cfg_section["confidence_weight"] == \
            DEFAULT_SCORING["confidence_weight"]


# ---------------------------------------------------------------------------
# Component math
# ---------------------------------------------------------------------------


class TestComponentMath:
    def test_exact_hand_computed_priority(self):
        # avg_conf 0.8 -> 0.32; avg_sev (1.0+0.6)/2=0.8 -> 0.24;
        # breadth: count 2/10=0.2, diversity 2 cats/4=0.5 -> 0.3*0.35=0.105
        findings = [
            _finding(signal_type="s1", category="execution_gap",
                     severity="HIGH", confidence=0.9),
            _finding(signal_type="s2", category="negative_space",
                     severity="MEDIUM", confidence=0.7),
        ]
        s = compute_attention_scores(findings)[0]
        assert s.priority == pytest.approx(66.5)
        assert s.avg_confidence == pytest.approx(0.8)
        assert s.avg_severity == pytest.approx(0.8)
        assert s.signal_count_score == pytest.approx(0.2)
        assert s.diversity_score == pytest.approx(0.5)

    def test_components_sum_back_to_priority(self):
        s = compute_attention_scores([
            _finding(), _finding(category="negative_space"),
            _finding(signal_type="x", category="behavioral_anomaly",
                     severity="LOW", confidence=0.4),
        ])[0]
        total = (s.components["confidence_component"]
                 + s.components["severity_component"]
                 + s.components["breadth_component"]) * \
            DEFAULT_SCORING["scale"]
        assert s.priority == pytest.approx(round(total, 1))

    def test_signal_count_saturates_at_target(self):
        findings = [_finding(signal_type=f"s{i}") for i in range(12)]
        s = compute_attention_scores(findings)[0]
        assert s.signal_count_score == 1.0
        assert s.n_signal_types == 12

    def test_diversity_caps_at_one(self):
        cats = ["a", "b", "c", "d", "e"]
        findings = [_finding(signal_type=f"s{i}", category=c)
                    for i, c in enumerate(cats)]
        s = compute_attention_scores(findings)[0]
        assert s.diversity_score == 1.0
        assert s.n_categories == 5

    def test_weights_are_configurable(self):
        findings = [_finding(), _finding(signal_type="s2",
                                         category="negative_space")]
        base = compute_attention_scores(findings)[0].priority
        sev_only = {"scoring": {"confidence_weight": 0.0,
                                "severity_weight": 1.0,
                                "breadth_weight": 0.0}}
        shifted = compute_attention_scores(findings,
                                           thresholds=sev_only)[0]
        assert shifted.priority == pytest.approx(
            round(shifted.avg_severity * 100, 1))
        assert shifted.priority != base

    def test_scale_is_configurable(self):
        s = compute_attention_scores([_finding()],
                                     thresholds={"scoring": {"scale": 10}})[0]
        assert 0 <= s.priority <= 10

    def test_zero_finding_cses_listed_with_zero(self):
        scores = compute_attention_scores([], all_cse_ids=["CSE-A", "CSE-B"])
        assert [s.cse_id for s in scores] == ["CSE-A", "CSE-B"]
        assert all(s.priority == 0.0 for s in scores)

    def test_empty_input_yields_nothing_without_ids(self):
        assert compute_attention_scores([]) == []


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


class TestRanking:
    def test_sorted_descending_and_deterministic(self):
        hi = _finding("CSE-HI")
        lo = _finding("CSE-B-LO", severity="LOW", confidence=0.3)
        lo2 = _finding("CSE-A-LO", severity="LOW", confidence=0.3)
        ranked = rank_scores(compute_attention_scores([lo, lo2, hi]))
        assert [s.cse_id for s in ranked] == ["CSE-HI", "CSE-A-LO",
                                              "CSE-B-LO"]

    def test_tie_broken_by_more_findings_first(self):
        single = [_finding("CSE-ONE")]
        double = [_finding("CSE-TWO"), _finding("CSE-TWO:x",
                                                category="negative_space",
                                                severity="LOW",
                                                confidence=0.9)]
        # Both end near each other; the 2-finding CSE must outrank on ties.
        a = compute_attention_scores(single)[0]
        b = compute_attention_scores(double)[0]
        ranked = rank_scores([a, b])
        assert ranked[0].n_findings >= ranked[1].n_findings or \
            ranked[0].priority > ranked[1].priority


# ---------------------------------------------------------------------------
# Transparency
# ---------------------------------------------------------------------------


class TestTransparency:
    def test_explanation_exposes_weights_and_parts(self):
        s = compute_attention_scores([_finding()])[0]
        text = s.explanation()
        assert s.cse_id in text
        assert "w=0.40" in text and "w=0.30" in text
        assert f"{s.priority:.1f}" in text

    def test_framing_is_prioritization_not_risk(self):
        from src.analytics.scoring import _DISCLAIMER

        assert "NOT a risk or compliance score" in _DISCLAIMER
        assert "does not mean safe" in _DISCLAIMER


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestStorage:
    def test_roundtrip_and_replace(self, tmp_path):
        db = tmp_path / "scores.db"
        scores = compute_attention_scores(
            [_finding("CSE-A"), _finding("CSE-B", severity="LOW",
                                         confidence=0.4)],
            all_cse_ids=["CSE-C"])
        assert store_scores(scores, db) == 3

        rows = load_scores(db)
        assert len(rows) == 3
        top = rows.iloc[0]
        assert top["cse_id"] == "CSE-A"
        assert top["priority"] == pytest.approx(scores[0].priority)
        assert "avg_confidence" in eval(top["components_json"])  # noqa: S307

        # Re-store replaces wholesale (run-scoped ranking).
        only_one = compute_attention_scores([_finding("CSE-Z")])
        store_scores(only_one, db)
        rows = load_scores(db)
        assert len(rows) == 1 and rows.iloc[0]["cse_id"] == "CSE-Z"

    def test_load_missing_table_returns_empty(self, tmp_path):
        assert load_scores(tmp_path / "none.db").empty


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@pytest.fixture()
def cli_db(tmp_path):
    from src.analytics.signal_engine import store_findings
    from src.storage.db import save_frames

    db = tmp_path / "cli.db"
    meta = pd.DataFrame([
        {"cse_id": "CSE-A", "sector": "Telecom", "size_band": "Large"},
        {"cse_id": "CSE-B", "sector": "Telecom", "size_band": "Large"},
    ])
    save_frames({"cse_metadata": meta}, db)
    store_findings([_finding("CSE-A"),
                    _finding("CSE-A", signal_type="t2",
                             category="negative_space")], db)
    return db


class TestCLI:
    def test_rank_prints_disclaimer_and_lines(self, cli_db, capsys):
        rc = main(["rank", "--db", str(cli_db)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "NOT a risk or compliance score" in out
        assert "CSE-A:" in out
        assert "(2 findings," in out
        assert "attention_scores" in out          # storage confirmation
        assert not load_scores(cli_db).empty

    def test_top_flag_limits_output(self, cli_db, capsys):
        rc = main(["rank", "--db", str(cli_db), "--top", "1"])
        out = capsys.readouterr().out
        assert rc == 0
        data_lines = [ln for ln in out.splitlines()
                      if ln.strip().startswith("CSE-")]
        assert len(data_lines) == 1

    def test_rank_without_findings_table_still_works(self, tmp_path, capsys):
        from src.storage.db import save_frames

        db = tmp_path / "bare.db"
        save_frames({"cse_metadata": pd.DataFrame(
            [{"cse_id": "X1", "sector": "Telecom", "size_band": "Large"}])
        }, db)
        rc = main(["rank", "--db", str(db)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "X1: 0.0" in out


# ---------------------------------------------------------------------------
# Full-portfolio integration (demo dataset)
# ---------------------------------------------------------------------------

DEMO_DIR = Path("data/samples/demo_dataset")
SEEDED = {"CSE-042", "CSE-017", "CSE-089", "CSE-031",
          "CSE-055", "CSE-073", "CSE-019", "CSE-061"}


@pytest.fixture(scope="module")
def demo_ranking():
    if not DEMO_DIR.exists():
        pytest.skip("demo dataset not generated")

    from src.analytics.finding import load_thresholds
    from src.analytics.profiler import compute_all_profiles
    from src.analytics.signal_engine import build_contexts, run_context

    readers = {
        "alerts": {"parse_dates": ["timestamp", "closure_timestamp"]},
        "investigations": {"parse_dates": ["timestamp_open",
                                           "timestamp_close"]},
        "escalations": {"parse_dates": ["timestamp"]},
    }
    frames = {name: pd.read_csv(DEMO_DIR / f"{name}.csv", **kw)
              for name, kw in readers.items()}
    metadata = pd.read_csv(DEMO_DIR / "cse_metadata.csv")
    frames["cse_metadata"] = metadata
    profiles = compute_all_profiles(frames)
    findings = []
    for ctx in build_contexts(frames, profiles,
                              thresholds=load_thresholds()).values():
        findings.extend(run_context(ctx))
    scores = compute_attention_scores(findings,
                                      all_cse_ids=metadata["cse_id"],
                                      thresholds=load_thresholds())
    return rank_scores(scores)


class TestDemoRanking:
    def test_all_50_cses_scored(self, demo_ranking):
        assert len(demo_ranking) == 50

    def test_priorities_within_bounds(self, demo_ranking):
        assert all(0.0 <= s.priority <= 100.0 for s in demo_ranking)

    def test_seeded_weaknesses_rank_in_top_10(self, demo_ranking):
        top10 = {s.cse_id for s in demo_ranking[:10]}
        assert SEEDED <= top10, f"missing from top 10: {SEEDED - top10}"

    def test_seeded_mean_clearly_above_baseline(self, demo_ranking):
        seeded = [s.priority for s in demo_ranking if s.cse_id in SEEDED]
        baseline = [s.priority for s in demo_ranking
                    if s.cse_id not in SEEDED]
        assert sum(seeded) / len(seeded) > sum(baseline) / len(baseline) + 20
