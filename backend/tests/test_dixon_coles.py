import math
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app import dixon_coles
from app.dixon_coles import (
    RhoObservation,
    adjust_score_matrix,
    select_rho,
    tau,
)
from app.poisson import score_matrix

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backtest import backtest_year  # noqa: E402


@pytest.mark.parametrize(
    ("home_score", "away_score", "expected"),
    [
        (0, 0, 1.096),
        (1, 0, 0.92),
        (0, 1, 0.88),
        (1, 1, 1.1),
        (2, 1, 1.0),
        (1, 2, 1.0),
    ],
)
def test_tau_only_corrects_low_scores(
    home_score: int,
    away_score: int,
    expected: float,
) -> None:
    assert tau(home_score, away_score, 1.2, 0.8, -0.1) == pytest.approx(
        expected
    )


def test_adjust_score_matrix_is_normalized_and_zero_rho_rolls_back() -> None:
    baseline = score_matrix(1.2, 0.8, max_goals=7)

    adjusted = adjust_score_matrix(baseline, 1.2, 0.8, -0.1)
    rolled_back = adjust_score_matrix(baseline, 1.2, 0.8, 0.0)

    assert adjusted.sum() == pytest.approx(1.0, abs=1e-12)
    assert np.all(adjusted >= 0.0)
    assert np.array_equal(rolled_back, baseline)


def test_select_rho_ignores_observations_at_or_after_cutoff() -> None:
    cutoff = datetime(2018, 6, 14, tzinfo=UTC)
    training = [
        RhoObservation(
            played_at=datetime(2014, 6, 12, tzinfo=UTC),
            lambda_home=1.0,
            lambda_away=1.0,
            home_score=0,
            away_score=0,
        )
        for _ in range(20)
    ]
    future = [
        RhoObservation(
            played_at=datetime(2018, 6, 14, tzinfo=UTC),
            lambda_home=1.0,
            lambda_away=1.0,
            home_score=1,
            away_score=0,
        )
        for _ in range(100)
    ]

    selected_without_future = select_rho(
        training,
        cutoff_at=cutoff,
        candidates=(-0.1, 0.0, 0.1),
    )
    selected_with_future = select_rho(
        training + future,
        cutoff_at=cutoff,
        candidates=(-0.1, 0.0, 0.1),
    )

    assert selected_without_future == pytest.approx(-0.1)
    assert selected_with_future == selected_without_future


def _backtest_matches(*, reverse_test_results: bool = False) -> pd.DataFrame:
    rows = [
        {
            "date": "2013-01-01",
            "home_team": "A",
            "away_team": "B",
            "home_score": 1,
            "away_score": 1,
            "tournament": "Friendly",
        },
        {
            "date": "2013-02-01",
            "home_team": "B",
            "away_team": "A",
            "home_score": 1,
            "away_score": 1,
            "tournament": "Friendly",
        },
    ]
    rows.extend(
        {
            "date": "2014-06-12",
            "home_team": "A",
            "away_team": "B",
            "home_score": 0,
            "away_score": 0,
            "tournament": "FIFA World Cup",
        }
        for _ in range(20)
    )
    rows.extend(
        {
            "date": "2018-06-14",
            "home_team": "A",
            "away_team": "B",
            "home_score": 0 if reverse_test_results else 1,
            "away_score": 1 if reverse_test_results else 0,
            "tournament": "FIFA World Cup",
        }
        for _ in range(20)
    )
    return pd.DataFrame(rows)


def test_shared_tournament_rho_selector_never_reads_target_results() -> None:
    original = dixon_coles.select_tournament_rho(_backtest_matches(), 2018)
    reversed_results = dixon_coles.select_tournament_rho(
        _backtest_matches(reverse_test_results=True),
        2018,
    )

    assert original.rho == reversed_results.rho
    assert original.training_year == 2014
    assert original.training_last_match_at < datetime(2018, 6, 14, tzinfo=UTC)


def test_backtest_rho_is_selected_without_test_tournament_results() -> None:
    original = backtest_year(
        _backtest_matches(),
        2018,
        variant="dixon-coles",
    )
    reversed_results = backtest_year(
        _backtest_matches(reverse_test_results=True),
        2018,
        variant="dixon-coles",
    )

    assert original["rho"] == reversed_results["rho"]
    assert original["rho_training_year"] == 2014
    assert original["rho_training_last_match_at"] < original["first_test_match_at"]
    assert all(
        math.isfinite(float(original[key]))
        for key in ["accuracy", "brier_score", "log_loss", "rho"]
    )


def test_dixon_coles_cli_does_not_require_output(tmp_path: Path) -> None:
    data_path = tmp_path / "historical.csv"
    _backtest_matches().to_csv(data_path, index=False)

    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts/backtest.py"),
            "--variant",
            "dixon-coles",
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
    assert "RHO=" in result.stdout
