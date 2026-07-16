import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping

import numpy as np
import pandas as pd
from scipy.stats import poisson

from app.elo import INITIAL_RATING, decay_weight, expected_score


@dataclass(frozen=True)
class ScoreProbability:
    home_score: int
    away_score: int
    probability: float


@dataclass(frozen=True)
class OutcomeProbabilities:
    home_win: float
    draw: float
    away_win: float
    score_matrix: np.ndarray = field(compare=False, repr=False)
    top_scores: tuple[ScoreProbability, ...]


@dataclass(frozen=True)
class FormStrength:
    attack: float
    defense: float
    weighted_games: float
    matches_used: int


@dataclass(frozen=True)
class MatchPrediction:
    team_a: str
    team_b: str
    cutoff_at: datetime
    home_xg: float
    away_xg: float
    home_win: float
    draw: float
    away_win: float
    home_advance: float
    away_advance: float
    top_scores: tuple[ScoreProbability, ...]
    score_matrix: np.ndarray = field(compare=False, repr=False)


def score_matrix(
    lambda_home: float,
    lambda_away: float,
    max_goals: int = 7,
) -> np.ndarray:
    goals = np.arange(max_goals + 1)
    home = poisson.pmf(goals, lambda_home)
    away = poisson.pmf(goals, lambda_away)
    matrix = np.outer(home, away)
    return matrix / matrix.sum()


def outcome_probabilities(
    lambda_home: float,
    lambda_away: float,
    max_goals: int = 7,
) -> OutcomeProbabilities:
    matrix = score_matrix(lambda_home, lambda_away, max_goals=max_goals)
    home_win = float(np.tril(matrix, k=-1).sum())
    draw = float(np.trace(matrix))
    away_win = float(np.triu(matrix, k=1).sum())
    ranked_scores = sorted(
        (
            ScoreProbability(home_score, away_score, float(matrix[home_score, away_score]))
            for home_score in range(max_goals + 1)
            for away_score in range(max_goals + 1)
        ),
        key=lambda score: (-score.probability, score.home_score, score.away_score),
    )
    return OutcomeProbabilities(
        home_win=home_win,
        draw=draw,
        away_win=away_win,
        score_matrix=matrix,
        top_scores=tuple(ranked_scores[:3]),
    )


def _cutoff_timestamp(cutoff_at: datetime) -> pd.Timestamp:
    if cutoff_at.tzinfo is None or cutoff_at.utcoffset() is None:
        raise ValueError("cutoff_at must include a timezone")
    return pd.Timestamp(cutoff_at).tz_convert("UTC")


def _pre_cutoff_matches(
    matches: pd.DataFrame,
    cutoff_at: datetime,
) -> tuple[pd.DataFrame, pd.Timestamp]:
    required_columns = {
        "date",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
    }
    missing_columns = required_columns - set(matches.columns)
    if missing_columns:
        raise ValueError(f"missing match columns: {sorted(missing_columns)}")
    cutoff = _cutoff_timestamp(cutoff_at)
    prepared = matches.copy()
    prepared["date"] = pd.to_datetime(prepared["date"], utc=True)
    prepared = prepared.loc[prepared["date"] < cutoff]
    prepared = prepared.dropna(subset=["home_score", "away_score"])
    return prepared, cutoff


def global_mean_goals(matches: pd.DataFrame, cutoff_at: datetime) -> float:
    prepared, _ = _pre_cutoff_matches(matches, cutoff_at)
    if prepared.empty:
        raise ValueError("at least one pre-cutoff match is required")
    total_goals = prepared["home_score"].sum() + prepared["away_score"].sum()
    mean = float(total_goals / (2.0 * len(prepared)))
    if not math.isfinite(mean) or mean <= 0.0:
        raise ValueError("global mean goals must be positive and finite")
    return mean


def form_strength(
    matches: pd.DataFrame,
    team: str,
    cutoff_at: datetime,
    *,
    global_mean: float,
    recent_matches: int = 20,
    shrinkage_games: float = 5.0,
) -> FormStrength:
    if global_mean <= 0.0 or not math.isfinite(global_mean):
        raise ValueError("global_mean must be positive and finite")
    prepared, cutoff = _pre_cutoff_matches(matches, cutoff_at)
    team_matches = prepared.loc[
        (prepared["home_team"] == team) | (prepared["away_team"] == team)
    ].sort_values("date", ascending=False, kind="stable")
    team_matches = team_matches.head(recent_matches)
    if team_matches.empty:
        return FormStrength(1.0, 1.0, 0.0, 0)

    weighted_goals_for = 0.0
    weighted_goals_against = 0.0
    weighted_games = 0.0
    for match in team_matches.itertuples(index=False):
        weight = decay_weight((cutoff - match.date).days)
        if str(match.home_team) == team:
            goals_for = float(match.home_score)
            goals_against = float(match.away_score)
        else:
            goals_for = float(match.away_score)
            goals_against = float(match.home_score)
        weighted_goals_for += weight * goals_for
        weighted_goals_against += weight * goals_against
        weighted_games += weight

    denominator = weighted_games + shrinkage_games
    attack = (
        (weighted_goals_for + shrinkage_games * global_mean) / denominator
    ) / global_mean
    defense = (
        (weighted_goals_against + shrinkage_games * global_mean) / denominator
    ) / global_mean
    return FormStrength(attack, defense, weighted_games, len(team_matches))


def advancement_probability(
    *,
    home_win: float,
    draw: float,
    rating_home: float,
    rating_away: float,
) -> float:
    return home_win + draw * expected_score(rating_home, rating_away)


def predict_match(
    team_a: str,
    team_b: str,
    cutoff_at: datetime,
    *,
    matches: pd.DataFrame,
    elo_ratings: Mapping[str, float],
    max_goals: int = 7,
) -> MatchPrediction:
    mean_goals = global_mean_goals(matches, cutoff_at)
    home_strength = form_strength(
        matches,
        team_a,
        cutoff_at,
        global_mean=mean_goals,
    )
    away_strength = form_strength(
        matches,
        team_b,
        cutoff_at,
        global_mean=mean_goals,
    )
    home_rating = float(elo_ratings.get(team_a, INITIAL_RATING))
    away_rating = float(elo_ratings.get(team_b, INITIAL_RATING))
    home_xg = mean_goals * home_strength.attack * away_strength.defense
    home_xg *= math.exp(0.25 * (home_rating - away_rating) / 400.0)
    away_xg = mean_goals * away_strength.attack * home_strength.defense
    away_xg *= math.exp(0.25 * (away_rating - home_rating) / 400.0)
    home_xg = min(3.5, max(0.2, home_xg))
    away_xg = min(3.5, max(0.2, away_xg))

    outcomes = outcome_probabilities(home_xg, away_xg, max_goals=max_goals)
    home_advance = advancement_probability(
        home_win=outcomes.home_win,
        draw=outcomes.draw,
        rating_home=home_rating,
        rating_away=away_rating,
    )
    return MatchPrediction(
        team_a=team_a,
        team_b=team_b,
        cutoff_at=cutoff_at,
        home_xg=home_xg,
        away_xg=away_xg,
        home_win=outcomes.home_win,
        draw=outcomes.draw,
        away_win=outcomes.away_win,
        home_advance=home_advance,
        away_advance=1.0 - home_advance,
        top_scores=outcomes.top_scores,
        score_matrix=outcomes.score_matrix,
    )
