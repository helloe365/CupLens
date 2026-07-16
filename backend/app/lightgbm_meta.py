import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

import numpy as np
import pandas as pd

from app.dixon_coles import (
    TournamentRhoSelection,
    adjust_score_matrix,
    select_tournament_rho,
)
from app.elo import INITIAL_RATING, fit_elo
from app.poisson import form_strength, global_mean_goals, outcome_probabilities


FEATURE_NAMES = (
    "elo_diff",
    "poisson_home_win",
    "poisson_draw",
    "poisson_away_win",
    "attack_diff",
    "defense_diff",
    "recent_five_form_diff",
    "neutral",
    "rest_days_diff",
)
PROBABILITY_FLOOR = 1e-6


@dataclass(frozen=True)
class MetaRow:
    match_date: datetime
    feature_cutoff: datetime
    features: tuple[float, ...]
    baseline_probabilities: tuple[float, float, float]
    actual_class: int


@dataclass(frozen=True)
class MetaBacktestResult:
    probabilities: np.ndarray
    baseline_probabilities: np.ndarray
    actual_classes: np.ndarray
    blend_weight: float
    rho_selections: tuple[TournamentRhoSelection, ...]
    training_years: tuple[int, ...]
    validation_year: int
    validation_last_match_at: datetime
    test_feature_cutoff: datetime
    first_test_match_at: datetime
    training_rows: int
    validation_rows: int
    test_rows: int


def validate_feature_cutoffs(rows: Sequence[MetaRow]) -> None:
    for row in rows:
        if row.feature_cutoff >= row.match_date:
            raise ValueError("feature_cutoff must be strictly before match_date")
        if len(row.features) != len(FEATURE_NAMES):
            raise ValueError("feature row does not match FEATURE_NAMES")


def _normalized_probabilities(probabilities: np.ndarray) -> np.ndarray:
    values = np.asarray(probabilities, dtype=float)
    if values.ndim != 2 or values.shape[1] != 3:
        raise ValueError("probabilities must have shape (rows, 3)")
    if not np.all(np.isfinite(values)) or np.any(values < 0.0):
        raise ValueError("probabilities must be finite and non-negative")
    totals = values.sum(axis=1, keepdims=True)
    if np.any(totals <= 0.0):
        raise ValueError("probability rows must have positive mass")
    return values / totals


def fit_predict_probabilities(
    training_rows: Sequence[MetaRow],
    prediction_rows: Sequence[MetaRow],
    *,
    seed: int,
) -> np.ndarray:
    import lightgbm as lgb

    if not training_rows or not prediction_rows:
        raise ValueError("training and prediction rows are required")
    validate_feature_cutoffs(training_rows)
    validate_feature_cutoffs(prediction_rows)
    training_features = np.asarray(
        [row.features for row in training_rows],
        dtype=float,
    )
    training_targets = np.asarray(
        [row.actual_class for row in training_rows],
        dtype=int,
    )
    if set(training_targets.tolist()) != {0, 1, 2}:
        raise ValueError("training rows must contain all three outcome classes")

    dataset = lgb.Dataset(training_features, label=training_targets)
    model = lgb.train(
        {
            "objective": "multiclass",
            "num_class": 3,
            "learning_rate": 0.05,
            "num_leaves": 7,
            "max_depth": 3,
            "min_data_in_leaf": 10,
            "lambda_l2": 1.0,
            "seed": seed,
            "num_threads": 1,
            "deterministic": True,
            "force_col_wise": True,
            "verbosity": -1,
        },
        dataset,
        num_boost_round=80,
    )
    raw = np.asarray(
        model.predict(
            np.asarray([row.features for row in prediction_rows], dtype=float),
            num_threads=1,
        ),
        dtype=float,
    )
    return _normalized_probabilities(raw)


def blend_probabilities(
    baseline: np.ndarray,
    meta: np.ndarray,
    meta_weight: float,
) -> np.ndarray:
    if not 0.0 <= meta_weight <= 1.0:
        raise ValueError("meta_weight must be between zero and one")
    baseline_values = _normalized_probabilities(baseline)
    meta_values = _normalized_probabilities(meta)
    if baseline_values.shape != meta_values.shape:
        raise ValueError("baseline and meta probabilities must have the same shape")
    return _normalized_probabilities(
        (1.0 - meta_weight) * baseline_values + meta_weight * meta_values
    )


def _validation_loss(
    probabilities: np.ndarray,
    actual_classes: np.ndarray,
) -> float:
    targets = np.eye(3, dtype=float)[actual_classes]
    brier = float(np.mean(np.sum((probabilities - targets) ** 2, axis=1)))
    observed = probabilities[np.arange(len(actual_classes)), actual_classes]
    log_loss = float(-np.mean(np.log(np.clip(observed, PROBABILITY_FLOOR, 1.0))))
    return brier + log_loss


def select_blend_weight(
    baseline: np.ndarray,
    meta: np.ndarray,
    actual_classes: np.ndarray,
    *,
    candidates: Sequence[float] = (0.0, 0.25, 0.5, 0.75, 1.0),
) -> float:
    baseline_values = _normalized_probabilities(baseline)
    meta_values = _normalized_probabilities(meta)
    targets = np.asarray(actual_classes, dtype=int)
    if baseline_values.shape != meta_values.shape:
        raise ValueError("baseline and meta probabilities must have the same shape")
    if len(targets) != len(baseline_values):
        raise ValueError("actual_classes must match probability rows")
    if not candidates:
        raise ValueError("at least one blend candidate is required")

    scored = [
        (
            float(candidate),
            _validation_loss(
                blend_probabilities(baseline_values, meta_values, candidate),
                targets,
            ),
        )
        for candidate in candidates
    ]
    selected, _ = min(scored, key=lambda item: (item[1], item[0]))
    return selected


def _actual_class(home_score: float, away_score: float) -> int:
    if home_score > away_score:
        return 0
    if home_score < away_score:
        return 2
    return 1


def _neutral_value(value: object) -> float:
    if isinstance(value, str):
        return 1.0 if value.strip().lower() in {"1", "true", "yes"} else 0.0
    return 1.0 if bool(value) else 0.0


def _recent_summary(
    prepared: pd.DataFrame,
    team: str,
    cutoff: pd.Timestamp,
) -> tuple[float, float]:
    team_matches = prepared.loc[
        (prepared["home_team"] == team) | (prepared["away_team"] == team)
    ].sort_values("date", ascending=False, kind="stable")
    if team_matches.empty:
        return 0.5, 3650.0

    recent = team_matches.head(5)
    points = 0.0
    for match in recent.itertuples(index=False):
        home_score = float(match.home_score)
        away_score = float(match.away_score)
        if home_score == away_score:
            points += 1.0
        elif (str(match.home_team) == team and home_score > away_score) or (
            str(match.away_team) == team and away_score > home_score
        ):
            points += 3.0
    form = points / (3.0 * len(recent))
    rest_days = max(
        0.0,
        (cutoff - team_matches.iloc[0]["date"]).total_seconds() / 86400.0,
    )
    return form, min(rest_days, 3650.0)


def build_world_cup_rows(
    matches: pd.DataFrame,
    year: int,
    *,
    probability_variant: str = "baseline",
    rho: float | None = None,
) -> list[MetaRow]:
    if probability_variant not in {"baseline", "dixon-coles"}:
        raise ValueError(f"unsupported probability variant: {probability_variant}")
    if probability_variant == "baseline" and rho is not None:
        raise ValueError("rho is only valid for Dixon-Coles probabilities")
    if probability_variant == "dixon-coles" and rho is None:
        rho = select_tournament_rho(matches, year).rho

    required_columns = {
        "date",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
        "tournament",
    }
    missing = required_columns - set(matches.columns)
    if missing:
        raise ValueError(f"missing match columns: {sorted(missing)}")

    dated = matches.copy()
    dated["date"] = pd.to_datetime(dated["date"], utc=True)
    tournament = dated.loc[
        (dated["tournament"] == "FIFA World Cup")
        & (dated["date"].dt.year == year)
        & dated["home_score"].notna()
        & dated["away_score"].notna()
    ].sort_values("date", kind="stable")
    if tournament.empty:
        raise ValueError(f"no completed FIFA World Cup matches for {year}")

    cutoff = tournament.iloc[0]["date"] - timedelta(microseconds=1)
    cutoff_at = cutoff.to_pydatetime()
    prepared = dated.loc[
        (dated["date"] < cutoff)
        & dated["home_score"].notna()
        & dated["away_score"].notna()
    ]
    elo_ratings = fit_elo(matches, cutoff_at)
    mean_goals = global_mean_goals(matches, cutoff_at)
    teams = sorted(
        set(tournament["home_team"].astype(str))
        | set(tournament["away_team"].astype(str))
    )
    strengths = {
        team: form_strength(
            matches,
            team,
            cutoff_at,
            global_mean=mean_goals,
        )
        for team in teams
    }
    recent = {team: _recent_summary(prepared, team, cutoff) for team in teams}

    rows: list[MetaRow] = []
    for match in tournament.itertuples(index=False):
        home_team = str(match.home_team)
        away_team = str(match.away_team)
        home_rating = float(elo_ratings.get(home_team, INITIAL_RATING))
        away_rating = float(elo_ratings.get(away_team, INITIAL_RATING))
        home_strength = strengths[home_team]
        away_strength = strengths[away_team]
        home_xg = mean_goals * home_strength.attack * away_strength.defense
        home_xg *= math.exp(0.25 * (home_rating - away_rating) / 400.0)
        away_xg = mean_goals * away_strength.attack * home_strength.defense
        away_xg *= math.exp(0.25 * (away_rating - home_rating) / 400.0)
        home_xg = min(3.5, max(0.2, home_xg))
        away_xg = min(3.5, max(0.2, away_xg))
        baseline = outcome_probabilities(home_xg, away_xg, max_goals=7)
        if probability_variant == "dixon-coles":
            adjusted = adjust_score_matrix(
                baseline.score_matrix,
                home_xg,
                away_xg,
                float(rho),
            )
            probability_values = (
                float(np.tril(adjusted, k=-1).sum()),
                float(np.trace(adjusted)),
                float(np.triu(adjusted, k=1).sum()),
            )
        else:
            probability_values = (
                baseline.home_win,
                baseline.draw,
                baseline.away_win,
            )
        home_form, home_rest = recent[home_team]
        away_form, away_rest = recent[away_team]
        neutral = _neutral_value(getattr(match, "neutral", False))
        rows.append(
            MetaRow(
                match_date=match.date.to_pydatetime(),
                feature_cutoff=cutoff_at,
                features=(
                    (home_rating - away_rating) / 400.0,
                    *probability_values,
                    home_strength.attack - away_strength.attack,
                    home_strength.defense - away_strength.defense,
                    home_form - away_form,
                    neutral,
                    (home_rest - away_rest) / 30.0,
                ),
                baseline_probabilities=probability_values,
                actual_class=_actual_class(match.home_score, match.away_score),
            )
        )
    validate_feature_cutoffs(rows)
    return rows


def _available_world_cup_years(matches: pd.DataFrame) -> list[int]:
    dates = pd.to_datetime(matches["date"], utc=True)
    years = dates.loc[matches["tournament"] == "FIFA World Cup"].dt.year.unique()
    return sorted(int(year) for year in years if int(year) >= 2006)


def _probability_array(rows: Sequence[MetaRow]) -> np.ndarray:
    return np.asarray([row.baseline_probabilities for row in rows], dtype=float)


def _class_array(rows: Sequence[MetaRow]) -> np.ndarray:
    return np.asarray([row.actual_class for row in rows], dtype=int)


def run_meta_backtest(
    matches: pd.DataFrame,
    test_year: int,
    *,
    seed: int,
    probability_variant: str = "baseline",
) -> MetaBacktestResult:
    if probability_variant not in {"baseline", "dixon-coles"}:
        raise ValueError(f"unsupported probability variant: {probability_variant}")
    prior_years = [
        year for year in _available_world_cup_years(matches) if year < test_year
    ]
    if len(prior_years) < 3:
        raise ValueError("at least three prior World Cups are required")
    validation_year = prior_years[-1]
    training_years = tuple(prior_years[:-1])
    rho_selections: list[TournamentRhoSelection] = []

    def rows_for_year(year: int) -> list[MetaRow]:
        if probability_variant == "baseline":
            return build_world_cup_rows(matches, year)
        selection = select_tournament_rho(matches, year)
        rho_selections.append(selection)
        return build_world_cup_rows(
            matches,
            year,
            probability_variant="dixon-coles",
            rho=selection.rho,
        )

    training_rows = [
        row
        for year in training_years
        for row in rows_for_year(year)
    ]
    validation_rows = rows_for_year(validation_year)
    test_rows = rows_for_year(test_year)
    validate_feature_cutoffs(training_rows + validation_rows + test_rows)

    validation_meta = fit_predict_probabilities(
        training_rows,
        validation_rows,
        seed=seed,
    )
    validation_baseline = _probability_array(validation_rows)
    blend_weight = select_blend_weight(
        validation_baseline,
        validation_meta,
        _class_array(validation_rows),
    )
    test_meta = fit_predict_probabilities(
        training_rows + validation_rows,
        test_rows,
        seed=seed,
    )
    probabilities = blend_probabilities(
        _probability_array(test_rows),
        test_meta,
        blend_weight,
    )
    return MetaBacktestResult(
        probabilities=probabilities,
        baseline_probabilities=_probability_array(test_rows),
        actual_classes=_class_array(test_rows),
        blend_weight=blend_weight,
        rho_selections=tuple(rho_selections),
        training_years=training_years,
        validation_year=validation_year,
        validation_last_match_at=max(row.match_date for row in validation_rows),
        test_feature_cutoff=test_rows[0].feature_cutoff,
        first_test_match_at=min(row.match_date for row in test_rows),
        training_rows=len(training_rows),
        validation_rows=len(validation_rows),
        test_rows=len(test_rows),
    )
