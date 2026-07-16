import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.schemas import (
    GroupSummary,
    MatchRecord,
    SourceRecord,
    TournamentData,
)


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_source_hashes(root: Path, sources: list[SourceRecord]) -> None:
    verified_paths: set[str] = set()
    for source in sources:
        for relative_path, expected_hash in source.file_sha256.items():
            candidate = Path(relative_path)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError(f"unsafe source file path: {relative_path}")
            actual_hash = _sha256(root / candidate)
            if actual_hash != expected_hash:
                raise ValueError(f"SHA-256 mismatch: {relative_path}")
            verified_paths.add(candidate.as_posix())

    required_paths = {
        "data/mappings/team_names.json",
        "data/raw/groups_final.json",
        "data/raw/knockout_results.json",
    }
    missing_paths = required_paths - verified_paths
    if missing_paths:
        raise ValueError(f"missing source hashes: {sorted(missing_paths)}")


def _normalize_team(team: str, mappings: dict[str, str]) -> str:
    try:
        return mappings[team]
    except KeyError as error:
        raise ValueError(f"unmapped team name: {team}") from error


def load_tournament_data(root: Path, cutoff_at: datetime) -> TournamentData:
    sources = [
        SourceRecord.model_validate(item)
        for item in _read_json(root / "data/sources.json")
    ]
    _verify_source_hashes(root, sources)

    mappings = _read_json(root / "data/mappings/team_names.json")
    groups_payload = _read_json(root / "data/raw/groups_final.json")
    matches_payload = _read_json(root / "data/raw/knockout_results.json")

    groups: list[GroupSummary] = []
    for group_payload in groups_payload["groups"]:
        normalized_group = dict(group_payload)
        normalized_group["standings"] = [
            {**standing, "team": _normalize_team(standing["team"], mappings)}
            for standing in group_payload["standings"]
        ]
        groups.append(GroupSummary.model_validate(normalized_group))

    matches: list[MatchRecord] = []
    for match_payload in matches_payload["matches"]:
        normalized_match = {
            **match_payload,
            "home_team": _normalize_team(match_payload["home_team"], mappings),
            "away_team": _normalize_team(match_payload["away_team"], mappings),
        }
        match = MatchRecord.model_validate(normalized_match)
        if match.verified_at > cutoff_at:
            raise ValueError(f"match {match.match_id} verified after cutoff")
        if match.status == "finished" and match.kickoff_at >= cutoff_at:
            raise ValueError(f"match {match.match_id} finishes at or after cutoff")
        if match.status == "scheduled" and match.kickoff_at < cutoff_at:
            raise ValueError(f"match {match.match_id} is scheduled before cutoff")
        matches.append(match)

    match_ids = [match.match_id for match in matches]
    if len(match_ids) != len(set(match_ids)):
        raise ValueError("duplicate match IDs")
    known_match_ids = set(match_ids)
    for match in matches:
        next_match_ids = [match.next_match_id, match.loser_next_match_id]
        for next_match_id in next_match_ids:
            if next_match_id is not None and next_match_id not in known_match_ids:
                raise ValueError(f"match {match.match_id} references unknown next match")
            if next_match_id is not None and next_match_id <= match.match_id:
                raise ValueError(f"match {match.match_id} has non-forward next match")

        source_match_ids = [
            match.home_source_match_id,
            match.away_source_match_id,
        ]
        for source_match_id in source_match_ids:
            if source_match_id is not None and source_match_id not in known_match_ids:
                raise ValueError(f"match {match.match_id} references unknown source match")
            if source_match_id is not None and source_match_id >= match.match_id:
                raise ValueError(f"match {match.match_id} has non-prior source match")

    return TournamentData(
        groups=groups,
        matches=matches,
        team_names=mappings,
        sources=sources,
    )
