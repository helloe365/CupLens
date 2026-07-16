import math
from datetime import datetime

import pandas as pd

INITIAL_RATING = 1500.0
BASE_K = 20.0
HALF_LIFE_YEARS = 3.0

CONTINENTAL_FINALS = {
    "AFC Asian Cup",
    "African Cup of Nations",
    "Copa América",
    "CONCACAF Championship",
    "Oceania Nations Cup",
    "Gold Cup",
    "UEFA Euro",
}


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def decay_weight(age_days: int, half_life_years: float = HALF_LIFE_YEARS) -> float:
    return math.exp(
        -math.log(2.0) * age_days / (365.0 * half_life_years)
    )


def tournament_importance(tournament: str) -> float:
    if tournament == "Friendly":
        return 0.5
    if tournament == "FIFA World Cup":
        return 1.5
    if tournament in CONTINENTAL_FINALS:
        return 1.25
    return 1.0


def _match_score(home_score: int, away_score: int) -> float:
    if home_score > away_score:
        return 1.0
    if home_score < away_score:
        return 0.0
    return 0.5


def fit_elo(matches: pd.DataFrame, cutoff_at: datetime) -> dict[str, float]:
    if cutoff_at.tzinfo is None or cutoff_at.utcoffset() is None:
        raise ValueError("cutoff_at must include a timezone")

    required_columns = {
        "date",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
        "tournament",
    }
    missing_columns = required_columns - set(matches.columns)
    if missing_columns:
        raise ValueError(f"missing match columns: {sorted(missing_columns)}")

    dated_matches = matches.copy()
    dated_matches["date"] = pd.to_datetime(dated_matches["date"], utc=True)
    cutoff = pd.Timestamp(cutoff_at).tz_convert("UTC")
    training_matches = dated_matches.loc[dated_matches["date"] < cutoff]
    training_matches = training_matches.dropna(subset=["home_score", "away_score"])
    training_matches = training_matches.sort_values("date", kind="stable")

    ratings: dict[str, float] = {}
    for match in training_matches.itertuples(index=False):
        home_team = str(match.home_team)
        away_team = str(match.away_team)
        home_rating = ratings.get(home_team, INITIAL_RATING)
        away_rating = ratings.get(away_team, INITIAL_RATING)
        home_expectation = expected_score(home_rating, away_rating)
        home_result = _match_score(int(match.home_score), int(match.away_score))
        age_days = (cutoff - match.date).days
        effective_k = (
            BASE_K
            * tournament_importance(str(match.tournament))
            * decay_weight(age_days)
        )
        change = effective_k * (home_result - home_expectation)
        ratings[home_team] = home_rating + change
        ratings[away_team] = away_rating - change

    return ratings
