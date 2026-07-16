import json
from pathlib import Path
from typing import Any

from app.snapshot_service import (
    SNAPSHOT_ID_PATTERN,
    compare_snapshots as _compare_snapshot_files,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = PROJECT_ROOT / "data" / "snapshots"
MODEL_CARD_PATH = PROJECT_ROOT / "docs" / "model-card.md"


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def _read_index(snapshot_dir: Path = SNAPSHOT_DIR) -> list[dict[str, Any]]:
    index = _read_json(snapshot_dir / "index.json")
    if not isinstance(index, list):
        raise ValueError("snapshot index must contain a list")
    return index


def _load_indexed_snapshot(
    entry: dict[str, Any], snapshot_dir: Path = SNAPSHOT_DIR
) -> dict[str, Any]:
    relative_path = Path(str(entry["path"]))
    if relative_path.is_absolute() or len(relative_path.parts) != 1:
        raise ValueError("unsafe snapshot path")
    snapshot = _read_json(snapshot_dir / relative_path)
    if snapshot.get("snapshot_id") != entry.get("snapshot_id"):
        raise ValueError("snapshot ID does not match index")
    return snapshot


def load_latest_snapshot(snapshot_dir: Path = SNAPSHOT_DIR) -> dict[str, Any]:
    index = _read_index(snapshot_dir)
    if not index:
        raise FileNotFoundError("no snapshots are available")
    return _load_indexed_snapshot(index[-1], snapshot_dir)


def list_snapshots(snapshot_dir: Path = SNAPSHOT_DIR) -> list[dict[str, Any]]:
    return _read_index(snapshot_dir)


def load_snapshot(
    snapshot_id: str, snapshot_dir: Path = SNAPSHOT_DIR
) -> dict[str, Any]:
    if not SNAPSHOT_ID_PATTERN.fullmatch(snapshot_id):
        raise ValueError("invalid snapshot ID")
    for entry in _read_index(snapshot_dir):
        if entry.get("snapshot_id") == snapshot_id:
            return _load_indexed_snapshot(entry, snapshot_dir)
    raise FileNotFoundError(snapshot_id)


def _provenance(snapshot: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "snapshot_id",
        "generated_at",
        "cutoff_at",
        "model_version",
        "data_sha256",
        "random_seed",
        "iterations",
        "sources",
    )
    return {field: snapshot[field] for field in fields}


def get_current_forecast() -> dict[str, Any]:
    """Return the latest precomputed forecast without changing its values."""
    snapshot = load_latest_snapshot()
    return {
        **_provenance(snapshot),
        "team_probabilities": snapshot["team_probabilities"],
        "forecast_matches": snapshot["forecast_matches"],
    }


def get_match_prediction(match_id: int) -> dict[str, Any]:
    """Return one precomputed match prediction from the latest snapshot."""
    snapshot = load_latest_snapshot()
    for prediction in snapshot["forecast_matches"]:
        if prediction.get("match_id") == match_id:
            return {**_provenance(snapshot), "prediction": prediction}
    raise FileNotFoundError(f"match prediction {match_id}")


def compare_snapshots(
    base_snapshot_id: str, target_snapshot_id: str
) -> dict[str, Any]:
    """Return the deterministic difference and provenance of two snapshots."""
    base = load_snapshot(base_snapshot_id)
    target = load_snapshot(target_snapshot_id)
    difference = _compare_snapshot_files(
        base_snapshot_id, target_snapshot_id, SNAPSHOT_DIR
    )
    return {
        "base_snapshot_id": difference.base_snapshot_id,
        "target_snapshot_id": difference.target_snapshot_id,
        "base": _provenance(base),
        "target": _provenance(target),
        "probability_changes": difference.probability_changes,
        "added_actual_match_ids": difference.added_actual_match_ids,
    }


def get_model_card() -> dict[str, Any]:
    """Return the committed model card with the latest snapshot provenance."""
    snapshot = load_latest_snapshot()
    return {
        **_provenance(snapshot),
        "metrics": snapshot["metrics"],
        "limitations": snapshot["limitations"],
        "model_card": MODEL_CARD_PATH.read_text(encoding="utf-8"),
    }
