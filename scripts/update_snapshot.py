import argparse
import hashlib
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.data_store import load_tournament_data  # noqa: E402
from app.config import MODEL_VARIANT, MODEL_VERSION  # noqa: E402
from app.elo import fit_elo  # noqa: E402
from app.model_variants import build_variant_predictor  # noqa: E402
from app.poisson import MatchPrediction, predict_match  # noqa: E402
from app.schemas import MatchRecord, SourceRecord  # noqa: E402
from app.snapshot_service import record_snapshot  # noqa: E402
from app.tournament import simulate_remaining  # noqa: E402

HASHED_INPUTS = (
    "data/mappings/team_names.json",
    "data/raw/groups_final.json",
    "data/raw/historical_matches.csv",
    "data/raw/knockout_results.json",
    "data/sources.json",
    "docs/backtest-baseline.json",
)


def _aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def _validated_sources(root: Path, cutoff_at: datetime) -> list[SourceRecord]:
    sources = [
        SourceRecord.model_validate(item)
        for item in _read_json(root / "data/sources.json")
    ]
    late_sources = [source for source in sources if source.verified_at > cutoff_at]
    if late_sources:
        details = ", ".join(
            f"{source.source_id} at {source.verified_at.isoformat()}"
            for source in late_sources
        )
        raise ValueError(f"source verified after cutoff: {details}")
    return sources


def _normalized_data_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for relative_path in HASHED_INPUTS:
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / relative_path).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _prediction_payload(
    match: MatchRecord,
    prediction: MatchPrediction,
) -> dict[str, Any]:
    return {
        "match_id": match.match_id,
        "stage": match.stage,
        "kickoff_at": match.kickoff_at.isoformat(),
        "home_team": match.home_team,
        "away_team": match.away_team,
        "result_kind": match.result_kind,
        "home_xg": prediction.home_xg,
        "away_xg": prediction.away_xg,
        "home_win": prediction.home_win,
        "draw": prediction.draw,
        "away_win": prediction.away_win,
        "home_advance": prediction.home_advance,
        "away_advance": prediction.away_advance,
        "top_scores": [
            {
                "home_score": score.home_score,
                "away_score": score.away_score,
                "probability": score.probability,
            }
            for score in prediction.top_scores
        ],
    }


def build_snapshot(
    root: Path,
    snapshot_id: str,
    cutoff_at: datetime,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    sources = _validated_sources(root, cutoff_at)
    generated_at = datetime.now().astimezone()
    if cutoff_at > generated_at:
        raise ValueError("cutoff cannot be after the real generation time")

    tournament_data = load_tournament_data(root, cutoff_at=cutoff_at)
    forecast_matches = [
        match
        for match in tournament_data.matches
        if match.result_kind == "forecast"
    ]
    if not forecast_matches:
        raise ValueError("no forecast matches remain")
    first_forecast_at = min(match.kickoff_at for match in forecast_matches)
    if generated_at >= first_forecast_at:
        raise ValueError(
            "generation time is not before the first remaining match: "
            f"generated {generated_at.isoformat()}, kickoff {first_forecast_at.isoformat()}"
        )

    historical_matches = pd.read_csv(root / "data/raw/historical_matches.csv")
    elo_ratings = fit_elo(historical_matches, cutoff_at)
    variant_predictor = build_variant_predictor(
        historical_matches,
        elo_ratings,
        cutoff_at,
        MODEL_VARIANT,
    )
    prediction_cache: dict[tuple[str, str], MatchPrediction] = {}

    def predictor(home_team: str, away_team: str) -> MatchPrediction:
        pair = (home_team, away_team)
        if pair not in prediction_cache:
            prediction_cache[pair] = variant_predictor(home_team, away_team)
        return prediction_cache[pair]

    simulation = simulate_remaining(
        tournament_data,
        predictor,
        iterations=iterations,
        seed=seed,
    )
    champion_sum = sum(simulation.champion_probabilities.values())
    if not math.isclose(champion_sum, 1.0, abs_tol=1e-12):
        raise ValueError("champion probabilities must sum to one")

    forecast_payload: list[dict[str, Any]] = []
    for match in forecast_matches:
        if match.home_team != "TBD" and match.away_team != "TBD":
            forecast_payload.append(_prediction_payload(match, predictor(match.home_team, match.away_team)))
        else:
            forecast_payload.append(match.model_dump(mode="json"))

    team_probabilities = [
        {
            "team": team,
            "champion_probability": probability,
            "final_probability": simulation.final_probabilities.get(team, 0.0),
        }
        for team, probability in simulation.champion_probabilities.items()
    ]
    return {
        "snapshot_id": snapshot_id,
        "generated_at": generated_at.isoformat(),
        "cutoff_at": cutoff_at.isoformat(),
        "model_version": MODEL_VERSION,
        "data_sha256": _normalized_data_hash(root),
        "random_seed": seed,
        "iterations": iterations,
        "sources": [source.model_dump(mode="json") for source in sources],
        "actual_matches": [
            match.model_dump(mode="json")
            for match in tournament_data.matches
            if match.result_kind == "actual"
        ],
        "forecast_matches": forecast_payload,
        "team_probabilities": team_probabilities,
        "metrics": _read_json(root / "docs/backtest-baseline.json"),
        "limitations": [
            "Independent Poisson score model with scores truncated to 0-7.",
            "Advancement uses an Elo allocation for drawn score-matrix outcomes; it is not an exact extra-time or penalty model.",
            "Lineups, injuries, suspensions, weather, news, and player-level data are not modeled.",
            "Predictions are uncertain estimates and are not betting advice.",
        ],
    }


def create_snapshot(
    root: Path,
    output_dir: Path,
    snapshot_id: str,
    cutoff_at: datetime,
    iterations: int,
    seed: int,
    *,
    builder=build_snapshot,
) -> tuple[dict[str, Any], Path]:
    """Build, validate, and immutably record one snapshot."""
    snapshot = builder(root, snapshot_id, cutoff_at, iterations, seed)
    target = record_snapshot(snapshot, output_dir)
    return snapshot, target


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create an immutable forecast snapshot")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--cutoff-at", type=_aware_datetime, required=True)
    parser.add_argument("--iterations", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = args.root.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else root / "data/snapshots"
    )
    try:
        snapshot, target = create_snapshot(
            root,
            output_dir,
            args.snapshot_id,
            args.cutoff_at,
            args.iterations,
            args.seed,
        )
    except (FileExistsError, OSError, TypeError, ValueError) as error:
        print(f"SNAPSHOT BLOCKED: {error}", file=sys.stderr)
        return 1

    print(f"SNAPSHOT: {target}")
    print(f"GENERATED AT: {snapshot['generated_at']}")
    print(f"CUTOFF AT: {snapshot['cutoff_at']}")
    print(f"DATA SHA-256: {snapshot['data_sha256']}")
    for item in snapshot["team_probabilities"]:
        print(
            f"{item['team']}: champion={item['champion_probability']:.12f} "
            f"final={item['final_probability']:.12f}"
        )
    print(
        "CHAMPION PROBABILITY SUM: "
        f"{sum(item['champion_probability'] for item in snapshot['team_probabilities']):.12f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
