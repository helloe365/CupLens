from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from app.elo import fit_elo
from app.model_variants import build_variant_predictor


CUTOFF = datetime(2026, 7, 14, tzinfo=timezone.utc)


def _matches() -> pd.DataFrame:
    return pd.read_csv(
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "data/raw/historical_matches.csv"
    )


def test_all_enabled_variants_return_normalized_predictions() -> None:
    matches = _matches()
    ratings = fit_elo(matches, CUTOFF)
    predictions = {
        variant: build_variant_predictor(matches, ratings, CUTOFF, variant)(
            "France", "Spain"
        )
        for variant in (
            "baseline",
            "dixon-coles",
            "lightgbm-meta",
            "dixon-coles-lightgbm-meta",
        )
    }

    for prediction in predictions.values():
        assert prediction.score_matrix.sum() == pytest.approx(1.0)
        assert prediction.home_win + prediction.draw + prediction.away_win == pytest.approx(1.0)
        assert prediction.home_advance + prediction.away_advance == pytest.approx(1.0)

    assert np.array_equal(
        predictions["baseline"].score_matrix,
        predictions["lightgbm-meta"].score_matrix,
    )
    assert np.array_equal(
        predictions["dixon-coles"].score_matrix,
        predictions["dixon-coles-lightgbm-meta"].score_matrix,
    )
    assert not np.array_equal(
        predictions["baseline"].score_matrix,
        predictions["dixon-coles"].score_matrix,
    )


def test_variant_predictor_rejects_unknown_variant() -> None:
    matches = _matches()
    ratings = fit_elo(matches, CUTOFF)

    with pytest.raises(ValueError, match="unsupported model variant"):
        build_variant_predictor(matches, ratings, CUTOFF, "unknown")
