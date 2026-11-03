"""CLI App: Simulated Paper Trading Runner."""

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
from packages.execution import PaperBroker

def main():
    parser = argparse.ArgumentParser(description="Simulate Paper Trading Live Execution")
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading symbol")
    parser.add_argument("--timeframe", default="1h", help="Timeframe")
    parser.add_argument("--steps", type=int, default=48, help="Simulate execution over the last N bars")
    parser.add_argument("--trade_allocation", type=float, default=2500.0, help="USDT per trade position")
    parser.add_argument("--threshold", type=float, default=0.002, help="Prediction threshold to trigger trade")
    args = parser.parse_args()

    dm = DataManager()
    raw_df = dm.load_raw_data(args.symbol, args.timeframe)
    if raw_df is None or len(raw_df) < 100:
        print(f"[Error] No data found. Please download data first.")
        sys.exit(1)

    pipeline = FeaturePipeline(target_horizon=3)
    features_df, feature_cols = pipeline.build_features(raw_df)
    
    agent = LGBMAgent()
    agent.train_cv(features_df, feature_cols, target_col="target_forward_return")

    broker = PaperBroker(initial_balance=10000.0)

    print("\n" + "=" * 70)
    print(f"  PAPER TRADING SIMULATION: {args.symbol} (Last {args.steps} bars)")
    print("=" * 70)
    print(f"  Initial Cash Balance: ${broker.cash:,.2f} USDT")

    test_slice = features_df.tail(args.steps).reset_index(drop=True)
    
    for i in range(len(test_slice)):
        bar = test_slice.iloc[i : i + 1]
        timestamp = bar["timestamp"].iloc[0]
        current_price = bar["close"].iloc[0]
        pred_return = agent.predict(bar)[0]

        has_pos = args.symbol in broker.positions and broker.positions[args.symbol]["amount"] > 0

        if pred_return > args.threshold and not has_pos:
            order = broker.buy(args.symbol, current_price, usdt_amount=args.trade_allocation)
            if order:
                print(f"[{timestamp}] [BUY]  | Price: ${order['price']:,.2f} | Amount: ${order['notional']:,.2f} | Exp. Return: {pred_return:+.3%}")

        elif pred_return < -args.threshold and has_pos:
            order = broker.sell(args.symbol, current_price, pct_position=1.0)
            if order:
                pnl = order["realized_pnl"]
                sign = "+" if pnl >= 0 else "-"
                print(f"[{timestamp}] [SELL] | Price: ${order['price']:,.2f} | Realized PnL: [{sign}] ${pnl:+.2f} | Exp. Return: {pred_return:+.3%}")

    latest_price = test_slice["close"].iloc[-1]
    summary = broker.summary(current_prices={args.symbol: latest_price})

    print("\n" + "=" * 70)
    print("  PAPER TRADING ACCOUNT DASHBOARD")
    print("=" * 70)
    print(f"  Cash Balance (USDT)       : ${summary['cash_usdt']:,.2f}")
    print(f"  Total Portfolio Value     : ${summary['portfolio_value_usdt']:,.2f}")
    print(f"  Total PnL (USDT / %)      : ${summary['total_pnl_usdt']:+,.2f} ({summary['total_pnl_pct']})")
    print(f"  Total Orders Executed     : {summary['total_trades']}")
    print(f"  Active Positions          : {summary['open_positions']}")
    print("=" * 70)

if __name__ == "__main__":
    main()
