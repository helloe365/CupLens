"""Application metadata and fail-closed feature flags."""

import os

APP_TITLE = "CupLens"
APP_VERSION = "0.1.0"
MODEL_VERSION_BY_VARIANT = {
    "baseline": "elo-poisson-v1",
    "dixon-coles": "elo-poisson-dixon-coles-enabled",
    "lightgbm-meta": "elo-poisson-lightgbm-meta-enabled",
    "dixon-coles-lightgbm-meta": (
        "elo-poisson-dixon-coles-lightgbm-meta-enabled"
    ),
}


def _enabled(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() == "true"


AUTO_UPDATE_ENABLED = _enabled("AUTO_UPDATE_ENABLED")
AUTO_UPDATE_SOURCE_URL = os.getenv("AUTO_UPDATE_SOURCE_URL")
MODEL_VARIANT = os.getenv(
    "MODEL_VARIANT", "dixon-coles-lightgbm-meta"
).strip().lower()
if MODEL_VARIANT not in MODEL_VERSION_BY_VARIANT:
    raise ValueError(f"unsupported MODEL_VARIANT: {MODEL_VARIANT}")
MODEL_VERSION = MODEL_VERSION_BY_VARIANT[MODEL_VARIANT]
