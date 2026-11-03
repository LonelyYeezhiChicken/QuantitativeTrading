"""CLI App: End-to-End Feature Engineering, LightGBM Training & Backtesting."""

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from packages.data import DataManager
from packages.features import FeaturePipeline
from packages.models import LGBMAgent
from packages.backtest import BacktestEngine

def main():
    parser = argparse.ArgumentParser(description="Train LightGBM Quant Model and Run Backtest")
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading symbol")
    parser.add_argument("--timeframe", default="1h", help="Timeframe")
    parser.add_argument("--threshold", type=float, default=0.002, help="Confidence threshold to trade (e.g. 0.002 = 0.2 percent)")
    args = parser.parse_args()

    dm = DataManager()
    raw_df = dm.load_raw_data(args.symbol, args.timeframe)
    if raw_df is None or len(raw_df) < 100:
        print(f"[Error] No data found for {args.symbol} {args.timeframe}. Please download data first.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"  AI QUANT PIPELINE: {args.symbol} ({args.timeframe})")
    print("=" * 60)

    # 1. Feature Engineering
    print(f"\n[Step 1] Constructing Multi-Factor Features...")
    pipeline = FeaturePipeline(target_horizon=3, label_threshold=0.005)
    features_df, feature_cols = pipeline.build_features(raw_df)
    print(f"  -> Generated {len(feature_cols)} features over {len(features_df)} valid bars.")

    dm.save_features(features_df, args.symbol, args.timeframe)

    # 2. Model Training with Purged TimeSeries CV
    print(f"\n[Step 2] Training LightGBM Model with Purged TimeSeries CV...")
    agent = LGBMAgent()
    cv_metrics = agent.train_cv(
        df=features_df,
        feature_cols=feature_cols,
        target_col="target_forward_return",
        n_splits=5,
    )
    print(f"  -> Out-Of-Fold RMSE: {cv_metrics['avg_rmse']:.5f}")
    print(f"  -> Information Coefficient (Spearman Rank IC): {cv_metrics['avg_ic']:+.4f}")

    print(f"\n[Step 3] Top 8 Predictive Feature Importances:")
    top_features = agent.get_top_features(8)
    max_imp = top_features["importance"].max() if len(top_features) > 0 and top_features["importance"].max() > 0 else 1.0
    for idx, row in top_features.iterrows():
        bar_len = int((row["importance"] / max_imp) * 20)
        bar = "#" * bar_len
        print(f"  {row['feature']:<20} | {row['importance']:>8.2f} {bar}")

    # 3. Model Inference
    print(f"\n[Step 4] Predicting Returns and Simulating Strategy...")
    predicted_returns = agent.predict(features_df)

    # 4. Backtesting with Fees & Slippage
    engine = BacktestEngine(
        initial_capital=10000.0,
        fee_rate=0.0005,
        slippage=0.0002,
        confidence_threshold=args.threshold,
        allow_short=False,
    )
    results_df, perf = engine.run(features_df, predicted_returns)

    print("\n" + "=" * 60)
    print("  STRATEGY BACKTEST PERFORMANCE REPORT (With Fees & Slippage)")
    print("=" * 60)
    for k, v in perf.items():
        print(f"  {k:<28}: {v}")

    bench_ret = ((features_df["close"].iloc[-1] / features_df["close"].iloc[0]) - 1.0) * 100
    strat_ret = perf.get("Total Return (%)", 0.0)
    print("-" * 60)
    print(f"  Strategy Return           : {strat_ret:+.2f}%")
    print(f"  Benchmark (Buy & Hold)    : {bench_ret:+.2f}%")
    print("=" * 60)

if __name__ == "__main__":
    main()
