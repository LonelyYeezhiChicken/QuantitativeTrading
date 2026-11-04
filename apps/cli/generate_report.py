"""CLI Entrypoint for Quantitative Daily (08:00 / 18:00) and Weekly (Monday) Reports."""

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from packages.core.autopilot_engine import compute_structural_indicators_from_ohlc
from packages.execution import BingXGateway, MarketType
from packages.journal.report_generator import QuantReportGenerator


def fetch_live_btc_context() -> tuple[float, dict]:
    gw = BingXGateway(dry_run=True, enable_ws=False)
    ticker = gw.fetch_ticker("BTC/USDT", market_type=MarketType.SWAP.value)
    cur_p = float(ticker.get("price") or 78000.0)
    try:
        resp = gw.client.fetch_klines("BTC-USDT", interval="1h", limit=60)
        k_data = resp.get("data", [])
        if k_data:
            closes = [float(x[4]) for x in k_data][::-1]
            highs = [float(x[2]) for x in k_data][::-1]
            lows = [float(x[3]) for x in k_data][::-1]
            sig = compute_structural_indicators_from_ohlc(closes, highs, lows, cur_p)
            return cur_p, sig
    except Exception:
        pass
    return cur_p, {"price": cur_p, "rsi": 50.0, "ema21": cur_p, "ema50": cur_p}


def main():
    parser = argparse.ArgumentParser(description="Generate Quantitative Daily or Weekly Report and Publish to GitHub Issues")
    parser.add_argument("--type", choices=["daily", "weekly", "both"], default="daily", help="Report type")
    parser.add_argument("--session", choices=["AM", "PM"], default=None, help="Daily session override (AM or PM)")
    parser.add_argument("--no-issue", action="store_true", help="Skip publishing report to GitHub Issues")
    args = parser.parse_args()

    cur_p, sig = fetch_live_btc_context()
    gen = QuantReportGenerator(root_dir=ROOT_DIR)
    publish_issue = not args.no_issue

    if args.type in ("daily", "both"):
        d_res = gen.generate_daily_report(
            current_price=cur_p,
            session=args.session,
            market_signals=sig,
            publish_issue=publish_issue,
        )
        print(d_res["markdown"])
        print(f"\n[日報已存檔] {d_res['path']}")
        if d_res.get("issue_url"):
            print(f"[GitHub Issue 已發布] {d_res['issue_url']}")

    if args.type in ("weekly", "both"):
        w_res = gen.generate_weekly_report(
            current_price=cur_p,
            publish_issue=publish_issue,
        )
        print(w_res["markdown"])
        print(f"\n[週報已存檔] {w_res['path']}")
        if w_res.get("issue_url"):
            print(f"[GitHub Issue 已發布] {w_res['issue_url']}")


if __name__ == "__main__":
    main()
