"""Data Package: CCXT market fetcher and Parquet/DuckDB storage."""

from packages.data.data_manager import DataManager
from packages.data.ccxt_fetcher import CCXTFetcher

__all__ = ["DataManager", "CCXTFetcher"]
