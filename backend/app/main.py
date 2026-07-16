from pathlib import Path as FileSystemPath
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import FileResponse

from app.agent import ChatRequest, answer_question
from app.api_schemas import (
    ChatResponse,
    HealthResponse,
    MatchPredictionResponse,
    Snapshot,
    SnapshotComparison,
    SnapshotIndexEntry,
)
from app.config import APP_TITLE, APP_VERSION
from app.snapshot_service import SNAPSHOT_ID_PATTERN
from app.tools import (
    compare_snapshots,
    get_match_prediction,
    list_snapshots,
    load_latest_snapshot,
    load_snapshot,
)

app = FastAPI(title=APP_TITLE, version=APP_VERSION)
FRONTEND_DIST = FileSystemPath(__file__).resolve().parents[2] / "frontend" / "dist"


@app.get("/api/health", response_model=HealthResponse)
def health() -> dict[str, str | None]:
    try:
        snapshot_id = load_latest_snapshot()["snapshot_id"]
    except FileNotFoundError:
        snapshot_id = None
    return {"status": "ok", "snapshot_id": snapshot_id}


@app.get("/api/snapshots/latest", response_model=Snapshot)
def latest_snapshot() -> dict[str, Any]:
    try:
        return load_latest_snapshot()
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="snapshot not found") from error


@app.get("/api/snapshots", response_model=list[SnapshotIndexEntry])
def snapshots() -> list[dict[str, Any]]:
    return list_snapshots()


@app.get("/api/snapshots/compare", response_model=SnapshotComparison)
def snapshot_comparison(
    base: Annotated[str, Query(pattern=SNAPSHOT_ID_PATTERN.pattern)],
    target: Annotated[str, Query(pattern=SNAPSHOT_ID_PATTERN.pattern)],
) -> dict[str, Any]:
    try:
        return compare_snapshots(base, target)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="snapshot not found") from error


@app.get("/api/snapshots/{snapshot_id}", response_model=Snapshot)
def snapshot_by_id(
    snapshot_id: Annotated[str, Path(pattern=SNAPSHOT_ID_PATTERN.pattern)],
) -> dict[str, Any]:
    try:
        return load_snapshot(snapshot_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="snapshot not found") from error


@app.get(
    "/api/matches/{match_id}/prediction",
    response_model=MatchPredictionResponse,
)
def match_prediction(match_id: int) -> dict[str, Any]:
    try:
        return get_match_prediction(match_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="match prediction not found") from error


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> dict[str, Any]:
    return answer_question(request.question)


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str) -> FileResponse:
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="not found")

    root = FRONTEND_DIST.resolve()
    requested = (root / full_path).resolve()
    try:
        requested.relative_to(root)
    except ValueError as error:
        raise HTTPException(status_code=404, detail="not found") from error

    if requested.is_file():
        return FileResponse(requested)

    index = root / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="frontend not built")
    return FileResponse(index)
