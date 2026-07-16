import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from app.elo import fit_elo
from app.poisson import predict_match


DEFAULT_RHO_CANDIDATES = tuple(round(-0.15 + index * 0.01, 2) for index in range(31))


@dataclass(frozen=True)
class RhoObservation:
    played_at: datetime
    lambda_home: float
    lambda_away: float
    home_score: int
    away_score: int


@dataclass(frozen=True)
class TournamentRhoSelection:
    target_year: int
    rho: float
    training_year: int
    training_last_match_at: datetime


def tau(
    home_score: int,
    away_score: int,
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> float:
    if home_score == 0 and away_score == 0:
        return 1.0 - lambda_home * lambda_away * rho
    if home_score == 1 and away_score == 0:
        return 1.0 + lambda_away * rho
    if home_score == 0 and away_score == 1:
        return 1.0 + lambda_home * rho
    if home_score == 1 and away_score == 1:
        return 1.0 - rho
    return 1.0


def _low_score_factors(
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> tuple[float, float, float, float]:
    return (
        tau(0, 0, lambda_home, lambda_away, rho),
        tau(1, 0, lambda_home, lambda_away, rho),
        tau(0, 1, lambda_home, lambda_away, rho),
        tau(1, 1, lambda_home, lambda_away, rho),
    )


def adjust_score_matrix(
    matrix: np.ndarray,
    lambda_home: float,
    lambda_away: float,
    rho: float,
) -> np.ndarray:
    if matrix.ndim != 2 or matrix.shape[0] < 2 or matrix.shape[1] < 2:
        raise ValueError("score matrix must include scores zero and one")
    if rho == 0.0:
        return matrix.copy()

    factors = _low_score_factors(lambda_home, lambda_away, rho)
    if not all(math.isfinite(factor) and factor > 0.0 for factor in factors):
        raise ValueError("rho produces a non-positive low-score correction")

    adjusted = np.asarray(matrix, dtype=float).copy()
    adjusted[0, 0] *= factors[0]
    adjusted[1, 0] *= factors[1]
    adjusted[0, 1] *= factors[2]
    adjusted[1, 1] *= factors[3]
    total = float(adjusted.sum())
    if not math.isfinite(total) or total <= 0.0:
        raise ValueError("adjusted score matrix must have positive finite mass")
    return adjusted / total


def select_rho(
    observations: Iterable[RhoObservation],
    *,
    cutoff_at: datetime,
    candidates: Sequence[float] = DEFAULT_RHO_CANDIDATES,
) -> float:
    if cutoff_at.tzinfo is None or cutoff_at.utcoffset() is None:
        raise ValueError("cutoff_at must include a timezone")
    training = [
        observation
        for observation in observations
        if observation.played_at < cutoff_at
    ]
    if not training:
        raise ValueError("at least one pre-cutoff observation is required")
    if not candidates:
        raise ValueError("at least one rho candidate is required")

    scored: list[tuple[float, float]] = []
    for candidate in candidates:
        log_likelihood = 0.0
        valid = True
        for observation in training:
            factors = _low_score_factors(
                observation.lambda_home,
                observation.lambda_away,
                candidate,
            )
            if not all(
                math.isfinite(factor) and factor > 0.0 for factor in factors
            ):
                valid = False
                break
            log_likelihood += math.log(
                tau(
                    observation.home_score,
                    observation.away_score,
                    observation.lambda_home,
                    observation.lambda_away,
                    candidate,
                )
            )
        if valid:
            scored.append((float(candidate), log_likelihood))

    if not scored:
        raise ValueError("no rho candidate produces valid corrections")
    selected, _ = max(
        scored,
        key=lambda item: (item[1], -abs(item[0]), -item[0]),
    )
    return selected


def _world_cup_matches(matches: pd.DataFrame, year: int) -> pd.DataFrame:
    dated = matches.copy()
    dated["date"] = pd.to_datetime(dated["date"], utc=True)
    selected = dated.loc[
        (dated["tournament"] == "FIFA World Cup")
        & (dated["date"].dt.year == year)
        & dated["home_score"].notna()
        & dated["away_score"].notna()
    ].sort_values("date", kind="stable")
    if selected.empty:
        raise ValueError(f"no completed FIFA World Cup matches for {year}")
    return selected


def select_tournament_rho(
    matches: pd.DataFrame,
    target_year: int,
    *,
    target_start: datetime | None = None,
) -> TournamentRhoSelection:
    target_matches = _world_cup_matches(matches, target_year)
    if target_start is None:
        target_start = target_matches.iloc[0]["date"].to_pydatetime()
    if target_start.tzinfo is None or target_start.utcoffset() is None:
        raise ValueError("target_start must include a timezone")

    dated = matches.copy()
    dated["date"] = pd.to_datetime(dated["date"], utc=True)
    prior_world_cups = dated.loc[
        (dated["tournament"] == "FIFA World Cup")
        & (dated["date"] < target_start)
        & dated["home_score"].notna()
        & dated["away_score"].notna()
    ]
    prior_years = sorted(
        int(year)
        for year in prior_world_cups["date"].dt.year.unique()
        if int(year) < target_year
    )
    if not prior_years:
        raise ValueError(f"no prior World Cup available to select rho for {target_year}")

    training_year = prior_years[-1]
    training_matches = _world_cup_matches(matches, training_year)
    training_start = training_matches.iloc[0]["date"].to_pydatetime()
    training_cutoff = training_start - timedelta(microseconds=1)
    elo_ratings = fit_elo(matches, training_cutoff)
    observations: list[RhoObservation] = []
    for match in training_matches.itertuples(index=False):
        prediction = predict_match(
            str(match.home_team),
            str(match.away_team),
            training_cutoff,
            matches=matches,
            elo_ratings=elo_ratings,
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

    return TournamentRhoSelection(
        target_year=target_year,
        rho=select_rho(observations, cutoff_at=target_start),
        training_year=training_year,
        training_last_match_at=training_matches.iloc[-1]["date"].to_pydatetime(),
    )
