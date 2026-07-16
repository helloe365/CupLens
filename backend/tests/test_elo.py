import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from app.elo import decay_weight, expected_score, fit_elo, tournament_importance


def test_equal_elo_has_half_expectation() -> None:
    assert expected_score(1500.0, 1500.0) == 0.5


def test_decay_weight_has_three_year_half_life() -> None:
    assert decay_weight(365 * 3) == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("tournament", "expected"),
    [
        ("Friendly", 0.5),
        ("FIFA World Cup qualification", 1.0),
        ("UEFA Euro", 1.25),
        ("Gold Cup", 1.25),
        ("FIFA World Cup", 1.5),
    ],
)
def test_tournament_importance_uses_fixed_weights(
    tournament: str,
    expected: float,
) -> None:
    assert tournament_importance(tournament) == expected


def test_fit_elo_ignores_matches_at_or_after_cutoff() -> None:
    matches = pd.DataFrame(
        [
            {
                "date": "2026-01-01",
                "home_team": "A",
                "away_team": "B",
                "home_score": 1,
                "away_score": 0,
                "tournament": "Friendly",
            },
            {
                "date": "2026-07-13",
                "home_team": "B",
                "away_team": "A",
                "home_score": 9,
                "away_score": 0,
                "tournament": "Friendly",
            },
            {
                "date": "2026-08-01",
                "home_team": "B",
                "away_team": "A",
                "home_score": 9,
                "away_score": 0,
                "tournament": "Friendly",
            },
        ]
    )

    ratings = fit_elo(matches, datetime(2026, 7, 13, tzinfo=UTC))

    assert ratings["A"] > ratings["B"]


def test_fit_elo_ignores_pre_cutoff_rows_without_scores() -> None:
    completed = {
        "date": "2026-01-01",
        "home_team": "A",
        "away_team": "B",
        "home_score": 1,
        "away_score": 0,
        "tournament": "Friendly",
    }
    scheduled = {
        "date": "2026-07-14",
        "home_team": "France",
        "away_team": "Spain",
        "home_score": None,
        "away_score": None,
        "tournament": "FIFA World Cup",
    }
    cutoff = datetime(2026, 7, 14, 3, 25, 41, tzinfo=UTC)

    ratings = fit_elo(pd.DataFrame([completed, scheduled]), cutoff)

    assert ratings == fit_elo(pd.DataFrame([completed]), cutoff)


def test_fit_elo_sorts_matches_chronologically() -> None:
    rows = [
        {
            "date": "2024-01-01",
            "home_team": "A",
            "away_team": "B",
            "home_score": 1,
            "away_score": 0,
            "tournament": "FIFA World Cup",
        },
        {
            "date": "2025-01-01",
            "home_team": "B",
            "away_team": "A",
            "home_score": 1,
            "away_score": 0,
            "tournament": "Friendly",
        },
    ]
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)

    chronological = fit_elo(pd.DataFrame(rows), cutoff)
    reversed_input = fit_elo(pd.DataFrame(list(reversed(rows))), cutoff)

    assert reversed_input == chronological


def test_fit_elo_is_deterministic_for_same_input_and_cutoff() -> None:
    matches = pd.DataFrame(
        [
            {
                "date": "2025-06-01",
                "home_team": "A",
                "away_team": "B",
                "home_score": 2,
                "away_score": 2,
                "tournament": "UEFA Euro",
            }
        ]
    )
    cutoff = datetime(2026, 7, 13, tzinfo=UTC)

    assert fit_elo(matches, cutoff) == fit_elo(matches, cutoff)


def _write_historical_source(root: Path, expected_hash: str) -> None:
    sources_path = root / "data/sources.json"
    sources_path.parent.mkdir(parents=True, exist_ok=True)
    sources_path.write_text(
        json.dumps(
            [
                {
                    "source_id": "historical-international-results",
                    "role": "secondary",
                    "url": (
                        "https://raw.githubusercontent.com/martj42/"
                        "international_results/master/results.csv"
                    ),
                    "retrieved_at": "2026-07-14T00:00:00+00:00",
                    "verified_at": "2026-07-14T00:00:00+00:00",
                    "file_sha256": {
                        "data/raw/historical_matches.csv": expected_hash
                    },
                }
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_fetch_historical_skips_matching_existing_file(tmp_path: Path) -> None:
    content = b"date,home_team,away_team,home_score,away_score,tournament\n"
    historical_path = tmp_path / "data/raw/historical_matches.csv"
    historical_path.parent.mkdir(parents=True)
    historical_path.write_bytes(content)
    _write_historical_source(tmp_path, hashlib.sha256(content).hexdigest())
    script = Path(__file__).resolve().parents[2] / "scripts/fetch_historical.py"

    result = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "HISTORICAL DATA ALREADY VERIFIED" in result.stdout


def test_fetch_historical_rejects_existing_hash_conflict(tmp_path: Path) -> None:
    historical_path = tmp_path / "data/raw/historical_matches.csv"
    historical_path.parent.mkdir(parents=True)
    historical_path.write_text("changed\n", encoding="utf-8")
    _write_historical_source(tmp_path, "0" * 64)
    script = Path(__file__).resolve().parents[2] / "scripts/fetch_historical.py"

    result = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "SHA-256 conflict" in result.stderr
