"""Tests for Modular Rolling Backtest Evaluator with Pluggable Models."""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.data import CCXTFetcher
from packages.models.base import BaseTradingModel
from packages.models import LGBMAgent, DualEMACrossoverModel
from packages.backtest import RollingBacktestEvaluator, RollingEvaluationResult

class CustomDummyMomentumModel(BaseTradingModel):
    """Custom model created on-the-fly to verify plug-and-play capability."""
    
    @property
    def name(self) -> str:
        return "Custom_Dummy_Model"

    def fit(self, df: pd.DataFrame, feature_cols: list, target_col: str = "target_forward_return", **kwargs) -> dict:
        return {"fitted": True}

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        # Alternating buy and hold signal
        return np.where(df["close"] > df["open"], 0.005, -0.005)

def test_modular_evaluator_with_custom_model():
    """Verify that any user-defined custom model can be plugged in directly."""
    fetcher = CCXTFetcher()
    mock_df = fetcher.generate_mock_ohlcv(days=60, seed=42)

    evaluator = RollingBacktestEvaluator(initial_capital=100.0)
    custom_model = CustomDummyMomentumModel()

    res = evaluator.evaluate(
        model=custom_model,
        df=mock_df,
        symbol="BTC/USDT",
        period_description="Mock 60 Days",
        threshold=0.002,
    )

    assert isinstance(res, RollingEvaluationResult)
    assert res.model_name == "Custom_Dummy_Model"
    assert res.initial_capital == 100.0
    assert res.final_equity > 0
    assert not res.monthly_breakdown.empty
    assert "Sharpe Ratio" in res.metrics

def test_modular_evaluator_with_lgbm_and_rule_based():
    """Verify built-in LightGBM and DualEMA both evaluate successfully."""
    fetcher = CCXTFetcher()
    mock_df = fetcher.generate_mock_ohlcv(days=60, seed=99)

    evaluator = RollingBacktestEvaluator(initial_capital=100.0)

    # 1. Test Rule-based EMA
    ema_model = DualEMACrossoverModel(fast_span=12, slow_span=26)
    res_ema = evaluator.evaluate(ema_model, mock_df, train_model=False)
    assert res_ema.model_name.startswith("DualEMA_Trend")

    # 2. Test LightGBM
    lgbm_model = LGBMAgent(num_boost_round=30)
    res_lgbm = evaluator.evaluate(lgbm_model, mock_df, train_model=True)
    assert res_lgbm.model_name == "LightGBM_MultiFactor"
    assert res_lgbm.final_equity > 0
