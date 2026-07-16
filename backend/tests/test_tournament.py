from types import SimpleNamespace

import pytest

from app.schemas import MatchRecord
from app.tournament import simulate_remaining

SOURCE_URL = "https://www.fifa.com/en/articles/knockout-stage-match-schedule-bracket"
VERIFIED_AT = "2026-07-14T10:59:23+08:00"


def _forecast_match(
    match_id: int,
    stage: str,
    home_team: str,
    away_team: str,
    **links: object,
) -> MatchRecord:
    return MatchRecord(
        match_id=match_id,
        stage=stage,
        kickoff_at=f"2026-07-{14 + match_id - 101:02d}T15:00:00-04:00",
        home_team=home_team,
        away_team=away_team,
        status="scheduled",
        result_kind="forecast",
        source_url=SOURCE_URL,
        verified_at=VERIFIED_AT,
        **links,
    )


def _tournament_data() -> SimpleNamespace:
    actual = MatchRecord(
        match_id=100,
        stage="quarterfinal",
        kickoff_at="2026-07-11T15:00:00-04:00",
        home_team="Actual A",
        away_team="Actual B",
        home_score=2,
        away_score=0,
        status="finished",
        result_kind="actual",
        next_match_id=101,
        source_url=SOURCE_URL,
        verified_at=VERIFIED_AT,
    )
    matches = [
        actual,
        _forecast_match(
            101,
            "semifinal",
            "A",
            "B",
            next_match_id=104,
            loser_next_match_id=103,
        ),
        _forecast_match(
            102,
            "semifinal",
            "C",
            "D",
            next_match_id=104,
            loser_next_match_id=103,
        ),
        _forecast_match(
            103,
            "third_place",
            "TBD",
            "TBD",
            home_source_match_id=101,
            home_source_outcome="loser",
            away_source_match_id=102,
            away_source_outcome="loser",
        ),
        _forecast_match(
            104,
            "final",
            "TBD",
            "TBD",
            home_source_match_id=101,
            home_source_outcome="winner",
            away_source_match_id=102,
            away_source_outcome="winner",
        ),
    ]
    return SimpleNamespace(matches=matches)


def test_simulation_is_reproducible() -> None:
    data = _tournament_data()

    def predictor(home_team: str, away_team: str) -> SimpleNamespace:
        return SimpleNamespace(home_advance=0.6)

    first = simulate_remaining(data, predictor, iterations=1000, seed=20260713)
    second = simulate_remaining(data, predictor, iterations=1000, seed=20260713)

    assert first == second


def test_simulation_probabilities_are_normalized() -> None:
    result = simulate_remaining(
        _tournament_data(),
        lambda home, away: SimpleNamespace(home_advance=0.5),
        iterations=1000,
        seed=20260713,
    )

    assert sum(result.champion_probabilities.values()) == pytest.approx(1.0)
    assert sum(result.final_probabilities.values()) == pytest.approx(2.0)
    assert set(result.champion_probabilities) == {"A", "B", "C", "D"}


def test_simulation_never_predicts_actual_matches() -> None:
    predicted_pairs: set[tuple[str, str]] = set()

    def predictor(home_team: str, away_team: str) -> SimpleNamespace:
        predicted_pairs.add((home_team, away_team))
        return SimpleNamespace(home_advance=0.5)

    simulate_remaining(_tournament_data(), predictor, iterations=10, seed=20260713)

    assert ("Actual A", "Actual B") not in predicted_pairs
