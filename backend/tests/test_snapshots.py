import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.snapshot_service import compare_snapshots, record_snapshot, write_snapshot


def _snapshot(snapshot_id: str, france_probability: float) -> dict[str, object]:
    return {
        "snapshot_id": snapshot_id,
        "generated_at": "2026-07-14T12:00:00+08:00",
        "cutoff_at": "2026-07-14T11:59:00+08:00",
        "model_version": "elo-poisson-v1",
        "data_sha256": "a" * 64,
        "random_seed": 20260714,
        "iterations": 1000,
        "sources": [],
        "actual_matches": [{"match_id": 100}],
        "forecast_matches": [],
        "team_probabilities": [
            {
                "team": "France",
                "champion_probability": france_probability,
                "final_probability": 0.6,
            },
            {
                "team": "Spain",
                "champion_probability": 1.0 - france_probability,
                "final_probability": 0.4,
            },
        ],
        "metrics": {},
        "limitations": [],
    }


def test_snapshot_cannot_be_overwritten(tmp_path: Path) -> None:
    original = _snapshot("snapshot-a", 0.6)
    target = write_snapshot(original, tmp_path)
    original_bytes = target.read_bytes()

    with pytest.raises(FileExistsError):
        write_snapshot(_snapshot("snapshot-a", 0.1), tmp_path)

    assert target.read_bytes() == original_bytes
    assert not list(tmp_path.glob("*.tmp"))


def test_record_snapshot_atomically_updates_index(tmp_path: Path) -> None:
    snapshot = _snapshot("snapshot-a", 0.6)

    target = record_snapshot(snapshot, tmp_path)

    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert target == tmp_path / "snapshot-a.json"
    assert index == [
        {
            "snapshot_id": "snapshot-a",
            "generated_at": snapshot["generated_at"],
            "cutoff_at": snapshot["cutoff_at"],
            "model_version": "elo-poisson-v1",
            "path": "snapshot-a.json",
        }
    ]
    assert not list(tmp_path.glob("*.tmp"))


def test_compare_snapshots_reports_probability_and_actual_match_changes(
    tmp_path: Path,
) -> None:
    base = _snapshot("base", 0.6)
    target = _snapshot("target", 0.7)
    target["actual_matches"] = [{"match_id": 100}, {"match_id": 101}]
    record_snapshot(base, tmp_path)
    record_snapshot(target, tmp_path)

    difference = compare_snapshots("base", "target", tmp_path)

    assert difference.probability_changes["France"] == pytest.approx(0.1)
    assert difference.probability_changes["Spain"] == pytest.approx(-0.1)
    assert difference.added_actual_match_ids == (101,)


def test_formal_snapshot_rejects_sources_verified_after_cutoff(
    tmp_path: Path,
) -> None:
    project_root = Path(__file__).resolve().parents[2]
    script = project_root / "scripts/update_snapshot.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(project_root),
            "--output-dir",
            str(tmp_path / "snapshots"),
            "--snapshot-id",
            "20260713-pre-semifinals-v1",
            "--cutoff-at",
            "2026-07-13T23:59:00+08:00",
            "--iterations",
            "20000",
            "--seed",
            "20260713",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "source verified after cutoff" in result.stderr
    assert not (tmp_path / "snapshots").exists()
