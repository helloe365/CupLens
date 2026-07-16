import json
import math
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.elo import decay_weight, expected_score
from app.poisson import (
    advancement_probability,
    form_strength,
    outcome_probabilities,
    predict_match,
    score_matrix,
)


def test_score_matrix_is_normalized_over_zero_to_seven_goals() -> None:
    matrix = score_matrix(1.4, 1.1, max_goals=7)

    assert matrix.shape == (8, 8)
    assert matrix.sum() == pytest.approx(1.0, abs=1e-12)
    assert np.all((0.0 <= matrix) & (matrix <= 1.0))


def test_outcome_probabilities_are_normalized() -> None:
    result = outcome_probabilities(1.4, 1.1, max_goals=7)

    assert result.home_win + result.draw + result.away_win == pytest.approx(
        1.0,
        abs=1e-12,
    )
    assert all(
        0.0 <= value <= 1.0
        for value in [result.home_win, result.draw, result.away_win]
    )


def test_outcome_probabilities_returns_top_three_scores_in_order() -> None:
    result = outcome_probabilities(1.4, 1.1, max_goals=7)

    assert len(result.top_scores) == 3
    assert result.top_scores[0].home_score == 1
    assert result.top_scores[0].away_score == 1
    probabilities = [score.probability for score in result.top_scores]
    assert probabilities == sorted(probabilities, reverse=True)


def test_form_strength_uses_weighting_and_five_game_shrinkage() -> None:
    matches = pd.DataFrame(
        [
            {
                "date": "2025-12-31",
                "home_team": "A",
                "away_team": f"B{index}",
                "home_score": 2,
                "away_score": 1,
                "tournament": "Friendly",
            }
            for index in range(20)
        ]
    )
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    weight = decay_weight(1)

    strength = form_strength(matches, "A", cutoff, global_mean=1.5)

    expected_attack = ((40 * weight + 5 * 1.5) / (20 * weight + 5)) / 1.5
    expected_defense = ((20 * weight + 5 * 1.5) / (20 * weight + 5)) / 1.5
    assert strength.attack == pytest.approx(expected_attack)
    assert strength.defense == pytest.approx(expected_defense)
    assert strength.matches_used == 20


def test_advancement_probability_uses_elo_only_for_draws() -> None:
    probability = advancement_probability(
        home_win=0.4,
        draw=0.3,
        rating_home=1600.0,
        rating_away=1500.0,
    )

    assert probability == pytest.approx(
        0.4 + 0.3 * expected_score(1600.0, 1500.0)
    )


def test_predict_match_ignores_matches_at_or_after_cutoff() -> None:
    rows = [
        {
            "date": "2026-01-01",
            "home_team": "A",
            "away_team": "B",
            "home_score": 2,
            "away_score": 0,
            "tournament": "Friendly",
        },
        {
            "date": "2026-07-13",
            "home_team": "B",
            "away_team": "A",
            "home_score": 99,
            "away_score": 0,
            "tournament": "Friendly",
        },
        {
            "date": "2026-08-01",
            "home_team": "B",
            "away_team": "A",
            "home_score": 99,
            "away_score": 0,
            "tournament": "Friendly",
        },
    ]
    cutoff = datetime(2026, 7, 13, tzinfo=UTC)
    matches = pd.DataFrame(rows)
    pre_cutoff_only = pd.DataFrame(rows[:1])
    ratings = {"A": 1550.0, "B": 1450.0}

    actual = predict_match(
        "A",
        "B",
        cutoff,
        matches=matches,
        elo_ratings=ratings,
    )
    expected = predict_match(
        "A",
        "B",
        cutoff,
        matches=pre_cutoff_only,
        elo_ratings=ratings,
    )

    assert actual == expected


def test_predict_match_clamps_xg_and_normalizes_probabilities() -> None:
    matches = pd.DataFrame(
        [
            {
                "date": "2025-01-01",
                "home_team": "A",
                "away_team": "B",
                "home_score": 100,
                "away_score": 0,
                "tournament": "Friendly",
            }
        ]
    )

    prediction = predict_match(
        "A",
        "B",
        datetime(2026, 1, 1, tzinfo=UTC),
        matches=matches,
        elo_ratings={"A": 2500.0, "B": 500.0},
    )

    assert 0.2 <= prediction.home_xg <= 3.5
    assert 0.2 <= prediction.away_xg <= 3.5
    assert prediction.home_win + prediction.draw + prediction.away_win == pytest.approx(
        1.0,
        abs=1e-12,
    )
    assert 0.0 <= prediction.home_advance <= 1.0


def test_backtest_script_writes_finite_time_split_metrics(tmp_path: Path) -> None:
    data_path = tmp_path / "historical.csv"
    pd.DataFrame(
        [
            {
                "date": "2017-01-01",
                "home_team": "A",
                "away_team": "B",
                "home_score": 1,
                "away_score": 0,
                "tournament": "Friendly",
            },
            {
                "date": "2018-06-14",
                "home_team": "A",
                "away_team": "B",
                "home_score": 2,
                "away_score": 1,
                "tournament": "FIFA World Cup",
            },
            {
                "date": "2021-01-01",
                "home_team": "B",
                "away_team": "A",
                "home_score": 1,
                "away_score": 1,
                "tournament": "Friendly",
            },
            {
                "date": "2022-11-20",
                "home_team": "B",
                "away_team": "A",
                "home_score": 0,
                "away_score": 1,
                "tournament": "FIFA World Cup",
            },
        ]
    ).to_csv(data_path, index=False)
    output_path = tmp_path / "backtest.json"
    script = Path(__file__).resolve().parents[2] / "scripts/backtest.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--test-years",
            "2018",
            "2022",
            "--data",
            str(data_path),
            "--output",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["feature_cutoff_rule"] == "date < tournament_start"
    assert [item["matches"] for item in payload["results"]] == [1, 1]
    for item in payload["results"]:
        assert item["feature_cutoff_at"] < item["first_test_match_at"]
        assert all(
            math.isfinite(item[key])
            for key in ["accuracy", "brier_score", "log_loss"]
        )
