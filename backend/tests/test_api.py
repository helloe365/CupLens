import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import tools
from app.main import app

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = PROJECT_ROOT / "data" / "snapshots"
BASE_SNAPSHOT_ID = "20260714-pre-semifinals-v1"
SNAPSHOT_ID = "20260716-post-england-argentina-v1"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def formal_snapshot() -> dict[str, object]:
    return json.loads(
        (SNAPSHOT_DIR / f"{SNAPSHOT_ID}.json").read_text(encoding="utf-8")
    )


def test_latest_snapshot_exposes_provenance(client: TestClient) -> None:
    response = client.get("/api/snapshots/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["snapshot_id"] == SNAPSHOT_ID
    assert body["cutoff_at"] == "2026-07-16T06:30:00+08:00"
    assert body["model_version"] == "elo-poisson-v1"
    assert len(body["data_sha256"]) == 64
    assert body["sources"]


def test_snapshot_routes_return_index_and_exact_snapshot(
    client: TestClient, formal_snapshot: dict[str, object]
) -> None:
    index = json.loads((SNAPSHOT_DIR / "index.json").read_text(encoding="utf-8"))

    assert client.get("/api/snapshots").json() == index
    response = client.get(f"/api/snapshots/{SNAPSHOT_ID}")

    assert response.status_code == 200
    assert response.json() == formal_snapshot


def test_compare_route_returns_provenance_and_deterministic_changes(
    client: TestClient, formal_snapshot: dict[str, object]
) -> None:
    base_snapshot = json.loads(
        (SNAPSHOT_DIR / f"{BASE_SNAPSHOT_ID}.json").read_text(encoding="utf-8")
    )
    response = client.get(
        "/api/snapshots/compare",
        params={"base": BASE_SNAPSHOT_ID, "target": SNAPSHOT_ID},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["base"]["snapshot_id"] == BASE_SNAPSHOT_ID
    assert body["base"]["data_sha256"] == base_snapshot["data_sha256"]
    assert body["base"]["sources"] == base_snapshot["sources"]
    assert body["target"]["snapshot_id"] == SNAPSHOT_ID
    assert set(body["probability_changes"]) == {
        "Argentina",
        "England",
        "France",
        "Spain",
    }
    assert body["added_actual_match_ids"] == [101, 102]


def test_match_prediction_route_preserves_snapshot_values(
    client: TestClient, formal_snapshot: dict[str, object]
) -> None:
    expected = formal_snapshot["forecast_matches"][0]

    response = client.get(f"/api/matches/{expected['match_id']}/prediction")

    assert response.status_code == 200
    body = response.json()
    assert body["snapshot_id"] == SNAPSHOT_ID
    assert body["cutoff_at"] == formal_snapshot["cutoff_at"]
    assert body["model_version"] == formal_snapshot["model_version"]
    assert body["data_sha256"] == formal_snapshot["data_sha256"]
    assert body["sources"] == formal_snapshot["sources"]
    assert body["prediction"] == expected


@pytest.mark.parametrize(
    ("path", "expected_status"),
    [
        ("/api/snapshots/missing-snapshot", 404),
        ("/api/matches/999/prediction", 404),
        ("/api/matches/not-an-integer/prediction", 422),
        (f"/api/snapshots/compare?target={SNAPSHOT_ID}", 422),
        (f"/api/snapshots/compare?base=../secret&target={SNAPSHOT_ID}", 422),
    ],
)
def test_api_uses_consistent_not_found_and_validation_errors(
    client: TestClient, path: str, expected_status: int
) -> None:
    assert client.get(path).status_code == expected_status


def test_four_agent_tools_preserve_values_and_provenance(
    formal_snapshot: dict[str, object],
) -> None:
    current = tools.get_current_forecast()
    expected_match = formal_snapshot["forecast_matches"][0]
    match = tools.get_match_prediction(expected_match["match_id"])
    difference = tools.compare_snapshots(BASE_SNAPSHOT_ID, SNAPSHOT_ID)
    model_card = tools.get_model_card()

    assert current["team_probabilities"] == formal_snapshot["team_probabilities"]
    assert current["forecast_matches"] == formal_snapshot["forecast_matches"]
    assert match["prediction"] == expected_match
    assert difference["target"]["sources"] == formal_snapshot["sources"]
    assert difference["target"]["data_sha256"] == formal_snapshot["data_sha256"]
    assert model_card["metrics"] == formal_snapshot["metrics"]
    assert model_card["limitations"] == formal_snapshot["limitations"]
    assert "Elo" in model_card["model_card"]

    for result in (current, match, model_card):
        assert result["snapshot_id"] == SNAPSHOT_ID
        assert result["cutoff_at"] == formal_snapshot["cutoff_at"]
        assert result["model_version"] == formal_snapshot["model_version"]
        assert result["data_sha256"] == formal_snapshot["data_sha256"]
        assert result["sources"] == formal_snapshot["sources"]


def test_api_and_tools_do_not_modify_snapshot_files(client: TestClient) -> None:
    before = {path.name: path.read_bytes() for path in SNAPSHOT_DIR.iterdir()}

    assert client.get("/api/snapshots").status_code == 200
    assert client.get("/api/snapshots/latest").status_code == 200
    assert client.get(f"/api/snapshots/{SNAPSHOT_ID}").status_code == 200
    assert client.get(f"/api/matches/103/prediction").status_code == 200
    tools.get_current_forecast()
    tools.get_match_prediction(103)
    tools.compare_snapshots(BASE_SNAPSHOT_ID, SNAPSHOT_ID)
    tools.get_model_card()

    after = {path.name: path.read_bytes() for path in SNAPSHOT_DIR.iterdir()}
    assert after == before
