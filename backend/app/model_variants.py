import math
from datetime import datetime, timedelta
from typing import Callable, Mapping

import numpy as np
import pandas as pd

from app.dixon_coles import RhoObservation, adjust_score_matrix, select_rho
from app.elo import INITIAL_RATING, fit_elo
from app.poisson import (
    MatchPrediction,
    ScoreProbability,
    advancement_probability,
    predict_match,
)

ENABLED_VARIANTS = {
    "baseline",
    "dixon-coles",
    "lightgbm-meta",
    "dixon-coles-lightgbm-meta",
}
VALIDATED_LIGHTGBM_WEIGHT = 0.0


def _latest_world_cup_rho(matches: pd.DataFrame, cutoff_at: datetime) -> float:
    dated = matches.copy()
    dated["date"] = pd.to_datetime(dated["date"], utc=True)
    cutoff = pd.Timestamp(cutoff_at).tz_convert("UTC")
    completed = dated.loc[
        (dated["tournament"] == "FIFA World Cup")
        & (dated["date"] < cutoff)
        & dated["home_score"].notna()
        & dated["away_score"].notna()
    ]
    if completed.empty:
        raise ValueError("no completed World Cup available to select rho")
    latest_year = int(completed["date"].dt.year.max())
    calibration = completed.loc[
        completed["date"].dt.year == latest_year
    ].sort_values("date", kind="stable")
    calibration_start = calibration.iloc[0]["date"].to_pydatetime()
    feature_cutoff = calibration_start - timedelta(microseconds=1)
    ratings = fit_elo(matches, feature_cutoff)
    observations = []
    for match in calibration.itertuples(index=False):
        prediction = predict_match(
            str(match.home_team),
            str(match.away_team),
            feature_cutoff,
            matches=matches,
            elo_ratings=ratings,
        )
        observations.append(
            RhoObservation(
                played_at=match.date.to_pydatetime(),
                lambda_home=prediction.home_xg,
                lambda_away=prediction.away_xg,
                home_score=int(match.home_score),
                away_score=int(match.away_score),
            )
        )
    return select_rho(observations, cutoff_at=cutoff_at)


def _prediction_from_matrix(
    baseline: MatchPrediction,
    matrix: np.ndarray,
    ratings: Mapping[str, float],
) -> MatchPrediction:
    home_win = float(np.tril(matrix, k=-1).sum())
    draw = float(np.trace(matrix))
    away_win = float(np.triu(matrix, k=1).sum())
    ranked = sorted(
        (
            ScoreProbability(home, away, float(matrix[home, away]))
            for home in range(matrix.shape[0])
            for away in range(matrix.shape[1])
        ),
        key=lambda score: (-score.probability, score.home_score, score.away_score),
    )
    home_advance = advancement_probability(
        home_win=home_win,
        draw=draw,
        rating_home=float(ratings.get(baseline.team_a, INITIAL_RATING)),
        rating_away=float(ratings.get(baseline.team_b, INITIAL_RATING)),
    )
    if not math.isclose(home_win + draw + away_win, 1.0, abs_tol=1e-12):
        raise ValueError("variant probabilities must sum to one")
    return MatchPrediction(
        team_a=baseline.team_a,
        team_b=baseline.team_b,
        cutoff_at=baseline.cutoff_at,
        home_xg=baseline.home_xg,
        away_xg=baseline.away_xg,
        home_win=home_win,
        draw=draw,
        away_win=away_win,
        home_advance=home_advance,
        away_advance=1.0 - home_advance,
        top_scores=tuple(ranked[:3]),
        score_matrix=matrix,
    )


def build_variant_predictor(
    matches: pd.DataFrame,
    elo_ratings: Mapping[str, float],
    cutoff_at: datetime,
    variant: str,
) -> Callable[[str, str], MatchPrediction]:
    if variant not in ENABLED_VARIANTS:
        raise ValueError(f"unsupported model variant: {variant}")
    uses_dixon_coles = variant in {
        "dixon-coles",
        "dixon-coles-lightgbm-meta",
    }
    rho = _latest_world_cup_rho(matches, cutoff_at) if uses_dixon_coles else None

    def predictor(home_team: str, away_team: str) -> MatchPrediction:
        baseline = predict_match(
            home_team,
            away_team,
            cutoff_at,
            matches=matches,
            elo_ratings=elo_ratings,
        )
        if not uses_dixon_coles:
            return baseline
        matrix = adjust_score_matrix(
            baseline.score_matrix,
            baseline.home_xg,
            baseline.away_xg,
            float(rho),
        )
        return _prediction_from_matrix(baseline, matrix, elo_ratings)

    return predictor
