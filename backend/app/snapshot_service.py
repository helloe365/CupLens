import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SNAPSHOT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class SnapshotDiff:
    base_snapshot_id: str
    target_snapshot_id: str
    probability_changes: dict[str, float]
    added_actual_match_ids: tuple[int, ...]


def _validate_snapshot(snapshot: dict[str, Any]) -> str:
    required_fields = {
        "snapshot_id",
        "generated_at",
        "cutoff_at",
        "model_version",
        "data_sha256",
        "random_seed",
        "iterations",
        "sources",
        "actual_matches",
        "forecast_matches",
        "team_probabilities",
        "metrics",
        "limitations",
    }
    missing_fields = required_fields - set(snapshot)
    if missing_fields:
        raise ValueError(f"snapshot missing fields: {sorted(missing_fields)}")
    snapshot_id = str(snapshot["snapshot_id"])
    if not SNAPSHOT_ID_PATTERN.fullmatch(snapshot_id):
        raise ValueError("invalid snapshot ID")
    data_sha256 = str(snapshot["data_sha256"])
    if not re.fullmatch(r"[0-9a-f]{64}", data_sha256):
        raise ValueError("data_sha256 must be a lowercase SHA-256")
    iterations = snapshot["iterations"]
    if not isinstance(iterations, int) or iterations <= 0:
        raise ValueError("iterations must be a positive integer")

    champion_probabilities = [
        float(item["champion_probability"])
        for item in snapshot["team_probabilities"]
    ]
    if not champion_probabilities or not all(
        math.isfinite(value) and 0.0 <= value <= 1.0
        for value in champion_probabilities
    ):
        raise ValueError("champion probabilities must be finite and bounded")
    if not math.isclose(sum(champion_probabilities), 1.0, abs_tol=1e-12):
        raise ValueError("champion probabilities must sum to one")
    return snapshot_id


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _exclusive_atomic_write(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.stem}-",
        suffix=".tmp",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.link(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_replace(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.stem}-",
        suffix=".tmp",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def write_snapshot(snapshot: dict[str, Any], output_dir: Path) -> Path:
    snapshot_id = _validate_snapshot(snapshot)
    target = output_dir / f"{snapshot_id}.json"
    _exclusive_atomic_write(target, _canonical_json(snapshot))
    return target


def _read_index(output_dir: Path) -> list[dict[str, Any]]:
    index_path = output_dir / "index.json"
    if not index_path.exists():
        return []
    with index_path.open(encoding="utf-8") as index_file:
        index = json.load(index_file)
    if not isinstance(index, list):
        raise ValueError("snapshot index must contain a list")
    return index


def record_snapshot(snapshot: dict[str, Any], output_dir: Path) -> Path:
    snapshot_id = _validate_snapshot(snapshot)
    index = _read_index(output_dir)
    if any(item.get("snapshot_id") == snapshot_id for item in index):
        raise FileExistsError(output_dir / f"{snapshot_id}.json")

    target = write_snapshot(snapshot, output_dir)
    index.append(
        {
            "snapshot_id": snapshot_id,
            "generated_at": snapshot["generated_at"],
            "cutoff_at": snapshot["cutoff_at"],
            "model_version": snapshot["model_version"],
            "path": target.name,
        }
    )
    _atomic_replace(output_dir / "index.json", _canonical_json(index))
    return target


def _load_snapshot(snapshot_id: str, output_dir: Path) -> dict[str, Any]:
    if not SNAPSHOT_ID_PATTERN.fullmatch(snapshot_id):
        raise ValueError("invalid snapshot ID")
    with (output_dir / f"{snapshot_id}.json").open(encoding="utf-8") as source:
        return json.load(source)


def _champion_probabilities(snapshot: dict[str, Any]) -> dict[str, float]:
    return {
        str(item["team"]): float(item["champion_probability"])
        for item in snapshot["team_probabilities"]
    }


def compare_snapshots(
    base_snapshot_id: str,
    target_snapshot_id: str,
    output_dir: Path,
) -> SnapshotDiff:
    base = _load_snapshot(base_snapshot_id, output_dir)
    target = _load_snapshot(target_snapshot_id, output_dir)
    base_probabilities = _champion_probabilities(base)
    target_probabilities = _champion_probabilities(target)
    teams = sorted(set(base_probabilities) | set(target_probabilities))
    probability_changes = {
        team: target_probabilities.get(team, 0.0)
        - base_probabilities.get(team, 0.0)
        for team in teams
    }
    base_actual_ids = {int(item["match_id"]) for item in base["actual_matches"]}
    target_actual_ids = {int(item["match_id"]) for item in target["actual_matches"]}
    return SnapshotDiff(
        base_snapshot_id=base_snapshot_id,
        target_snapshot_id=target_snapshot_id,
        probability_changes=probability_changes,
        added_actual_match_ids=tuple(sorted(target_actual_ids - base_actual_ids)),
    )
