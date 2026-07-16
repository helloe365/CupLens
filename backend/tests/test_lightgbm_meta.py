import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.lightgbm_meta import (
    FEATURE_NAMES,
    MetaRow,
    blend_probabilities,
    build_world_cup_rows,
    fit_predict_probabilities,
    run_meta_backtest,
    select_blend_weight,
    validate_feature_cutoffs,
)


APPROVED_FEATURES = {
    "elo_diff",
    "poisson_home_win",
    "poisson_draw",
    "poisson_away_win",
    "attack_diff",
    "defense_diff",
    "recent_five_form_diff",
    "neutral",
    "rest_days_diff",
}
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _row(index: int, actual_class: int) -> MetaRow:
    match_date = datetime(2010, 6, 1, tzinfo=UTC) + timedelta(days=index)
    features = [0.0] * len(FEATURE_NAMES)
    features[actual_class] = 1.0
    return MetaRow(
        match_date=match_date,
        feature_cutoff=match_date - timedelta(microseconds=1),
        features=tuple(features),
        baseline_probabilities=(0.34, 0.33, 0.33),
        actual_class=actual_class,
    )


def test_feature_names_are_limited_to_approved_pre_match_inputs() -> None:
    assert set(FEATURE_NAMES) == APPROVED_FEATURES


def test_every_feature_cutoff_is_strictly_before_match_date() -> None:
    valid = [_row(0, 0), _row(1, 1)]
    validate_feature_cutoffs(valid)

    invalid = MetaRow(
        match_date=valid[0].match_date,
        feature_cutoff=valid[0].match_date,
        features=valid[0].features,
        baseline_probabilities=valid[0].baseline_probabilities,
        actual_class=valid[0].actual_class,
    )
    with pytest.raises(ValueError, match="feature_cutoff"):
        validate_feature_cutoffs([invalid])


def test_lightgbm_predict_proba_rows_sum_to_one() -> None:
    pytest.importorskip("lightgbm")
    training = [_row(index, index % 3) for index in range(60)]
    prediction = [_row(100 + index, index % 3) for index in range(6)]

    probabilities = fit_predict_probabilities(training, prediction, seed=20260715)

    assert probabilities.shape == (6, 3)
    assert np.all((0.0 <= probabilities) & (probabilities <= 1.0))
    assert np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-12)


def test_blend_weight_is_selected_only_from_supplied_validation_rows() -> None:
    baseline = np.asarray(
        [
            [0.34, 0.33, 0.33],
            [0.34, 0.33, 0.33],
            [0.34, 0.33, 0.33],
        ]
    )
    meta = np.asarray(
        [
            [0.90, 0.05, 0.05],
            [0.05, 0.90, 0.05],
            [0.05, 0.05, 0.90],
        ]
    )
    actual_classes = np.asarray([0, 1, 2])

    selected = select_blend_weight(
        baseline,
        meta,
        actual_classes,
        candidates=(0.0, 0.5, 1.0),
    )
    blended = blend_probabilities(baseline, meta, selected)

    assert selected == 1.0
    assert np.allclose(blended.sum(axis=1), 1.0, atol=1e-12)


def _rolling_matches(*, reverse_test_results: bool = False) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for friendly_year in (2001, 2005):
        for month, (home, away, home_score, away_score) in enumerate(
            [
                ("A", "B", 2, 1),
                ("B", "C", 1, 1),
                ("C", "A", 0, 1),
            ],
            start=1,
        ):
            rows.append(
                {
                    "date": f"{friendly_year}-{month:02d}-01",
                    "home_team": home,
                    "away_team": away,
                    "home_score": home_score,
                    "away_score": away_score,
                    "tournament": "Friendly",
                    "neutral": False,
                }
            )

    patterns = [("A", "B", 1, 0), ("B", "C", 1, 1), ("C", "A", 0, 1)]
    for year in (2002, 2006, 2010, 2014, 2018):
        for index in range(12):
            home, away, home_score, away_score = patterns[index % 3]
            if year == 2018 and reverse_test_results:
                home_score, away_score = away_score, home_score
            rows.append(
                {
                    "date": f"{year}-06-{10 + index:02d}",
                    "home_team": home,
                    "away_team": away,
                    "home_score": home_score,
                    "away_score": away_score,
                    "tournament": "FIFA World Cup",
                    "neutral": True,
                }
            )
    return pd.DataFrame(rows)


def test_world_cup_rows_freeze_features_before_tournament() -> None:
    rows = build_world_cup_rows(_rolling_matches(), 2014)

    assert rows
    validate_feature_cutoffs(rows)
    assert len({row.feature_cutoff for row in rows}) == 1
    assert rows[0].feature_cutoff < min(row.match_date for row in rows)


def test_dixon_coles_rows_feed_corrected_probabilities_to_meta_model() -> None:
    matches = _rolling_matches()
    baseline = build_world_cup_rows(matches, 2014)
    combined = build_world_cup_rows(
        matches,
        2014,
        probability_variant="dixon-coles",
    )

    validate_feature_cutoffs(combined)
    for row in combined:
        assert row.features[1:4] == pytest.approx(row.baseline_probabilities)
        assert sum(row.baseline_probabilities) == pytest.approx(1.0)
    baseline_values = np.asarray(
        [row.baseline_probabilities for row in baseline],
        dtype=float,
    )
    combined_values = np.asarray(
        [row.baseline_probabilities for row in combined],
        dtype=float,
    )
    assert not np.allclose(baseline_values, combined_values, atol=1e-12)


def test_rolling_backtest_does_not_select_blend_on_test_results() -> None:
    pytest.importorskip("lightgbm")
    original = run_meta_backtest(_rolling_matches(), 2018, seed=20260715)
    reversed_results = run_meta_backtest(
        _rolling_matches(reverse_test_results=True),
        2018,
        seed=20260715,
    )

    assert original.training_years == (2006, 2010)
    assert original.validation_year == 2014
    assert original.blend_weight == reversed_results.blend_weight
    assert original.validation_last_match_at < original.test_feature_cutoff
    assert np.allclose(original.probabilities.sum(axis=1), 1.0, atol=1e-12)


def test_combined_backtest_selects_rho_and_blend_without_test_results() -> None:
    pytest.importorskip("lightgbm")
    original = run_meta_backtest(
        _rolling_matches(),
        2018,
        seed=20260715,
        probability_variant="dixon-coles",
    )
    reversed_results = run_meta_backtest(
        _rolling_matches(reverse_test_results=True),
        2018,
        seed=20260715,
        probability_variant="dixon-coles",
    )

    original_rho = [
        (item.target_year, item.rho, item.training_year)
        for item in original.rho_selections
    ]
    reversed_rho = [
        (item.target_year, item.rho, item.training_year)
        for item in reversed_results.rho_selections
    ]
    assert original.blend_weight == reversed_results.blend_weight
    assert original_rho == reversed_rho
    assert [item.target_year for item in original.rho_selections] == [
        2006,
        2010,
        2014,
        2018,
    ]
    assert all(
        item.training_year < item.target_year
        for item in original.rho_selections
    )
    assert original.validation_last_match_at < original.test_feature_cutoff
    assert np.all(np.isfinite(original.probabilities))
    assert np.all((0.0 <= original.probabilities) & (original.probabilities <= 1.0))
    assert np.allclose(original.probabilities.sum(axis=1), 1.0, atol=1e-12)


def test_lightgbm_meta_cli_runs_without_output_file(tmp_path: Path) -> None:
    pytest.importorskip("lightgbm")
    data_path = tmp_path / "historical.csv"
    _rolling_matches().to_csv(data_path, index=False)

    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts/backtest.py"),
            "--variant",
            "lightgbm-meta",
            "--test-years",
            "2018",
            "--data",
            str(data_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "BLEND_WEIGHT=" in result.stdout
    assert "VALIDATION_YEAR=2014" in result.stdout


def test_combined_meta_cli_reports_blend_and_rho_provenance(
    tmp_path: Path,
) -> None:
    pytest.importorskip("lightgbm")
    data_path = tmp_path / "historical.csv"
    _rolling_matches().to_csv(data_path, index=False)

    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts/backtest.py"),
            "--variant",
            "dixon-coles-lightgbm-meta",
            "--test-years",
            "2018",
            "--data",
            str(data_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "BLEND_WEIGHT=" in result.stdout
    assert "VALIDATION_YEAR=2014" in result.stdout
    assert "RHO_YEARS=2006,2010,2014,2018" in result.stdout
    assert list(tmp_path.iterdir()) == [data_path]
