import pytest
from fastapi.exceptions import ResponseValidationError
from fastapi.testclient import TestClient

from app import main


EXPECTED_RESPONSE_SCHEMAS = {
    ("get", "/api/health"): "HealthResponse",
    ("get", "/api/snapshots"): "SnapshotIndexEntry",
    ("get", "/api/snapshots/latest"): "Snapshot",
    ("get", "/api/snapshots/{snapshot_id}"): "Snapshot",
    ("get", "/api/snapshots/compare"): "SnapshotComparison",
    ("get", "/api/matches/{match_id}/prediction"): "MatchPredictionResponse",
    ("post", "/api/chat"): "ChatResponse",
}


def _success_schema(method: str, path: str) -> dict[str, object]:
    return main.app.openapi()["paths"][path][method]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]


def test_public_json_routes_publish_named_response_schemas() -> None:
    for (method, path), expected in EXPECTED_RESPONSE_SCHEMAS.items():
        schema = _success_schema(method, path)
        serialized = str(schema)
        assert expected in serialized, (method, path, schema)

    chat_schema = str(main.app.openapi()["components"]["schemas"]["ChatResponse"])
    for structured_type in (
        "CurrentForecastResponse",
        "MatchPredictionResponse",
        "SnapshotComparison",
        "ModelCardResponse",
    ):
        assert structured_type in chat_schema


def test_latest_response_rejects_invalid_internal_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "load_latest_snapshot",
        lambda: {"snapshot_id": "missing-required-fields"},
    )

    with pytest.raises(ResponseValidationError):
        TestClient(main.app).get("/api/snapshots/latest")
