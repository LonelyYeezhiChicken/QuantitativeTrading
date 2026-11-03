"""CLI App: Run Modular 100 USDT Compounding Rolling Backtest with Any Model."""

import argparse
import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from packages.backtest import RollingBacktestEvaluator
from packages.models import LGBMAgent, DualEMACrossoverModel, RSIMomentumModel, TypeSafeAIAgent

def get_model(model_name: str):
    """Factory to instantiate the requested trading model."""
    name = model_name.lower().strip()
    if name == "lgbm":
        return LGBMAgent(num_boost_round=150)
    elif name in ["trend", "ema"]:
        return DualEMACrossoverModel(fast_span=21, slow_span=50)
    elif name == "rsi":
        return RSIMomentumModel(lower_thresh=35.0, upper_thresh=65.0)
    elif name in ["typesafe", "jev"]:
        return TypeSafeAIAgent()
    else:
        raise ValueError(f"Unknown model '{model_name}'. Choose from: 'lgbm', 'trend', 'rsi', 'typesafe'")

def main():
    parser = argparse.ArgumentParser(description="Modular Full-Year Rolling Backtest Runner")
    parser.add_argument("--model", default="lgbm", choices=["lgbm", "trend", "rsi", "typesafe"], help="Trading model to test")
    parser.add_argument("--year", type=int, default=2025, help="Backtest calendar year")
    parser.add_argument("--capital", type=float, default=100.0, help="Initial capital in USDT")
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading pair symbol")
    parser.add_argument("--threshold", type=float, default=0.002, help="Signal confidence threshold")
    args = parser.parse_args()

    model = get_model(args.model)
    evaluator = RollingBacktestEvaluator(
        initial_capital=args.capital,
        fee_rate=0.0005,
        slippage=0.0002,
        atr_stop_multiplier=2.0,
        allow_short=False,
    )

    result = evaluator.evaluate_year(
        model=model,
        symbol=args.symbol,
        year=args.year,
        timeframe="1h",
        threshold=args.threshold,
    )

    result.print_summary()

if __name__ == "__main__":
    main()
