import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.data_store import load_tournament_data  # noqa: E402
from app.schemas import MatchRecord, TournamentData  # noqa: E402


def _winner(match: MatchRecord) -> str:
    if match.status != "finished":
        raise ValueError(f"match {match.match_id} has no actual winner")
    if match.home_penalty_score is not None:
        if match.home_penalty_score > match.away_penalty_score:
            return match.home_team
        return match.away_team
    if match.home_score == match.away_score:
        raise ValueError(f"match {match.match_id} has no recorded tiebreaker")
    if match.home_score > match.away_score:
        return match.home_team
    return match.away_team


def _validate_groups(data: TournamentData) -> None:
    expected_groups = list("ABCDEFGHIJKL")
    if [group.group for group in data.groups] != expected_groups:
        raise ValueError("groups must be ordered A through L")

    teams: list[str] = []
    for group in data.groups:
        if [standing.rank for standing in group.standings] != [1, 2, 3, 4]:
            raise ValueError(f"group {group.group} must contain ranks 1 through 4")
        teams.extend(standing.team for standing in group.standings)
    if len(teams) != 48 or len(set(teams)) != 48:
        raise ValueError("final group standings must contain 48 unique teams")


def _validate_matches(data: TournamentData) -> None:
    matches_by_id = {match.match_id: match for match in data.matches}
    if set(matches_by_id) != set(range(73, 105)):
        raise ValueError("knockout match IDs must cover 73 through 104")

    actual_ids = {
        match.match_id for match in data.matches if match.result_kind == "actual"
    }
    forecast_ids = {
        match.match_id for match in data.matches if match.result_kind == "forecast"
    }
    first_forecast_id = min(forecast_ids, default=105)
    if actual_ids != set(range(73, first_forecast_id)):
        raise ValueError("actual matches must form a contiguous prefix")
    if forecast_ids != set(range(first_forecast_id, 105)):
        raise ValueError("forecast matches must follow all actual matches")

    expected_stages = {
        **{match_id: "round_of_32" for match_id in range(73, 89)},
        **{match_id: "round_of_16" for match_id in range(89, 97)},
        **{match_id: "quarterfinal" for match_id in range(97, 101)},
        101: "semifinal",
        102: "semifinal",
        103: "third_place",
        104: "final",
    }
    for match_id, expected_stage in expected_stages.items():
        if matches_by_id[match_id].stage != expected_stage:
            raise ValueError(f"match {match_id} must be stage {expected_stage}")

    for match in data.matches:
        source_slots = (
            (match.home_team, match.home_source_match_id, match.home_source_outcome),
            (match.away_team, match.away_source_match_id, match.away_source_outcome),
        )
        for team, source_match_id, source_outcome in source_slots:
            if source_match_id is None:
                continue
            source_match = matches_by_id[source_match_id]
            if source_match.status != "finished":
                if team != "TBD":
                    raise ValueError(
                        f"match {match.match_id} must use TBD for unresolved source"
                    )
                continue
            winner = _winner(source_match)
            loser = (
                source_match.away_team
                if winner == source_match.home_team
                else source_match.home_team
            )
            expected_team = winner if source_outcome == "winner" else loser
            if team == "TBD":
                continue
            if team != expected_team:
                raise ValueError(
                    f"match {match.match_id} participant does not match source result"
                )


def validate_project_data(root: Path, cutoff_at: datetime) -> TournamentData:
    data = load_tournament_data(root, cutoff_at=cutoff_at)
    _validate_groups(data)
    _validate_matches(data)

    roles = {source.role for source in data.sources}
    if roles != {"official", "secondary"}:
        raise ValueError("official and secondary sources are both required")
    if any(source.verified_at > cutoff_at for source in data.sources):
        raise ValueError("sources cannot be verified after the cutoff")

    known_source_urls = {str(source.url).rstrip("/") for source in data.sources}
    for match in data.matches:
        if match.source_url.rstrip("/") not in known_source_urls:
            raise ValueError(f"match {match.match_id} references an unknown source")
    return data


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate CupLens tournament data")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--cutoff-at", type=datetime.fromisoformat)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    cutoff_at = args.cutoff_at or datetime.now().astimezone()
    try:
        data = validate_project_data(args.root.resolve(), cutoff_at=cutoff_at)
    except (OSError, KeyError, TypeError, ValueError) as error:
        print(f"DATA INVALID: {error}", file=sys.stderr)
        return 1

    actual_matches = sum(match.result_kind == "actual" for match in data.matches)
    remaining_matches = sum(match.result_kind == "forecast" for match in data.matches)
    print(f"TEAM MAPPINGS: {len(data.team_names)}")
    print(f"ACTUAL MATCHES: {actual_matches}")
    print(f"REMAINING MATCHES: {remaining_matches}")
    print(f"SOURCES: {len(data.sources)}")
    print("DATA VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
