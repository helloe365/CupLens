import argparse
import hashlib
import json
import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.elo import fit_elo  # noqa: E402
from app.dixon_coles import (  # noqa: E402
    adjust_score_matrix,
    select_tournament_rho,
)
from app.poisson import predict_match  # noqa: E402

TOURNAMENT_STARTS = {
    2018: datetime(2018, 6, 14, tzinfo=UTC),
    2022: datetime(2022, 11, 20, tzinfo=UTC),
}
PROBABILITY_FLOOR = 1e-6


def _actual_class(home_score: float, away_score: float) -> int:
    if home_score > away_score:
        return 0
    if home_score < away_score:
        return 2
    return 1


def _metrics(
    probabilities: list[tuple[float, float, float]],
    actual_classes: list[int],
) -> tuple[float, float, float]:
    probability_array = np.asarray(probabilities, dtype=float)
    actual_array = np.asarray(actual_classes, dtype=int)
    predicted_classes = probability_array.argmax(axis=1)
    accuracy = float(np.mean(predicted_classes == actual_array))
    targets = np.eye(3, dtype=float)[actual_array]
    brier_score = float(np.mean(np.sum((probability_array - targets) ** 2, axis=1)))
    actual_probabilities = probability_array[np.arange(len(actual_array)), actual_array]
    clipped = np.clip(
        actual_probabilities,
        PROBABILITY_FLOOR,
        1.0 - PROBABILITY_FLOOR,
    )
    log_loss = float(-np.mean(np.log(clipped)))
    if not all(math.isfinite(value) for value in (accuracy, brier_score, log_loss)):
        raise ValueError("backtest metrics must be finite")
    return accuracy, brier_score, log_loss


def _world_cup_matches(matches: pd.DataFrame, year: int) -> pd.DataFrame:
    dated_matches = matches.copy()
    dated_matches["date"] = pd.to_datetime(dated_matches["date"], utc=True)
    selected = dated_matches.loc[
        (dated_matches["tournament"] == "FIFA World Cup")
        & (dated_matches["date"].dt.year == year)
        & dated_matches["home_score"].notna()
        & dated_matches["away_score"].notna()
    ].sort_values("date", kind="stable")
    if selected.empty:
        raise ValueError(f"no completed FIFA World Cup matches for {year}")
    return selected


def _select_training_rho(
    matches: pd.DataFrame,
    *,
    target_year: int,
    target_start: datetime,
) -> tuple[float, int, datetime]:
    selection = select_tournament_rho(
        matches,
        target_year,
        target_start=target_start,
    )
    return (
        selection.rho,
        selection.training_year,
        selection.training_last_match_at,
    )


def backtest_year(
    matches: pd.DataFrame,
    year: int,
    *,
    variant: str = "baseline",
) -> dict[str, object]:
    if variant not in {"baseline", "dixon-coles"}:
        raise ValueError(f"unsupported model variant: {variant}")
    try:
        tournament_start = TOURNAMENT_STARTS[year]
    except KeyError as error:
        raise ValueError(f"unsupported test year: {year}") from error
    feature_cutoff = tournament_start - timedelta(microseconds=1)
    test_matches = _world_cup_matches(matches, year)

    rho = 0.0
    rho_training_year: int | None = None
    rho_training_last_match_at: datetime | None = None
    if variant == "dixon-coles":
        rho, rho_training_year, rho_training_last_match_at = _select_training_rho(
            matches,
            target_year=year,
            target_start=tournament_start,
        )

    elo_ratings = fit_elo(matches, feature_cutoff)
    probabilities: list[tuple[float, float, float]] = []
    actual_classes: list[int] = []
    for match in test_matches.itertuples(index=False):
        prediction = predict_match(
            str(match.home_team),
            str(match.away_team),
            feature_cutoff,
            matches=matches,
            elo_ratings=elo_ratings,
        )
        if variant == "dixon-coles":
            matrix = adjust_score_matrix(
                prediction.score_matrix,
                prediction.home_xg,
                prediction.away_xg,
                rho,
            )
            probabilities.append(
                (
                    float(np.tril(matrix, k=-1).sum()),
                    float(np.trace(matrix)),
                    float(np.triu(matrix, k=1).sum()),
                )
            )
        else:
            probabilities.append(
                (prediction.home_win, prediction.draw, prediction.away_win)
            )
        actual_classes.append(_actual_class(match.home_score, match.away_score))

    accuracy, brier_score, log_loss = _metrics(probabilities, actual_classes)
    result: dict[str, object] = {
        "test_year": year,
        "feature_cutoff_at": feature_cutoff.isoformat(),
        "first_test_match_at": test_matches.iloc[0]["date"].isoformat(),
        "matches": len(test_matches),
        "accuracy": accuracy,
        "brier_score": brier_score,
        "log_loss": log_loss,
    }
    if variant == "dixon-coles":
        result.update(
            {
                "rho": rho,
                "rho_training_year": rho_training_year,
                "rho_training_last_match_at": rho_training_last_match_at.isoformat()
                if rho_training_last_match_at is not None
                else None,
            }
        )
    return result


def _lightgbm_backtest_year(
    matches: pd.DataFrame,
    year: int,
    *,
    probability_variant: str = "baseline",
) -> dict[str, object]:
    from app.lightgbm_meta import run_meta_backtest

    experiment = run_meta_backtest(
        matches,
        year,
        seed=20260715,
        probability_variant=probability_variant,
    )
    probabilities = [tuple(row) for row in experiment.probabilities.tolist()]
    actual_classes = experiment.actual_classes.tolist()
    accuracy, brier_score, log_loss = _metrics(probabilities, actual_classes)
    result: dict[str, object] = {
        "test_year": year,
        "feature_cutoff_at": experiment.test_feature_cutoff.isoformat(),
        "first_test_match_at": experiment.first_test_match_at.isoformat(),
        "matches": experiment.test_rows,
        "accuracy": accuracy,
        "brier_score": brier_score,
        "log_loss": log_loss,
        "blend_weight": experiment.blend_weight,
        "training_years": list(experiment.training_years),
        "validation_year": experiment.validation_year,
        "validation_last_match_at": experiment.validation_last_match_at.isoformat(),
        "training_rows": experiment.training_rows,
        "validation_rows": experiment.validation_rows,
    }
    if probability_variant == "dixon-coles":
        result["rho_selections"] = [
            {
                "target_year": selection.target_year,
                "rho": selection.rho,
                "training_year": selection.training_year,
                "training_last_match_at": selection.training_last_match_at.isoformat(),
            }
            for selection in experiment.rho_selections
        ]
    return result


def run_backtest(
    data_path: Path,
    test_years: list[int],
    *,
    variant: str = "baseline",
) -> dict[str, object]:
    if variant not in {
        "baseline",
        "dixon-coles",
        "lightgbm-meta",
        "dixon-coles-lightgbm-meta",
    }:
        raise ValueError(f"unsupported model variant: {variant}")
    content = data_path.read_bytes()
    matches = pd.read_csv(data_path)
    if variant in {"lightgbm-meta", "dixon-coles-lightgbm-meta"}:
        combined = variant == "dixon-coles-lightgbm-meta"
        model_version = (
            "elo-poisson-dixon-coles-lightgbm-meta-experiment"
            if combined
            else "elo-poisson-lightgbm-meta-experiment"
        )
        results = [
            _lightgbm_backtest_year(
                matches,
                year,
                probability_variant="dixon-coles" if combined else "baseline",
            )
            for year in test_years
        ]
    else:
        model_version = (
            "elo-poisson-v1"
            if variant == "baseline"
            else "elo-poisson-dixon-coles-experiment"
        )
        results = [
            backtest_year(matches, year, variant=variant) for year in test_years
        ]
    payload: dict[str, object] = {
        "model_version": model_version,
        "data_path": data_path.name,
        "data_sha256": hashlib.sha256(content).hexdigest(),
        "feature_cutoff_rule": "date < tournament_start",
        "score_range": [0, 7],
        "log_loss_probability_clip": [PROBABILITY_FLOOR, 1.0 - PROBABILITY_FLOOR],
        "results": results,
    }
    if variant == "dixon-coles":
        payload["variant"] = variant
        payload["rho_selection_rule"] = (
            "grid search on the latest completed World Cup before each test tournament"
        )
    elif variant in {"lightgbm-meta", "dixon-coles-lightgbm-meta"}:
        from app.lightgbm_meta import FEATURE_NAMES

        payload["variant"] = variant
        payload["features"] = list(FEATURE_NAMES)
        payload["random_seed"] = 20260715
        payload["blend_selection_rule"] = (
            "fixed grid selected on the latest World Cup before the test tournament"
        )
        if variant == "dixon-coles-lightgbm-meta":
            payload["probability_variant"] = "dixon-coles"
            payload["rho_selection_rule"] = (
                "latest completed World Cup before each feature tournament"
            )
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run chronological World Cup backtests")
    parser.add_argument("--test-years", nargs="+", type=int, required=True)
    parser.add_argument(
        "--data",
        type=Path,
        default=PROJECT_ROOT / "data/raw/historical_matches.csv",
    )
    parser.add_argument(
        "--variant",
        choices=(
            "baseline",
            "dixon-coles",
            "lightgbm-meta",
            "dixon-coles-lightgbm-meta",
        ),
        default="baseline",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        payload = run_backtest(
            args.data.resolve(),
            args.test_years,
            variant=args.variant,
        )
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n",
                encoding="utf-8",
            )
    except (OSError, TypeError, ValueError) as error:
        print(f"BACKTEST FAILED: {error}", file=sys.stderr)
        return 1

    for result in payload["results"]:
        fields = [
            f"{result['test_year']} MATCHES={result['matches']}",
            f"ACCURACY={result['accuracy']:.12f}",
            f"BRIER={result['brier_score']:.12f}",
            f"LOG_LOSS={result['log_loss']:.12f}",
        ]
        if args.variant == "dixon-coles":
            fields.extend(
                [
                    f"RHO={result['rho']:.12f}",
                    f"RHO_TRAIN_YEAR={result['rho_training_year']}",
                ]
            )
        elif args.variant in {"lightgbm-meta", "dixon-coles-lightgbm-meta"}:
            fields.extend(
                [
                    f"BLEND_WEIGHT={result['blend_weight']:.12f}",
                    f"TRAINING_YEARS={','.join(str(year) for year in result['training_years'])}",
                    f"VALIDATION_YEAR={result['validation_year']}",
                ]
            )
            if args.variant == "dixon-coles-lightgbm-meta":
                fields.append(
                    "RHO_YEARS="
                    + ",".join(
                        str(selection["target_year"])
                        for selection in result["rho_selections"]
                    )
                )
        print(" ".join(fields))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
