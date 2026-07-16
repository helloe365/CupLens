from pathlib import Path


def test_compose_passes_enabled_model_and_disabled_auto_update() -> None:
    root = Path(__file__).resolve().parents[2]
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")

    assert "MODEL_VARIANT: ${MODEL_VARIANT:-dixon-coles-lightgbm-meta}" in compose
    assert "AUTO_UPDATE_ENABLED: ${AUTO_UPDATE_ENABLED:-false}" in compose
    assert "AUTO_UPDATE_SOURCE_URL: ${AUTO_UPDATE_SOURCE_URL:-}" in compose


def test_production_requirements_include_lightgbm() -> None:
    root = Path(__file__).resolve().parents[2]
    requirements = (root / "backend/requirements.txt").read_text(encoding="utf-8")

    assert "lightgbm==4.6.0" in requirements.splitlines()
