"""Unit tests for TypeSafeAIAgent."""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.data import CCXTFetcher
from packages.features import FeaturePipeline
from packages.models import TypeSafeAIAgent

def test_typesafe_predict_shape_and_bounds():
    """Verify predict output array has correct dimensions and bounded values."""
    fetcher = CCXTFetcher()
    mock_df = fetcher.generate_mock_ohlcv(days=20, seed=55)
    pipeline = FeaturePipeline(target_horizon=3)
    feat_df, _ = pipeline.build_features(mock_df)

    agent = TypeSafeAIAgent(signal_magnitude=0.005)
    preds = agent.predict(feat_df)

    assert isinstance(preds, np.ndarray)
    assert len(preds) == len(feat_df)
    assert np.all(preds >= -0.005)
    assert np.all(preds <= 0.005)

def test_typesafe_mock_inference_scenarios():
    """Verify decision outputs across oversold vs overbought states."""
    agent = TypeSafeAIAgent()

    # Oversold state
    res_oversold = agent._mock_inference("RSI(14): 25.0 | 1h_Return: -2.0% | EMA_200_Trend: +1.0% | Vol_Multiplier: 1.5x")
    assert res_oversold["action"]["choice"] == "BUY"
    assert res_oversold["is_high_conviction"]["noul"] > 0.70

    # Overbought state
    res_overbought = agent._mock_inference("RSI(14): 75.0 | 1h_Return: +3.0% | EMA_200_Trend: -2.0% | Vol_Multiplier: 1.0x")
    assert res_overbought["action"]["choice"] == "SELL"

    # Neutral state
    res_neutral = agent._mock_inference("RSI(14): 50.0 | 1h_Return: +0.0% | EMA_200_Trend: 0.0% | Vol_Multiplier: 0.9x")
    assert res_neutral["action"]["choice"] == "HOLD"
