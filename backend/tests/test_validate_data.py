import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.data_store import load_tournament_data  # noqa: E402
from app.schemas import MatchRecord  # noqa: E402
from scripts.validate_data import _validate_matches  # noqa: E402


def test_validation_accepts_finished_semifinal_with_derived_tbd_participants() -> None:
    data = load_tournament_data(
        PROJECT_ROOT,
        cutoff_at=datetime.fromisoformat("2026-07-16T06:30:00+08:00"),
    )
    matches: list[MatchRecord] = []
    for match in data.matches:
        payload = match.model_dump(mode="json")
        if match.match_id == 101:
            payload.update(
                {
                    "home_score": 0,
                    "away_score": 2,
                    "status": "finished",
                    "result_kind": "actual",
                }
            )
        matches.append(MatchRecord.model_validate(payload))

    _validate_matches(SimpleNamespace(matches=matches))
