from pathlib import Path

from fastapi.testclient import TestClient

from app import main


def _frontend_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><title>CupLens test SPA</title>", encoding="utf-8"
    )
    (dist / "assets" / "app.js").write_text(
        "console.log('cuplens')", encoding="utf-8"
    )
    return dist


def test_spa_fallback_serves_index_for_client_route(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        main, "FRONTEND_DIST", _frontend_dist(tmp_path), raising=False
    )

    response = TestClient(main.app).get("/timeline")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "CupLens test SPA" in response.text


def test_spa_serves_built_asset(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        main, "FRONTEND_DIST", _frontend_dist(tmp_path), raising=False
    )

    response = TestClient(main.app).get("/assets/app.js")

    assert response.status_code == 200
    assert response.text == "console.log('cuplens')"


def test_unknown_api_route_does_not_fall_back_to_spa(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        main, "FRONTEND_DIST", _frontend_dist(tmp_path), raising=False
    )

    response = TestClient(main.app).get("/api/missing")

    assert response.status_code == 404
