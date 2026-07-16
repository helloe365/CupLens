"""Fail-closed updater for a curated results bundle.

The downloaded JSON object must contain ``knockout_results`` in the project's
raw-data shape and ``sources`` as the complete SourceRecord manifest.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.config import AUTO_UPDATE_ENABLED, AUTO_UPDATE_SOURCE_URL  # noqa: E402
from app.schemas import MatchRecord, SourceRecord  # noqa: E402
from app.snapshot_service import SNAPSHOT_ID_PATTERN  # noqa: E402
from scripts.update_snapshot import build_snapshot, create_snapshot  # noqa: E402
from scripts.validate_data import validate_project_data  # noqa: E402

RESULTS_PATH = Path("data/raw/knockout_results.json")
SOURCES_PATH = Path("data/sources.json")
INDEX_PATH = Path("data/snapshots/index.json")

Downloader = Callable[[str, Path], None]
Validator = Callable[[Path, datetime], Any]
SnapshotBuilder = Callable[[Path, str, datetime, int, int], dict[str, Any]]
AtomicReplace = Callable[[Path, bytes], None]


@dataclass(frozen=True)
class AutoUpdateSettings:
    enabled: bool
    source_url: str | None
    snapshot_id: str | None
    cutoff_at: datetime | None
    iterations: int
    seed: int


@dataclass(frozen=True)
class UpdateResult:
    status: str
    snapshot_id: str | None
    updated_match_ids: tuple[int, ...]


def canonical_json(value: Any) -> bytes:
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


def atomic_replace_bytes(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.stem}-",
        suffix=".tmp",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _exclusive_write(target: Path, content: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.stem}-",
        suffix=".tmp",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    linked = False
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, target)
        linked = True
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except BaseException:
            if linked:
                target.unlink(missing_ok=True)
            raise


def download_to_path(source_url: str, target: Path) -> None:
    request = urllib.request.Request(
        source_url,
        headers={"User-Agent": "CupLens atomic result updater/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        expected_length = response.headers.get("Content-Length")
        received = 0
        with target.open("wb") as output:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                received += len(chunk)
            output.flush()
            os.fsync(output.fileno())
    if expected_length is not None and received != int(expected_length):
        raise OSError(
            f"download interrupted: expected {expected_length} bytes, got {received}"
        )


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def _records_by_id(payload: Any, label: str) -> dict[int, MatchRecord]:
    if not isinstance(payload, dict) or not isinstance(payload.get("matches"), list):
        raise ValueError(f"{label} must contain a matches list")
    records = [MatchRecord.model_validate(item) for item in payload["matches"]]
    by_id = {record.match_id: record for record in records}
    if len(records) != len(by_id):
        raise ValueError(f"{label} contains duplicate match IDs")
    return by_id


def validate_results_transition(
    current_payload: Any,
    candidate_payload: Any,
    cutoff_at: datetime,
) -> tuple[int, ...]:
    current = _records_by_id(current_payload, "current results")
    candidate = _records_by_id(candidate_payload, "candidate results")
    if set(current) != set(candidate):
        raise ValueError("candidate match IDs differ from current match IDs")

    immutable_fields = (
        "stage",
        "kickoff_at",
        "home_team",
        "away_team",
        "next_match_id",
        "loser_next_match_id",
        "home_source_match_id",
        "home_source_outcome",
        "away_source_match_id",
        "away_source_outcome",
    )
    updated: list[int] = []
    for match_id in sorted(current):
        existing = current[match_id]
        incoming = candidate[match_id]
        if (existing.home_team, existing.away_team) != (
            incoming.home_team,
            incoming.away_team,
        ):
            raise ValueError(f"match {match_id} teams changed")
        if any(
            getattr(existing, field) != getattr(incoming, field)
            for field in immutable_fields
        ):
            raise ValueError(f"match {match_id} immutable fields changed")

        if existing.status == "finished":
            if existing != incoming:
                raise ValueError(f"finished match {match_id} was modified")
            continue
        if incoming.status == "scheduled":
            if existing != incoming:
                raise ValueError(
                    f"match {match_id} changed without scheduled -> finished"
                )
            continue
        if incoming.status != "finished" or incoming.result_kind != "actual":
            raise ValueError(f"match {match_id} is not a valid finished result")
        if incoming.verified_at <= existing.verified_at:
            raise ValueError(f"match {match_id} result is not newly verified")
        if incoming.verified_at > cutoff_at:
            raise ValueError(f"match {match_id} is verified after the cutoff")
        if incoming.kickoff_at >= cutoff_at:
            raise ValueError(f"match {match_id} finishes at or after the cutoff")
        if incoming.verified_at <= incoming.kickoff_at:
            raise ValueError(f"match {match_id} was verified before kickoff")
        updated.append(match_id)

    if not updated:
        raise ValueError("candidate contains no new finished matches")
    return tuple(updated)


def _validate_sources(
    sources_payload: Any,
    current_sources_payload: Any,
    results_bytes: bytes,
    candidate: dict[int, MatchRecord],
    updated_match_ids: tuple[int, ...],
    cutoff_at: datetime,
) -> None:
    if not isinstance(sources_payload, list) or not sources_payload:
        raise ValueError("candidate sources are missing")
    sources = [SourceRecord.model_validate(item) for item in sources_payload]
    if len({source.source_id for source in sources}) != len(sources):
        raise ValueError("candidate sources contain duplicate source IDs")
    if any(
        source.retrieved_at > cutoff_at or source.verified_at > cutoff_at
        for source in sources
    ):
        raise ValueError("candidate source is unverified at the cutoff")
    if any(source.verified_at < source.retrieved_at for source in sources):
        raise ValueError("candidate source was verified before retrieval")

    if not isinstance(current_sources_payload, list):
        raise ValueError("current sources must contain a list")
    current_sources = [
        SourceRecord.model_validate(item) for item in current_sources_payload
    ]
    incoming_by_id = {source.source_id: source for source in sources}
    current_source_ids = {source.source_id for source in current_sources}
    relative_path = RESULTS_PATH.as_posix()
    for current_source in current_sources:
        incoming = incoming_by_id.get(current_source.source_id)
        if incoming is None:
            raise ValueError(
                f"candidate sources dropped source {current_source.source_id}"
            )
        current_hashes = dict(current_source.file_sha256)
        incoming_hashes = dict(incoming.file_sha256)
        current_hashes.pop(relative_path, None)
        incoming_hashes.pop(relative_path, None)
        if (
            incoming.role != current_source.role
            or incoming.url != current_source.url
            or incoming.retrieved_at != current_source.retrieved_at
            or incoming.verified_at != current_source.verified_at
            or incoming_hashes != current_hashes
        ):
            raise ValueError(
                f"candidate sources rewrote source history {current_source.source_id}"
            )
        if relative_path in incoming.file_sha256:
            raise ValueError(
                f"candidate sources reused stale evidence {current_source.source_id}"
            )

    expected_hash = hashlib.sha256(results_bytes).hexdigest()
    evidence = [
        source
        for source in sources
        if source.source_id not in current_source_ids
        and relative_path in source.file_sha256
    ]
    if not evidence:
        raise ValueError("candidate sources do not verify the results file")
    if any(source.file_sha256[relative_path] != expected_hash for source in evidence):
        raise ValueError("candidate sources conflict on the results hash")
    if {source.role for source in evidence} != {"official", "secondary"}:
        raise ValueError("candidate results require official and secondary verification")

    latest_result_verification = max(
        candidate[match_id].verified_at for match_id in updated_match_ids
    )
    if any(source.verified_at < latest_result_verification for source in evidence):
        raise ValueError("candidate result sources are not fully verified")
    known_urls = {str(source.url).rstrip("/") for source in evidence}
    for match_id in updated_match_ids:
        if candidate[match_id].source_url.rstrip("/") not in known_urls:
            raise ValueError(f"match {match_id} references an unverified source")


def _parse_bundle(
    path: Path,
    current_payload: Any,
    current_sources_payload: Any,
    cutoff_at: datetime,
) -> tuple[bytes, bytes, tuple[int, ...]]:
    bundle = _load_json(path)
    if not isinstance(bundle, dict):
        raise ValueError("downloaded update bundle must be an object")
    if "knockout_results" not in bundle or "sources" not in bundle:
        raise ValueError("downloaded update bundle is missing results or sources")
    candidate_payload = bundle["knockout_results"]
    updated_match_ids = validate_results_transition(
        current_payload,
        candidate_payload,
        cutoff_at,
    )
    candidate = _records_by_id(candidate_payload, "candidate results")
    results_bytes = canonical_json(candidate_payload)
    _validate_sources(
        bundle["sources"],
        current_sources_payload,
        results_bytes,
        candidate,
        updated_match_ids,
        cutoff_at,
    )
    return results_bytes, canonical_json(bundle["sources"]), updated_match_ids


def _ensure_snapshot_available(root: Path, snapshot_id: str) -> None:
    if not SNAPSHOT_ID_PATTERN.fullmatch(snapshot_id):
        raise ValueError("invalid snapshot ID")
    target = root / "data/snapshots" / f"{snapshot_id}.json"
    if target.exists():
        raise FileExistsError(target)
    index = _load_json(root / INDEX_PATH)
    if not isinstance(index, list):
        raise ValueError("snapshot index must contain a list")
    if any(item.get("snapshot_id") == snapshot_id for item in index):
        raise FileExistsError(target)


def _stage_project(root: Path, stage_root: Path) -> None:
    shutil.copytree(root / "data", stage_root / "data")
    baseline = root / "docs/backtest-baseline.json"
    if baseline.exists():
        (stage_root / "docs").mkdir(parents=True)
        shutil.copy2(baseline, stage_root / "docs/backtest-baseline.json")


def _commit_staged_update(
    root: Path,
    stage_root: Path,
    snapshot_id: str,
    atomic_replace: AtomicReplace,
) -> None:
    live_snapshot = root / "data/snapshots" / f"{snapshot_id}.json"
    staged_snapshot = stage_root / "data/snapshots" / f"{snapshot_id}.json"
    replacement_paths = (RESULTS_PATH, SOURCES_PATH, INDEX_PATH)
    original = {path: (root / path).read_bytes() for path in replacement_paths}
    replaced: list[Path] = []
    snapshot_created = False
    try:
        _exclusive_write(live_snapshot, staged_snapshot.read_bytes())
        snapshot_created = True
        for relative_path in replacement_paths:
            replaced.append(relative_path)
            atomic_replace(
                root / relative_path,
                (stage_root / relative_path).read_bytes(),
            )
    except BaseException:
        for relative_path in reversed(replaced):
            atomic_replace_bytes(root / relative_path, original[relative_path])
        if snapshot_created:
            live_snapshot.unlink(missing_ok=True)
        raise


def _validated_settings(settings: AutoUpdateSettings) -> tuple[str, str, datetime]:
    if not settings.source_url:
        raise ValueError("AUTO_UPDATE_SOURCE_URL is required when enabled")
    if not settings.snapshot_id:
        raise ValueError("snapshot ID is required when enabled")
    if settings.cutoff_at is None:
        raise ValueError("cutoff is required when enabled")
    if settings.cutoff_at.tzinfo is None or settings.cutoff_at.utcoffset() is None:
        raise ValueError("cutoff must include a timezone")
    if settings.iterations <= 0:
        raise ValueError("iterations must be positive")
    return settings.source_url, settings.snapshot_id, settings.cutoff_at


def execute_update(
    settings: AutoUpdateSettings,
    root: Path,
    dry_run: bool,
    *,
    downloader: Downloader = download_to_path,
    validator: Validator = validate_project_data,
    snapshot_builder: SnapshotBuilder = build_snapshot,
    atomic_replace: AtomicReplace = atomic_replace_bytes,
) -> UpdateResult:
    root = root.resolve()
    if not settings.enabled:
        return UpdateResult("disabled", settings.snapshot_id, ())

    source_url, snapshot_id, cutoff_at = _validated_settings(settings)
    _ensure_snapshot_available(root, snapshot_id)
    current_payload = _load_json(root / RESULTS_PATH)
    current_sources_payload = _load_json(root / SOURCES_PATH)

    with tempfile.TemporaryDirectory(prefix=".auto-update-", dir=root) as temporary:
        temporary_root = Path(temporary)
        download_path = temporary_root / "download.json"
        downloader(source_url, download_path)
        results_bytes, sources_bytes, updated_match_ids = _parse_bundle(
            download_path,
            current_payload,
            current_sources_payload,
            cutoff_at,
        )

        stage_root = temporary_root / "project"
        _stage_project(root, stage_root)
        (stage_root / RESULTS_PATH).write_bytes(results_bytes)
        (stage_root / SOURCES_PATH).write_bytes(sources_bytes)
        validator(stage_root, cutoff_at)
        create_snapshot(
            stage_root,
            stage_root / "data/snapshots",
            snapshot_id,
            cutoff_at,
            settings.iterations,
            settings.seed,
            builder=snapshot_builder,
        )

        if dry_run:
            return UpdateResult("dry-run", snapshot_id, updated_match_ids)
        _commit_staged_update(root, stage_root, snapshot_id, atomic_replace)
        return UpdateResult("updated", snapshot_id, updated_match_ids)


def _aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch, validate, and atomically stage current results"
    )
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--source-url", default=AUTO_UPDATE_SOURCE_URL)
    parser.add_argument("--snapshot-id")
    parser.add_argument("--cutoff-at", type=_aware_datetime)
    parser.add_argument("--iterations", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=20260715)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    settings = AutoUpdateSettings(
        enabled=AUTO_UPDATE_ENABLED,
        source_url=args.source_url,
        snapshot_id=args.snapshot_id,
        cutoff_at=args.cutoff_at,
        iterations=args.iterations,
        seed=args.seed,
    )
    try:
        result = execute_update(settings, args.root, args.dry_run)
    except (OSError, KeyError, TypeError, ValueError) as error:
        print(f"AUTO UPDATE BLOCKED: {error}", file=sys.stderr)
        return 1

    if result.status == "disabled":
        print("AUTO UPDATE DISABLED: no network request or file write performed")
    elif result.status == "dry-run":
        print(
            "AUTO UPDATE DRY RUN VALID: "
            f"matches={list(result.updated_match_ids)} snapshot={result.snapshot_id}"
        )
    else:
        print(
            "AUTO UPDATE COMPLETE: "
            f"matches={list(result.updated_match_ids)} snapshot={result.snapshot_id}"
        )
        print("MANUAL VERIFICATION REQUIRED BEFORE FORMAL SUBMISSION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
