import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.fetch_current_results import AutoUpdateSettings, execute_update  # noqa: E402

CUTOFF = datetime.fromisoformat("2026-07-16T04:00:00+08:00")
CURRENT_URL = "https://official.example/schedule"
OFFICIAL_URL = "https://official.example/results"
SECONDARY_URL = "https://secondary.example/results"


def _json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _match(match_id: int, status: str, home: str, away: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "match_id": match_id,
        "stage": "semifinal",
        "kickoff_at": f"2026-07-{13 + match_id}T15:00:00-04:00",
        "home_team": home,
        "away_team": away,
        "status": status,
        "result_kind": "actual" if status == "finished" else "forecast",
        "source_url": CURRENT_URL,
        "verified_at": "2026-07-15T09:00:00+08:00",
    }
    if status == "finished":
        result.update(home_score=1, away_score=0)
    return result


def _current() -> dict[str, Any]:
    return {"matches": [_match(1, "finished", "France", "Spain"), _match(2, "scheduled", "England", "Argentina")]}


def _candidate() -> dict[str, Any]:
    result = _current()
    result["matches"][1].update(
        home_score=2,
        away_score=1,
        status="finished",
        result_kind="actual",
        source_url=OFFICIAL_URL,
        verified_at="2026-07-16T03:30:00+08:00",
    )
    return result


def _current_sources() -> list[dict[str, Any]]:
    digest = hashlib.sha256(_json(_current())).hexdigest()
    common = {
        "retrieved_at": "2026-07-15T09:00:00+08:00",
        "verified_at": "2026-07-15T09:00:00+08:00",
        "file_sha256": {"data/raw/knockout_results.json": digest},
    }
    return [
        {**common, "source_id": "old-official", "role": "official", "url": CURRENT_URL},
        {**common, "source_id": "old-secondary", "role": "secondary", "url": "https://secondary.example/schedule"},
    ]


def _candidate_sources(results: dict[str, Any]) -> list[dict[str, Any]]:
    digest = hashlib.sha256(_json(results)).hexdigest()
    prior = _current_sources()
    for source in prior:
        source["file_sha256"] = {}
    common = {
        "retrieved_at": "2026-07-16T03:35:00+08:00",
        "verified_at": "2026-07-16T03:40:00+08:00",
        "file_sha256": {"data/raw/knockout_results.json": digest},
    }
    sources = prior + [
        {**common, "source_id": "official-results", "role": "official", "url": OFFICIAL_URL},
        {**common, "source_id": "secondary-results", "role": "secondary", "url": SECONDARY_URL},
    ]
    for source in sources:
        source["file_sha256"] = dict(source["file_sha256"])
    return sources


def _bundle(results: dict[str, Any] | None = None) -> bytes:
    results = results or _candidate()
    return _json({"knockout_results": results, "sources": _candidate_sources(results)})


def _snapshot(snapshot_id: str) -> dict[str, Any]:
    return {
        "snapshot_id": snapshot_id,
        "generated_at": "2026-07-16T03:50:00+08:00",
        "cutoff_at": CUTOFF.isoformat(),
        "model_version": "elo-poisson-v1",
        "data_sha256": "a" * 64,
        "random_seed": 20260716,
        "iterations": 100,
        "sources": [],
        "actual_matches": [{"match_id": 1}, {"match_id": 2}],
        "forecast_matches": [],
        "team_probabilities": [{"team": "England", "champion_probability": 1.0, "final_probability": 1.0}],
        "metrics": {},
        "limitations": [],
    }


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "data/raw").mkdir(parents=True)
    (root / "data/snapshots").mkdir(parents=True)
    (root / "data/raw/knockout_results.json").write_bytes(_json(_current()))
    (root / "data/sources.json").write_bytes(_json(_current_sources()))
    old = _snapshot("old-snapshot")
    (root / "data/snapshots/old-snapshot.json").write_bytes(_json(old))
    (root / "data/snapshots/index.json").write_bytes(_json([{
        "snapshot_id": "old-snapshot",
        "generated_at": old["generated_at"],
        "cutoff_at": old["cutoff_at"],
        "model_version": old["model_version"],
        "path": "old-snapshot.json",
    }]))
    return root


def _settings(snapshot_id: str = "new-snapshot", enabled: bool = True) -> AutoUpdateSettings:
    return AutoUpdateSettings(enabled, "https://feed.example/results.json", snapshot_id, CUTOFF, 100, 20260716)


def _download(payload: bytes) -> Callable[[str, Path], None]:
    return lambda _url, target: target.write_bytes(payload)


def _validate(root: Path, _cutoff: datetime) -> None:
    assert json.loads((root / "data/raw/knockout_results.json").read_text())["matches"][1]["status"] == "finished"


def _build(_root: Path, snapshot_id: str, _cutoff: datetime, _iterations: int, _seed: int) -> dict[str, Any]:
    return _snapshot(snapshot_id)


def _hashes(root: Path) -> dict[str, str]:
    relative_paths = (
        "data/raw/knockout_results.json",
        "data/sources.json",
        "data/snapshots/index.json",
        "data/snapshots/old-snapshot.json",
    )
    return {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in relative_paths}


def _execute(root: Path, **overrides: Any):
    arguments: dict[str, Any] = {
        "settings": _settings(),
        "root": root,
        "dry_run": False,
        "downloader": _download(_bundle()),
        "validator": _validate,
        "snapshot_builder": _build,
    }
    arguments.update(overrides)
    return execute_update(**arguments)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data["matches"].append(_match(3, "scheduled", "Brazil", "Italy")), "match IDs"),
        (lambda data: data["matches"][1].update(home_team="Brazil"), "teams"),
        (lambda data: data["matches"][0].update(home_score=0), "finished match"),
        (
            lambda data: data["matches"][0].update(
                status="scheduled",
                result_kind="forecast",
                home_score=None,
                away_score=None,
            ),
            "finished match",
        ),
        (
            lambda data: data["matches"][1].update(
                kickoff_at="2026-07-15T16:00:00-04:00"
            ),
            "immutable fields",
        ),
        (
            lambda data: data["matches"][1].update(
                verified_at="2026-07-16T02:59:00+08:00"
            ),
            "before kickoff",
        ),
    ],
)
def test_invalid_id_team_or_score_rewrite_preserves_state(tmp_path: Path, mutate: Callable[[dict[str, Any]], None], message: str) -> None:
    root = _project(tmp_path)
    before = _hashes(root)
    candidate = _candidate()
    mutate(candidate)

    with pytest.raises(ValueError, match=message):
        _execute(root, downloader=_download(_bundle(candidate)))

    assert _hashes(root) == before
    assert not (root / "data/snapshots/new-snapshot.json").exists()


@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "conflict",
        "unverified",
        "verified-before-retrieval",
        "stale-evidence",
    ],
)
def test_missing_conflicting_or_unverified_sources_stop_update(
    tmp_path: Path,
    failure: str,
) -> None:
    root = _project(tmp_path)
    before = _hashes(root)
    candidate = _candidate()
    sources = _candidate_sources(candidate)
    if failure == "missing":
        sources = []
    elif failure == "conflict":
        sources[-1]["file_sha256"]["data/raw/knockout_results.json"] = "b" * 64
    elif failure == "unverified":
        sources[-1]["verified_at"] = "2026-07-16T04:01:00+08:00"
    elif failure == "verified-before-retrieval":
        sources[-1]["verified_at"] = "2026-07-16T03:34:00+08:00"
    else:
        sources[0]["file_sha256"]["data/raw/knockout_results.json"] = (
            hashlib.sha256(_json(candidate)).hexdigest()
        )
    payload = _json({"knockout_results": candidate, "sources": sources})

    with pytest.raises(ValueError):
        _execute(root, downloader=_download(payload))

    assert _hashes(root) == before
    assert not (root / "data/snapshots/new-snapshot.json").exists()


def test_download_interruption_preserves_state(tmp_path: Path) -> None:
    root = _project(tmp_path)
    before = _hashes(root)

    def interrupted(_url: str, target: Path) -> None:
        target.write_bytes(b'{"knockout_results":')
        raise OSError("connection interrupted")

    with pytest.raises(OSError, match="interrupted"):
        _execute(root, downloader=interrupted)

    assert _hashes(root) == before
    assert not list(root.glob(".auto-update-*"))


def test_validation_failure_preserves_data_and_latest_snapshot(tmp_path: Path) -> None:
    root = _project(tmp_path)
    before = _hashes(root)

    def reject(_root: Path, _cutoff: datetime) -> None:
        raise ValueError("candidate validation failed")

    with pytest.raises(ValueError, match="validation failed"):
        _execute(root, validator=reject)

    assert _hashes(root) == before
    assert not (root / "data/snapshots/new-snapshot.json").exists()


def test_existing_snapshot_id_is_rejected_without_overwrite(tmp_path: Path) -> None:
    root = _project(tmp_path)
    before = _hashes(root)
    with pytest.raises(FileExistsError):
        _execute(root, settings=_settings("old-snapshot"))
    assert _hashes(root) == before


def test_commit_failure_rolls_back_every_protected_file(tmp_path: Path) -> None:
    root = _project(tmp_path)
    before = _hashes(root)
    calls = 0
    from scripts.fetch_current_results import atomic_replace_bytes

    def fail_second(target: Path, content: bytes) -> None:
        nonlocal calls
        calls += 1
        atomic_replace_bytes(target, content)
        if calls == 2:
            raise OSError("injected commit failure")

    with pytest.raises(OSError, match="injected commit failure"):
        _execute(root, atomic_replace=fail_second)

    assert _hashes(root) == before
    assert not (root / "data/snapshots/new-snapshot.json").exists()


def test_default_disabled_performs_no_download_or_write(tmp_path: Path) -> None:
    root = _project(tmp_path)
    before = _hashes(root)
    called = False

    def forbidden(_url: str, _target: Path) -> None:
        nonlocal called
        called = True
        pytest.fail("disabled auto update must not access the network")

    result = _execute(root, settings=_settings(enabled=False), downloader=forbidden)

    assert result.status == "disabled"
    assert called is False
    assert _hashes(root) == before
    assert not list(root.glob(".auto-update-*"))


def test_dry_run_validates_without_changing_live_files(tmp_path: Path) -> None:
    root = _project(tmp_path)
    before = _hashes(root)
    result = _execute(root, dry_run=True)
    assert result.status == "dry-run"
    assert result.updated_match_ids == (2,)
    assert result.snapshot_id == "new-snapshot"
    assert _hashes(root) == before
    assert not (root / "data/snapshots/new-snapshot.json").exists()


def test_valid_transition_atomically_replaces_data_and_adds_snapshot(tmp_path: Path) -> None:
    root = _project(tmp_path)
    result = _execute(root)
    assert result.status == "updated"
    assert result.updated_match_ids == (2,)
    assert json.loads((root / "data/raw/knockout_results.json").read_text())["matches"][1]["status"] == "finished"
    index = json.loads((root / "data/snapshots/index.json").read_text())
    assert [item["snapshot_id"] for item in index] == ["old-snapshot", "new-snapshot"]
    assert (root / "data/snapshots/new-snapshot.json").exists()
