"""CLI App: Download or generate historical market data."""

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from packages.data import CCXTFetcher, DataManager

def main():
    parser = argparse.ArgumentParser(description="Download crypto market data")
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading pair symbol")
    parser.add_argument("--timeframe", default="1h", help="K-line timeframe (15m, 1h, 1d)")
    parser.add_argument("--days", type=int, default=180, help="Days of data to fetch/generate")
    parser.add_argument("--mock", action="store_true", help="Force synthetic realistic data generation")
    args = parser.parse_args()

    dm = DataManager()
    fetcher = CCXTFetcher(exchange_id="binance")

    print(f"\n==================================================")
    print(f"  Fetching Market Data: {args.symbol} ({args.timeframe})")
    print(f"==================================================")

    df = None
    if not args.mock:
        try:
            print("Connecting to Binance via CCXT...")
            df = fetcher.fetch_ohlcv(
                symbol=args.symbol,
                timeframe=args.timeframe,
                limit_per_call=1000,
                max_total_candles=args.days * 24,
            )
            if df.empty or len(df) < 50:
                print("[Notice] Online fetch returned empty or insufficient data. Falling back to synthetic dataset.")
                df = None
        except Exception as e:
            print(f"[Warning] Failed to fetch online data ({e}). Switching to synthetic dataset.")
            df = None

    if df is None:
        print(f"Generating {args.days} days of realistic geometric Brownian motion data for {args.symbol}...")
        df = fetcher.generate_mock_ohlcv(
            symbol=args.symbol,
            timeframe=args.timeframe,
            days=args.days,
            start_price=75000.0 if "BTC" in args.symbol else (3950.0 if "XAUT" in args.symbol else 2500.0),
        )

    saved_path = dm.save_raw_data(df, args.symbol, args.timeframe)
    print(f"SUCCESS! Saved {len(df)} candles to: {saved_path}")
    print(f"Data range: {df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]}")

if __name__ == "__main__":
    main()
