import importlib

import pytest

from app import config


def test_model_variant_defaults_to_combined(monkeypatch) -> None:
    monkeypatch.delenv("MODEL_VARIANT", raising=False)

    reloaded = importlib.reload(config)

    assert reloaded.MODEL_VARIANT == "dixon-coles-lightgbm-meta"
    assert (
        reloaded.MODEL_VERSION
        == "elo-poisson-dixon-coles-lightgbm-meta-enabled"
    )


@pytest.mark.parametrize(
    ("variant", "version"),
    [
        ("baseline", "elo-poisson-v1"),
        ("dixon-coles", "elo-poisson-dixon-coles-enabled"),
        ("lightgbm-meta", "elo-poisson-lightgbm-meta-enabled"),
        (
            "dixon-coles-lightgbm-meta",
            "elo-poisson-dixon-coles-lightgbm-meta-enabled",
        ),
    ],
)
def test_model_variant_accepts_all_enabled_values(
    monkeypatch, variant: str, version: str
) -> None:
    monkeypatch.setenv("MODEL_VARIANT", variant)

    reloaded = importlib.reload(config)

    assert reloaded.MODEL_VARIANT == variant
    assert reloaded.MODEL_VERSION == version


def test_model_variant_rejects_unknown_value(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_VARIANT", "unknown")

    with pytest.raises(ValueError, match="unsupported MODEL_VARIANT"):
        importlib.reload(config)

    monkeypatch.delenv("MODEL_VARIANT", raising=False)
    importlib.reload(config)
