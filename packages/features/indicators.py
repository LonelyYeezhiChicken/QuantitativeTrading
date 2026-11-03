"""Technical Indicators & Alpha Factor Calculations."""

import numpy as np
import pandas as pd

def calculate_returns(df: pd.DataFrame, periods=[1, 3, 6, 12, 24]) -> pd.DataFrame:
    """Calculate historical log returns at various lookback windows."""
    df = df.copy()
    for p in periods:
        df[f"ret_{p}"] = np.log(df["close"] / df["close"].shift(p))
    return df

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (RSI)."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / (loss + 1e-12)
    return 100 - (100 / (1 + rs))

def calculate_macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """Moving Average Convergence Divergence (MACD)."""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0):
    """Bollinger Bands %B and Bandwidth."""
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + (std * num_std)
    lower = sma - (std * num_std)
    bandwidth = (upper - lower) / (sma + 1e-12)
    percent_b = (series - lower) / (upper - lower + 1e-12)
    return upper, lower, bandwidth, percent_b

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (ATR) normalized by close price."""
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    natr = atr / (df["close"] + 1e-12)
    return natr
