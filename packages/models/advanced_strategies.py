"""Advanced & Practitioner Trading Strategy Models for Crypto Markets.

Includes:
1. FibonacciSNRModel: Support/Resistance + Fibonacci Golden Pocket (0.50 ~ 0.618) Retracement Swing Model
2. SpotMomentumPullbackModel: Spot Daemon Logic (EMA21 Dynamic Pullback + RSI Confirmation)
3. SwapMultiRegimeModel: Perpetual Futures Dual-Direction Trend Following with Dynamic Stop
4. RSIBottomHunterModel: Multi-Indicator Confirmed Deep Oversold Reversal Model
5. BollingerBreakoutModel: Volatility Expansion Band Breakout Model
"""

from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from packages.models.base import BaseTradingModel


class FibonacciSNRModel(BaseTradingModel):
    """Support/Resistance (SNR) combined with Fibonacci Retracement Golden Pocket.

    Captures 4h/1h institutional swing pullbacks into the 0.50 ~ 0.618 Golden Pocket
    in alignment with higher timeframe trend structure.
    """

    def __init__(
        self,
        swing_window: int = 48,           # 48 1h bars = 2 full days swing range (or 12 4h bars)
        fib_lower: float = 0.50,          # 50% equilibrium retracement
        fib_upper: float = 0.65,          # 61.8% ~ 65% Golden Pocket zone
        trend_filter_span: int = 50,      # Structural trend moving average filter
        signal_strength: float = 0.005,
    ):
        self.swing_window = swing_window
        self.fib_lower = fib_lower
        self.fib_upper = fib_upper
        self.trend_filter_span = trend_filter_span
        self.signal_strength = signal_strength

    @property
    def name(self) -> str:
        return f"Fibonacci_SNR_GoldenPocket_{self.swing_window}"

    def fit(self, df: pd.DataFrame, feature_cols: List[str], target_col: str = "target_forward_return", **kwargs) -> Dict[str, float]:
        return {
            "status": "ready",
            "model_type": "Fibonacci_SNR_PriceAction",
            "swing_window": float(self.swing_window),
        }

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Calculate Fib Retracement Golden Pocket entry signals."""
        close = df["close"].values
        high = df["high"].values if "high" in df.columns else close
        low = df["low"].values if "low" in df.columns else close
        n = len(df)

        signals = np.zeros(n)
        trend_ema = pd.Series(close).ewm(span=self.trend_filter_span, adjust=False).mean().values

        # Rolling Swing High and Low (SNR Structure)
        s_high = pd.Series(high).rolling(window=self.swing_window, min_periods=self.swing_window // 2).max().values
        s_low = pd.Series(low).rolling(window=self.swing_window, min_periods=self.swing_window // 2).min().values

        in_pos = 0  # 1 = Long, -1 = Short, 0 = Flat
        target_p = 0.0
        stop_p = 0.0

        for i in range(self.swing_window, n):
            h_val = s_high[i - 1]
            l_val = s_low[i - 1]
            swing_range = h_val - l_val
            c = close[i]

            if in_pos == 0:
                if swing_range <= 0 or (swing_range / max(c, 1e-4)) < 0.015:
                    continue

                cur_trend = c > trend_ema[i]

                # Bullish Golden Pocket Retracement (50% ~ 65% pullback from Swing High)
                long_pocket_top = h_val - (self.fib_lower * swing_range)
                long_pocket_bottom = h_val - (self.fib_upper * swing_range)

                # Bearish Golden Pocket Retracement (50% ~ 65% bounce from Swing Low)
                short_pocket_bottom = l_val + (self.fib_lower * swing_range)
                short_pocket_top = l_val + (self.fib_upper * swing_range)

                if cur_trend and (long_pocket_bottom <= c <= long_pocket_top):
                    # Bullish rejection confirmed (close off the lower quartile)
                    if c >= (low[i] + 0.25 * (high[i] - low[i])):
                        signals[i] = self.signal_strength
                        in_pos = 1
                        target_p = h_val * 0.995                       # Target: Retest Swing High Resistance
                        stop_p = h_val - (0.786 * swing_range)         # Stop Loss: 0.786 Deep Invalidation Level
                elif (not cur_trend) and (short_pocket_bottom <= c <= short_pocket_top):
                    # Bearish rejection confirmed (close off the upper quartile)
                    if c <= (high[i] - 0.25 * (high[i] - low[i])):
                        signals[i] = -self.signal_strength
                        in_pos = -1
                        target_p = l_val * 1.005                       # Target: Retest Swing Low Support
                        stop_p = l_val + (0.786 * swing_range)         # Stop Loss: 0.786 Deep Invalidation Level
            elif in_pos == 1:
                # Long Exit: Hit Target Resistance or Breached 0.786 Stop Loss
                if c >= target_p or c <= stop_p:
                    signals[i] = 0.0
                    in_pos = 0
                    target_p = 0.0
                    stop_p = 0.0
                else:
                    signals[i] = self.signal_strength                  # Hold Long
            elif in_pos == -1:
                # Short Exit: Hit Target Support or Breached 0.786 Stop Loss
                if c <= target_p or c >= stop_p:
                    signals[i] = 0.0
                    in_pos = 0
                    target_p = 0.0
                    stop_p = 0.0
                else:
                    signals[i] = -self.signal_strength                 # Hold Short

        return signals


class SpotMomentumPullbackModel(BaseTradingModel):
    """Spot Daemon Strategy: EMA 21 Pullback Support + RSI Exhaustion Take-Profit.

    Mirrors the production overnight spot trading bot rules with asymmetric stop-loss.
    """

    def __init__(self, ema_span: int = 21, rsi_period: int = 14, signal_strength: float = 0.005):
        self.ema_span = ema_span
        self.rsi_period = rsi_period
        self.signal_strength = signal_strength

    @property
    def name(self) -> str:
        return f"Spot_Momentum_Pullback_EMA{self.ema_span}"

    def fit(self, df: pd.DataFrame, feature_cols: List[str], target_col: str = "target_forward_return", **kwargs) -> Dict[str, float]:
        return {"status": "ready", "type": "Spot_Overnight_Bot_Logic"}

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        close = df["close"].values
        n = len(df)
        signals = np.zeros(n)

        ema = pd.Series(close).ewm(span=self.ema_span, adjust=False).mean().values
        rsi = df["rsi_14"].values if "rsi_14" in df.columns else np.full(n, 50.0)

        in_pos = False
        entry_price = 0.0

        for i in range(1, n):
            c = close[i]
            r = rsi[i]
            e = ema[i]

            if not in_pos:
                # 1. Dip support near EMA21 with RSI <= 55 OR Extreme oversold RSI < 38
                if (c >= e * 0.998 and r <= 55.0) or (r < 38.0):
                    signals[i] = self.signal_strength
                    in_pos = True
                    entry_price = c
            else:
                gain_pct = (c - entry_price) / entry_price if entry_price > 0 else 0.0
                # Take profit on RSI overbought OR hard stop loss at -1.5%
                if r >= 72.0 or gain_pct <= -0.015 or gain_pct >= 0.025:
                    signals[i] = 0.0
                    in_pos = False
                    entry_price = 0.0
                else:
                    signals[i] = self.signal_strength  # Hold position

        return signals


class SwapMultiRegimeModel(BaseTradingModel):
    """Swap Daemon Strategy: Dual-Direction Breakout with Leverage and Tight Stops.

    Mirrors the production overnight perpetual swap trading bot rules.
    """

    def __init__(self, ema_span: int = 21, signal_strength: float = 0.006):
        self.ema_span = ema_span
        self.signal_strength = signal_strength

    @property
    def name(self) -> str:
        return f"Swap_MultiRegime_LongShort_EMA{self.ema_span}"

    def fit(self, df: pd.DataFrame, feature_cols: List[str], target_col: str = "target_forward_return", **kwargs) -> Dict[str, float]:
        return {"status": "ready", "type": "Swap_Overnight_Bot_Logic"}

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        close = df["close"].values
        n = len(df)
        signals = np.zeros(n)

        ema = pd.Series(close).ewm(span=self.ema_span, adjust=False).mean().values
        rsi = df["rsi_14"].values if "rsi_14" in df.columns else np.full(n, 50.0)

        current_side = 0  # 1 = Long, -1 = Short, 0 = Flat
        entry_price = 0.0

        for i in range(1, n):
            c = close[i]
            r = rsi[i]
            e = ema[i]

            if current_side == 0:
                # Long entry: price >= EMA and RSI 45~58 OR RSI < 35
                if (c >= e and 45.0 <= r <= 58.0) or (r < 35.0):
                    signals[i] = self.signal_strength
                    current_side = 1
                    entry_price = c
                # Short entry: price < EMA*0.995 and RSI 40~48
                elif c < e * 0.995 and 40.0 <= r <= 48.0:
                    signals[i] = -self.signal_strength
                    current_side = -1
                    entry_price = c
            elif current_side == 1:
                gain_pct = (c - entry_price) / entry_price if entry_price > 0 else 0.0
                if r >= 73.0 or gain_pct <= -0.02 or gain_pct >= 0.035:
                    signals[i] = 0.0
                    current_side = 0
                    entry_price = 0.0
                else:
                    signals[i] = self.signal_strength
            elif current_side == -1:
                gain_pct = (entry_price - c) / entry_price if entry_price > 0 else 0.0
                if r <= 27.0 or gain_pct <= -0.02 or gain_pct >= 0.035:
                    signals[i] = 0.0
                    current_side = 0
                    entry_price = 0.0
                else:
                    signals[i] = -self.signal_strength

        return signals


class RSIBottomHunterModel(BaseTradingModel):
    """Multi-Confirmed Deep Oversold Reversal Model (RSI + MACD Momentum Recovery)."""

    def __init__(self, oversold_threshold: float = 30.0, exit_rsi: float = 55.0, signal_strength: float = 0.005):
        self.oversold_threshold = oversold_threshold
        self.exit_rsi = exit_rsi
        self.signal_strength = signal_strength

    @property
    def name(self) -> str:
        return f"RSI_BottomHunter_Confirmed_{int(self.oversold_threshold)}"

    def fit(self, df: pd.DataFrame, feature_cols: List[str], target_col: str = "target_forward_return", **kwargs) -> Dict[str, float]:
        return {"status": "ready"}

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        n = len(df)
        signals = np.zeros(n)
        rsi = df["rsi_14"].values if "rsi_14" in df.columns else np.full(n, 50.0)
        close = df["close"].values
        macd_hist = df["macd_hist"].values if "macd_hist" in df.columns else np.zeros(n)

        in_pos = False
        entry_price = 0.0

        for i in range(2, n):
            r = rsi[i]
            c = close[i]

            if not in_pos:
                # Deep oversold + MACD histogram curling up + price tick above previous close
                if r < self.oversold_threshold and macd_hist[i] > macd_hist[i - 1] and c > close[i - 1]:
                    signals[i] = self.signal_strength
                    in_pos = True
                    entry_price = c
            else:
                gain_pct = (c - entry_price) / entry_price if entry_price > 0 else 0.0
                if r >= self.exit_rsi or gain_pct <= -0.02:
                    signals[i] = 0.0
                    in_pos = False
                    entry_price = 0.0
                else:
                    signals[i] = self.signal_strength

        return signals


class BollingerBreakoutModel(BaseTradingModel):
    """Bollinger Band Volatility Expansion Breakout with ATR Trailing Invalidation."""

    def __init__(self, bb_period: int = 20, bb_std: float = 2.0, signal_strength: float = 0.005):
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.signal_strength = signal_strength

    @property
    def name(self) -> str:
        return f"Bollinger_Breakout_{self.bb_period}_{self.bb_std}"

    def fit(self, df: pd.DataFrame, feature_cols: List[str], target_col: str = "target_forward_return", **kwargs) -> Dict[str, float]:
        return {"status": "ready"}

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        close = df["close"]
        n = len(df)
        signals = np.zeros(n)

        ma = close.rolling(self.bb_period).mean().values
        std = close.rolling(self.bb_period).std().values
        upper = ma + (self.bb_std * std)
        lower = ma - (self.bb_std * std)
        close_arr = close.values

        in_long = False
        for i in range(self.bb_period, n):
            c = close_arr[i]
            if not in_long:
                if c > upper[i]:
                    signals[i] = self.signal_strength
                    in_long = True
            else:
                if c < ma[i]:  # Exit below middle band
                    signals[i] = 0.0
                    in_long = False
                else:
                    signals[i] = self.signal_strength

        return signals
