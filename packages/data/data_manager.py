"""Data Manager: Parquet caching and DuckDB query interface."""

import os
from pathlib import Path
from typing import Optional
import pandas as pd
import duckdb

class DataManager:
    """Manages raw and processed market data storage and querying."""

    def __init__(self, raw_dir: str = "data/raw", processed_dir: str = "data/processed"):
        self.raw_dir = Path(raw_dir)
        self.processed_dir = Path(processed_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_symbol(self, symbol: str) -> str:
        """Convert 'BTC/USDT' to 'BTC_USDT' for safe filenames."""
        return symbol.replace("/", "_").replace(":", "_").upper()

    def get_raw_filepath(self, symbol: str, timeframe: str) -> Path:
        clean_symbol = self._sanitize_symbol(symbol)
        return self.raw_dir / f"{clean_symbol}_{timeframe}.parquet"

    def get_processed_filepath(self, symbol: str, timeframe: str) -> Path:
        clean_symbol = self._sanitize_symbol(symbol)
        return self.processed_dir / f"{clean_symbol}_{timeframe}_features.parquet"

    def save_raw_data(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Path:
        """Save raw OHLCV dataframe to Parquet with timestamp sorting and deduplication."""
        if df.empty:
            raise ValueError(f"Cannot save empty DataFrame for {symbol} {timeframe}")

        filepath = self.get_raw_filepath(symbol, timeframe)
        
        df = df.copy()
        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            
        df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
        df.to_parquet(filepath, engine="pyarrow", index=False)
        return filepath

    def load_raw_data(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Load raw OHLCV dataframe from Parquet if exists."""
        filepath = self.get_raw_filepath(symbol, timeframe)
        if not filepath.exists():
            return None
        df = pd.read_parquet(filepath, engine="pyarrow")
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df.sort_values("timestamp").reset_index(drop=True)

    def save_features(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Path:
        """Save feature-engineered dataset."""
        filepath = self.get_processed_filepath(symbol, timeframe)
        df.to_parquet(filepath, engine="pyarrow", index=False)
        return filepath

    def load_features(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Load feature-engineered dataset."""
        filepath = self.get_processed_filepath(symbol, timeframe)
        if not filepath.exists():
            return None
        return pd.read_parquet(filepath, engine="pyarrow")

    def query_with_duckdb(self, query: str) -> pd.DataFrame:
        """Execute arbitrary DuckDB SQL query against local parquet files."""
        con = duckdb.connect(database=":memory:")
        return con.execute(query).df()
