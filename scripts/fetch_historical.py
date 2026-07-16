import argparse
import csv
import hashlib
import io
import json
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SOURCE_ID = "historical-international-results"
SOURCE_URL = (
    "https://raw.githubusercontent.com/martj42/"
    "international_results/master/results.csv"
)
RELATIVE_DATA_PATH = "data/raw/historical_matches.csv"
REQUIRED_COLUMNS = {
    "date",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
    "tournament",
}


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_sources(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as source_file:
        value = json.load(source_file)
    if not isinstance(value, list):
        raise ValueError("data/sources.json must contain a list")
    return value


def _historical_source(sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    matches = [source for source in sources if source.get("source_id") == SOURCE_ID]
    if len(matches) > 1:
        raise ValueError(f"duplicate source record: {SOURCE_ID}")
    return matches[0] if matches else None


def _validate_csv(content: bytes) -> None:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("historical data is not UTF-8 CSV") from error
    reader = csv.DictReader(io.StringIO(text))
    columns = set(reader.fieldnames or [])
    missing = REQUIRED_COLUMNS - columns
    if missing:
        raise ValueError(f"historical CSV missing columns: {sorted(missing)}")


def _download() -> bytes:
    try:
        with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:
            return response.read()
    except (OSError, urllib.error.URLError) as error:
        raise RuntimeError(f"historical data download failed: {error}") from error


def _write_bytes_once(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_bytes(content)
    if path.exists():
        temporary_path.unlink()
        raise FileExistsError(f"refusing to overwrite existing file: {path}")
    temporary_path.replace(path)


def _write_sources(path: Path, sources: list[dict[str, Any]]) -> None:
    content = json.dumps(sources, ensure_ascii=False, indent=2) + "\n"
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(content, encoding="utf-8")
    temporary_path.replace(path)


def fetch_historical(root: Path) -> str:
    data_path = root / RELATIVE_DATA_PATH
    sources_path = root / "data/sources.json"
    sources = _read_sources(sources_path)
    source = _historical_source(sources)

    expected_hash = None
    if source is not None:
        if source.get("url") != SOURCE_URL:
            raise ValueError("historical source URL conflict")
        expected_hash = source.get("file_sha256", {}).get(RELATIVE_DATA_PATH)
        if not expected_hash:
            raise ValueError("historical source is missing its SHA-256")

    if data_path.exists():
        if expected_hash is None:
            raise ValueError("existing historical data has no source record")
        actual_hash = _sha256(data_path.read_bytes())
        if actual_hash != expected_hash:
            raise ValueError(
                f"SHA-256 conflict for {RELATIVE_DATA_PATH}: "
                f"expected {expected_hash}, got {actual_hash}"
            )
        return f"HISTORICAL DATA ALREADY VERIFIED {actual_hash}"

    content = _download()
    _validate_csv(content)
    actual_hash = _sha256(content)
    if expected_hash is not None and actual_hash != expected_hash:
        raise ValueError(
            f"downloaded SHA-256 conflict for {RELATIVE_DATA_PATH}: "
            f"expected {expected_hash}, got {actual_hash}"
        )

    _write_bytes_once(data_path, content)
    if source is None:
        retrieved_at = datetime.now(UTC).isoformat(timespec="seconds")
        sources.append(
            {
                "source_id": SOURCE_ID,
                "role": "secondary",
                "url": SOURCE_URL,
                "retrieved_at": retrieved_at,
                "verified_at": retrieved_at,
                "file_sha256": {RELATIVE_DATA_PATH: actual_hash},
            }
        )
        _write_sources(sources_path, sources)
    return f"HISTORICAL DATA DOWNLOADED {actual_hash}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    try:
        print(fetch_historical(args.root.resolve()))
    except (FileExistsError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
