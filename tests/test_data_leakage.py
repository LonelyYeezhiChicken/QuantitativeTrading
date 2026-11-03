"""Test data leakage prevention and feature integrity."""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent))

from packages.features import FeaturePipeline
from packages.data import CCXTFetcher

def test_feature_data_leakage():
    """Verify that changing future data does not affect past feature values."""
    fetcher = CCXTFetcher()
    df1 = fetcher.generate_mock_ohlcv(days=30, seed=100)
    df2 = df1.copy()

    # Modify the last 5 rows of df2 (simulating future market price changes)
    df2.iloc[-5:, df2.columns.get_loc("close")] *= 2.0
    df2.iloc[-5:, df2.columns.get_loc("high")] *= 2.0

    pipeline = FeaturePipeline(target_horizon=3)
    feat1, feature_cols = pipeline.build_features(df1)
    feat2, _ = pipeline.build_features(df2)

    # Cutoff row: any row strictly before the modified region (accounting for target_horizon shift)
    safe_cutoff = len(feat1) - 10

    # Ensure all features computed before the perturbation are bit-for-bit IDENTICAL
    for col in feature_cols:
        val1 = feat1[col].iloc[:safe_cutoff].values
        val2 = feat2[col].iloc[:safe_cutoff].values
        np.testing.assert_allclose(
            val1,
            val2,
            rtol=1e-5,
            atol=1e-8,
            err_msg=f"Data leakage detected in feature '{col}'! Future modifications altered past values.",
        )
