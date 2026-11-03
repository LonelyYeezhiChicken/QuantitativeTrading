"""CCXT Data Fetcher: Fetches historical OHLCV candles from crypto exchanges."""

import time
from datetime import datetime, timezone
from typing import Optional
import numpy as np
import pandas as pd
import ccxt

class CCXTFetcher:
    """Fetches OHLCV market data via CCXT with automatic pagination and rate limit handling."""

    def __init__(self, exchange_id: str = "binance", enable_rate_limit: bool = True):
        self.exchange_id = exchange_id.lower()
        exchange_class = getattr(ccxt, self.exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"Exchange '{exchange_id}' is not supported by ccxt.")
            
        self.exchange = exchange_class({
            "enableRateLimit": enable_rate_limit,
            "timeout": 30000,
        })

    def fetch_ohlcv(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        since_str: Optional[str] = "2023-01-01 00:00:00",
        limit_per_call: int = 1000,
        max_total_candles: Optional[int] = 5000,
    ) -> pd.DataFrame:
        """Fetch historical candles with pagination."""
        since_ms = None
        if since_str:
            dt = datetime.fromisoformat(since_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            since_ms = int(dt.timestamp() * 1000)

        all_ohlcv = []
        current_since = since_ms

        while True:
            try:
                candles = self.exchange.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    since=current_since,
                    limit=limit_per_call,
                )
            except Exception as e:
                print(f"[Warning] Error fetching {symbol} {timeframe} since {current_since}: {e}")
                break

            if not candles:
                break

            all_ohlcv.extend(candles)
            last_timestamp = candles[-1][0]

            if len(candles) < limit_per_call:
                break

            if max_total_candles and len(all_ohlcv) >= max_total_candles:
                all_ohlcv = all_ohlcv[:max_total_candles]
                break

            current_since = last_timestamp + 1
            time.sleep(self.exchange.rateLimit / 1000.0)

        if not all_ohlcv:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = pd.DataFrame(
            all_ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        return df

    @staticmethod
    def generate_mock_ohlcv(
        symbol: str = "BTC/USDT",
        timeframe: str = "1h",
        days: int = 180,
        start_price: float = 30000.0,
        volatility: float = 0.015,
        seed: int = 42,
    ) -> pd.DataFrame:
        """Generate realistic geometric Brownian motion OHLCV data for offline development/testing."""
        np.random.seed(seed)
        
        freq_map = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}
        freq = freq_map.get(timeframe, "1h")
        timestamps = pd.date_range(end=datetime.now(timezone.utc), periods=days * 24, freq=freq)
        n = len(timestamps)

        returns = np.random.normal(0.0002, volatility, n)
        price_series = start_price * np.exp(np.cumsum(returns))

        highs = price_series * (1 + np.abs(np.random.normal(0.003, 0.005, n)))
        lows = price_series * (1 - np.abs(np.random.normal(0.003, 0.005, n)))
        opens = np.roll(price_series, 1)
        opens[0] = start_price
        
        highs = np.maximum.reduce([opens, price_series, highs])
        lows = np.minimum.reduce([opens, price_series, lows])
        
        base_volume = np.random.lognormal(mean=4.0, sigma=0.8, size=n) * 100
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": price_series,
            "volume": base_volume
        })
        return df
