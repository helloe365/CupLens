import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.data_store import load_tournament_data
from app.schemas import MatchRecord, SourceRecord


def write_json(path: Path, value: object) -> str:
    content = json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_finished_match_requires_score_and_actual_kind() -> None:
    with pytest.raises(ValidationError):
        MatchRecord(
            match_id=101,
            stage="semifinal",
            kickoff_at="2026-07-14T15:00:00-04:00",
            home_team="France",
            away_team="Spain",
            status="finished",
            result_kind="forecast",
            source_url="https://www.fifa.com/",
            verified_at="2026-07-13T00:00:00+08:00",
        )


def test_match_timestamps_must_include_a_timezone() -> None:
    with pytest.raises(ValidationError):
        MatchRecord(
            match_id=101,
            stage="semifinal",
            kickoff_at="2026-07-14T15:00:00",
            home_team="France",
            away_team="Spain",
            status="scheduled",
            result_kind="forecast",
            source_url="https://www.fifa.com/",
            verified_at="2026-07-13T00:00:00+08:00",
        )


def test_source_hashes_must_be_lowercase_sha256() -> None:
    with pytest.raises(ValidationError):
        SourceRecord(
            source_id="fifa",
            role="official",
            url="https://www.fifa.com/",
            retrieved_at="2026-07-13T00:00:00+08:00",
            verified_at="2026-07-13T00:00:00+08:00",
            file_sha256={"data/raw/groups_final.json": "not-a-sha256"},
        )


def test_finished_match_rejects_negative_scores() -> None:
    with pytest.raises(ValidationError):
        MatchRecord(
            match_id=100,
            stage="quarterfinal",
            kickoff_at="2026-07-11T21:00:00-04:00",
            home_team="Argentina",
            away_team="Switzerland",
            home_score=-1,
            away_score=0,
            status="finished",
            result_kind="actual",
            source_url="https://www.fifa.com/",
            verified_at="2026-07-13T00:00:00+08:00",
        )


def test_scheduled_match_rejects_scores() -> None:
    with pytest.raises(ValidationError):
        MatchRecord(
            match_id=101,
            stage="semifinal",
            kickoff_at="2026-07-14T15:00:00-04:00",
            home_team="France",
            away_team="Spain",
            home_score=0,
            away_score=0,
            status="scheduled",
            result_kind="forecast",
            source_url="https://www.fifa.com/",
            verified_at="2026-07-13T00:00:00+08:00",
        )


def test_penalty_shootout_requires_both_penalty_scores() -> None:
    with pytest.raises(ValidationError):
        MatchRecord(
            match_id=74,
            stage="round_of_32",
            kickoff_at="2026-06-29T12:00:00-04:00",
            home_team="Germany",
            away_team="Paraguay",
            home_score=1,
            away_score=1,
            home_penalty_score=3,
            status="finished",
            result_kind="actual",
            source_url="https://www.fifa.com/",
            verified_at="2026-07-13T00:00:00+08:00",
        )


def test_unresolved_match_uses_explicit_source_matches() -> None:
    match = MatchRecord(
        match_id=103,
        stage="third_place",
        kickoff_at="2026-07-18T17:00:00-04:00",
        home_team="TBD",
        away_team="TBD",
        status="scheduled",
        result_kind="forecast",
        home_source_match_id=101,
        home_source_outcome="loser",
        away_source_match_id=102,
        away_source_outcome="loser",
        source_url="https://www.fifa.com/",
        verified_at="2026-07-13T00:00:00+08:00",
    )

    assert match.home_source_match_id == 101
    assert match.home_source_outcome == "loser"
    assert match.away_source_match_id == 102
    assert match.away_source_outcome == "loser"

    semifinal = MatchRecord(
        match_id=101,
        stage="semifinal",
        kickoff_at="2026-07-14T15:00:00-04:00",
        home_team="France",
        away_team="Spain",
        status="scheduled",
        result_kind="forecast",
        next_match_id=104,
        loser_next_match_id=103,
        source_url="https://www.fifa.com/",
        verified_at="2026-07-13T00:00:00+08:00",
    )

    assert semifinal.next_match_id == 104
    assert semifinal.loser_next_match_id == 103


def test_load_tournament_data_normalizes_teams_and_verifies_hashes(
    tmp_path: Path,
) -> None:
    source_url = "https://www.fifa.com/en/articles/knockout-stage-match-schedule-bracket"
    verified_at = "2026-07-13T00:00:00+00:00"
    groups_hash = write_json(
        tmp_path / "data/raw/groups_final.json",
        {
            "groups": [
                {
                    "group": "A",
                    "standings": [
                        {"rank": 1, "team": "France"},
                        {"rank": 2, "team": "España"},
                    ],
                }
            ]
        },
    )
    matches_hash = write_json(
        tmp_path / "data/raw/knockout_results.json",
        {
            "matches": [
                {
                    "match_id": 100,
                    "stage": "quarterfinal",
                    "kickoff_at": "2026-07-11T21:00:00-04:00",
                    "home_team": "France",
                    "away_team": "España",
                    "home_score": 2,
                    "away_score": 1,
                    "status": "finished",
                    "result_kind": "actual",
                    "next_match_id": 101,
                    "source_url": source_url,
                    "verified_at": verified_at,
                },
                {
                    "match_id": 101,
                    "stage": "semifinal",
                    "kickoff_at": "2026-07-14T15:00:00-04:00",
                    "home_team": "France",
                    "away_team": "España",
                    "status": "scheduled",
                    "result_kind": "forecast",
                    "source_url": source_url,
                    "verified_at": verified_at,
                },
            ]
        },
    )
    mappings_hash = write_json(
        tmp_path / "data/mappings/team_names.json",
        {"España": "Spain", "France": "France", "Spain": "Spain"},
    )
    write_json(
        tmp_path / "data/sources.json",
        [
            {
                "source_id": "fifa-knockout",
                "role": "official",
                "url": source_url,
                "retrieved_at": verified_at,
                "verified_at": verified_at,
                "file_sha256": {
                    "data/mappings/team_names.json": mappings_hash,
                    "data/raw/groups_final.json": groups_hash,
                    "data/raw/knockout_results.json": matches_hash,
                },
            }
        ],
    )

    data = load_tournament_data(
        tmp_path,
        cutoff_at=datetime(2026, 7, 13, 23, 59, tzinfo=UTC),
    )

    assert data.groups[0].standings[1].team == "Spain"
    assert data.matches[0].away_team == "Spain"
    assert data.matches[1].result_kind == "forecast"


def test_validate_data_script_reports_verified_counts() -> None:
    project_root = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [
            sys.executable,
            str(project_root / "scripts/validate_data.py"),
            "--cutoff-at",
            "2026-07-16T06:30:00+08:00",
        ],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "TEAM MAPPINGS: 59" in result.stdout
    assert "ACTUAL MATCHES: 30" in result.stdout
    assert "REMAINING MATCHES: 2" in result.stdout
    assert "SOURCES: 10" in result.stdout
    assert result.stdout.rstrip().endswith("DATA VALID")
