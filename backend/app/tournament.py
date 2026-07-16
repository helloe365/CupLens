import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.schemas import MatchRecord


@dataclass(frozen=True)
class TournamentForecast:
    iterations: int
    seed: int
    champion_probabilities: dict[str, float]
    final_probabilities: dict[str, float]


def _actual_outcome(match: MatchRecord) -> tuple[str, str]:
    if match.result_kind != "actual" or match.status != "finished":
        raise ValueError(f"match {match.match_id} is not an actual result")
    if match.home_penalty_score is not None:
        home_won = match.home_penalty_score > match.away_penalty_score
    elif match.home_score != match.away_score:
        home_won = match.home_score > match.away_score
    else:
        raise ValueError(f"actual match {match.match_id} has no winner")
    if home_won:
        return match.home_team, match.away_team
    return match.away_team, match.home_team


def _validate_bracket_links(matches_by_id: dict[int, MatchRecord]) -> None:
    for match in matches_by_id.values():
        source_slots = (
            (match.home_source_match_id, match.home_source_outcome),
            (match.away_source_match_id, match.away_source_outcome),
        )
        for source_match_id, source_outcome in source_slots:
            if source_match_id is None:
                continue
            try:
                source = matches_by_id[source_match_id]
            except KeyError as error:
                raise ValueError(
                    f"match {match.match_id} references unknown source {source_match_id}"
                ) from error
            expected_next = (
                source.next_match_id
                if source_outcome == "winner"
                else source.loser_next_match_id
            )
            if expected_next != match.match_id:
                raise ValueError(
                    f"match {match.match_id} conflicts with source {source_match_id} "
                    f"{source_outcome} link"
                )


def _resolve_team(
    configured_team: str,
    source_match_id: int | None,
    source_outcome: str | None,
    outcomes: dict[int, tuple[str, str]],
) -> str:
    if source_match_id is None:
        if configured_team == "TBD":
            raise ValueError("TBD participant requires a source match")
        return configured_team
    try:
        winner, loser = outcomes[source_match_id]
    except KeyError as error:
        raise ValueError(f"source match {source_match_id} has no outcome") from error
    resolved = winner if source_outcome == "winner" else loser
    if configured_team != "TBD" and configured_team != resolved:
        raise ValueError(
            f"configured team {configured_team} conflicts with resolved team {resolved}"
        )
    return resolved


def _home_advance_probability(prediction: Any) -> float:
    if isinstance(prediction, dict):
        probability = prediction.get("home_advance")
    else:
        probability = getattr(prediction, "home_advance", None)
    if probability is None:
        raise ValueError("predictor must return home_advance")
    value = float(probability)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("home_advance must be finite and between zero and one")
    return value


def simulate_remaining(
    data: Any,
    predictor: Callable[[str, str], Any],
    iterations: int,
    seed: int,
) -> TournamentForecast:
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    matches = list(data.matches)
    matches_by_id = {match.match_id: match for match in matches}
    if len(matches_by_id) != len(matches):
        raise ValueError("duplicate match IDs")
    _validate_bracket_links(matches_by_id)

    actual_outcomes = {
        match.match_id: _actual_outcome(match)
        for match in matches
        if match.result_kind == "actual"
    }
    forecast_matches = sorted(
        (match for match in matches if match.result_kind == "forecast"),
        key=lambda match: match.match_id,
    )
    final_matches = [match for match in matches if match.stage == "final"]
    if len(final_matches) != 1:
        raise ValueError("tournament requires exactly one final")
    final_match_id = final_matches[0].match_id

    rng = np.random.default_rng(seed)
    probability_cache: dict[tuple[str, str], float] = {}
    champion_counts: dict[str, int] = {}
    final_counts: dict[str, int] = {}

    for _ in range(iterations):
        outcomes = dict(actual_outcomes)
        for match in forecast_matches:
            home_team = _resolve_team(
                match.home_team,
                match.home_source_match_id,
                match.home_source_outcome,
                outcomes,
            )
            away_team = _resolve_team(
                match.away_team,
                match.away_source_match_id,
                match.away_source_outcome,
                outcomes,
            )
            pair = (home_team, away_team)
            if pair not in probability_cache:
                probability_cache[pair] = _home_advance_probability(
                    predictor(home_team, away_team)
                )
            if rng.random() < probability_cache[pair]:
                outcome = (home_team, away_team)
            else:
                outcome = (away_team, home_team)
            outcomes[match.match_id] = outcome

            if match.match_id == final_match_id:
                final_counts[home_team] = final_counts.get(home_team, 0) + 1
                final_counts[away_team] = final_counts.get(away_team, 0) + 1
                champion = outcome[0]
                champion_counts[champion] = champion_counts.get(champion, 0) + 1

    teams = sorted(set(champion_counts) | set(final_counts))
    champion_probabilities = {
        team: champion_counts.get(team, 0) / iterations for team in teams
    }
    final_probabilities = {
        team: final_counts.get(team, 0) / iterations for team in teams
    }
    if not math.isclose(sum(champion_probabilities.values()), 1.0, abs_tol=1e-12):
        raise ValueError("champion probabilities must sum to one")
    return TournamentForecast(
        iterations=iterations,
        seed=seed,
        champion_probabilities=champion_probabilities,
        final_probabilities=final_probabilities,
    )
