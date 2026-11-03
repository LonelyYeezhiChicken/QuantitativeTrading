"""Example Rule-Based / Technical Indicator Trading Models."""

from typing import Dict, List
import numpy as np
import pandas as pd
from packages.models.base import BaseTradingModel

class DualEMACrossoverModel(BaseTradingModel):
    """Traditional Trend-Following Strategy: EMA 21 / EMA 50 Crossover."""

    def __init__(self, fast_span: int = 21, slow_span: int = 50, signal_strength: float = 0.005):
        self.fast_span = fast_span
        self.slow_span = slow_span
        self.signal_strength = signal_strength

    @property
    def name(self) -> str:
        return f"DualEMA_Trend_{self.fast_span}_{self.slow_span}"

    def fit(self, df: pd.DataFrame, feature_cols: List[str], target_col: str = "target_forward_return", **kwargs) -> Dict[str, float]:
        """Rule-based models don't require training, but interface is fulfilled."""
        return {"status": "ready", "rules": f"EMA_{self.fast_span} > EMA_{self.slow_span}"}

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Predict bullish (+strength) when fast EMA > slow EMA, else flat/bearish (-strength)."""
        close = df["close"]
        ema_fast = close.ewm(span=self.fast_span, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow_span, adjust=False).mean()

        # Signal score: positive if trend is up, negative if trend is down
        signals = np.where(ema_fast > ema_slow, self.signal_strength, -self.signal_strength)
        return signals

class RSIMomentumModel(BaseTradingModel):
    """Mean Reversion Strategy based on RSI Overbought / Oversold conditions."""

    def __init__(self, lower_thresh: float = 35.0, upper_thresh: float = 65.0, signal_strength: float = 0.004):
        self.lower_thresh = lower_thresh
        self.upper_thresh = upper_thresh
        self.signal_strength = signal_strength

    @property
    def name(self) -> str:
        return f"RSI_Momentum_{int(self.lower_thresh)}_{int(self.upper_thresh)}"

    def fit(self, df: pd.DataFrame, feature_cols: List[str], target_col: str = "target_forward_return", **kwargs) -> Dict[str, float]:
        return {"status": "ready"}

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        rsi = df["rsi_14"] if "rsi_14" in df.columns else np.full(len(df), 50.0)
        # Buy when oversold, Sell/Flat when overbought
        signals = np.where(rsi < self.lower_thresh, self.signal_strength, 0.0)
        signals = np.where(rsi > self.upper_thresh, -self.signal_strength, signals)
        return signals
