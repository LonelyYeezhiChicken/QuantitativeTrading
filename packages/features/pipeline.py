"""Feature Engineering Pipeline: transforms raw OHLCV into ML-ready tabular dataset."""

from typing import List, Tuple
import numpy as np
import pandas as pd
from packages.features.indicators import (
    calculate_returns,
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_atr,
)

class FeaturePipeline:
    """Builds technical and statistical features for tabular ML models."""

    def __init__(self, target_horizon: int = 3, label_threshold: float = 0.005):
        self.target_horizon = target_horizon
        self.label_threshold = label_threshold

    def build_features(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        """Construct multi-factor features from OHLCV data."""
        data = df.copy()

        # 1. Past Returns
        data = calculate_returns(data, periods=[1, 3, 6, 12, 24, 48])

        # 2. RSI (Momentum)
        data["rsi_14"] = calculate_rsi(data["close"], period=14)
        data["rsi_28"] = calculate_rsi(data["close"], period=28)

        # 3. MACD
        macd_line, macd_signal, macd_hist = calculate_macd(data["close"])
        data["macd_line"] = macd_line / data["close"]
        data["macd_signal"] = macd_signal / data["close"]
        data["macd_hist"] = macd_hist / data["close"]

        # 4. Bollinger Bands
        _, _, bb_width, bb_pct = calculate_bollinger_bands(data["close"], period=20)
        data["bb_bandwidth"] = bb_width
        data["bb_percent"] = bb_pct

        # 5. Volatility
        data["natr_14"] = calculate_atr(data, period=14)
        data["volatility_12"] = data["ret_1"].rolling(12).std()
        data["volatility_24"] = data["ret_1"].rolling(24).std()

        # 6. Moving Average Ratios
        for span in [7, 21, 50, 200]:
            ema = data["close"].ewm(span=span, adjust=False).mean()
            data[f"ema_ratio_{span}"] = (data["close"] / ema) - 1.0

        # 7. Volume Dynamics
        vol_ma = data["volume"].rolling(24).mean()
        data["volume_ratio_24"] = data["volume"] / (vol_ma + 1e-12)
        data["volume_change"] = data["volume"].pct_change()

        # 8. High-Low Spread
        data["hl_spread"] = (data["high"] - data["low"]) / data["close"]

        # Target Labeling: Future N-period return
        data["target_forward_return"] = (data["close"].shift(-self.target_horizon) - data["close"]) / data["close"]

        data["target_direction"] = np.select(
            [
                data["target_forward_return"] > self.label_threshold,
                data["target_forward_return"] < -self.label_threshold,
            ],
            [1, -1],
            default=0,
        )

        exclude_cols = {
            "timestamp", "open", "high", "low", "close", "volume",
            "target_forward_return", "target_direction"
        }
        feature_cols = [c for c in data.columns if c not in exclude_cols]

        clean_df = data.dropna().reset_index(drop=True)
        return clean_df, feature_cols
