"""Autonomous Quantitative Autopilot CLI (Production Entrypoint).

Usage:
    python apps/cli/autopilot.py                # Boots in STANDBY mode (Safe)
    python apps/cli/autopilot.py --arm          # Boots and immediately arms
    python apps/cli/autopilot.py --status       # Prints current status and exits
    python apps/cli/autopilot.py --mode SPOT    # Spot asset mode
"""

import argparse
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from packages.core.autopilot_engine import UnifiedAutopilotEngine, AutopilotState


def print_status(engine: UnifiedAutopilotEngine):
    """Print clean terminal status summary."""
    step_data = engine.step()
    status_label = "[ARMED 守護中]" if engine.status == AutopilotState.ARMED else "[STANDBY 待機中]"
    print("=" * 65)
    print(f"  量化自動操盤中樞狀態速查 {status_label}")
    print("=" * 65)
    print(f"  運作模式: {engine.mode} (槓桿: {engine.leverage}x)")
    print(f"  總帳戶淨值: ${step_data['total_equity']:,.2f} USDT (現金: ${engine.cash:.2f})")
    print(f"  當前持倉: {step_data['position_side']} | 未實現損益: ${step_data['pnl_usdt']:+,.2f} ({step_data['pnl_pct']:+.2f}%)")
    print("-" * 65)
    print("  最新精簡交易日誌 (為什麼進場 / 決策 / 結果):")
    journals = engine.load_journal()
    if journals:
        for j in journals[:3]:
            print(f"  - [{j['time']}] {j['side']} (盈虧: ${j['pnl_usdt']:+,.2f} | {j['pnl_pct']:+.2f}%)")
            print(f"    【為什麼進場】：{j['why_enter']}")
            print(f"    【AI 決策依據】：{j['ai_decision']}")
            print(f"    【出場與結果】：{j['exit_result']}")
            print()
    else:
        print("    (目前尚無歷史平倉紀錄)")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(description="Unified Autopilot Trading CLI")
    parser.add_argument("--symbol", type=str, default="BTC/USDT", help="Trading symbol (e.g. BTC/USDT, ETH/USDT, SOL/USDT)")
    parser.add_argument("--leverage", type=int, default=3, help="Leverage multiplier (1 for SPOT, >1 for SWAP)")
    parser.add_argument("--capital", type=float, default=100.0, help="Initial capital in USDT")
    parser.add_argument("--mode", type=str, default=None, help="Explicit mode override (optional, defaults to auto-derive from leverage)")
    parser.add_argument("--interval", type=int, default=30, help="Heartbeat loop interval in seconds")
    parser.add_argument("--arm", action="store_true", help="Explicitly arm trading upon startup")
    parser.add_argument("--status", action="store_true", help="Print status and exit")
    parser.add_argument("--disarm", action="store_true", help="Disarm to standby and exit")
    parser.add_argument("--run-loop", action="store_true", help="Run 24/7 continuous autonomous monitoring loop")
    parser.add_argument("--no-ai", action="store_true", help="Disable local Ollama AI veto guard")
    args = parser.parse_args()

    engine = UnifiedAutopilotEngine(
        symbol=args.symbol,
        leverage=args.leverage,
        capital=args.capital,
        mode=args.mode,
        enable_ai_veto=not args.no_ai,
    )

    if args.status:
        print_status(engine)
        return

    if args.disarm:
        msg = engine.disarm()
        print(f"[系統指令] {msg}")
        return

    print("=" * 70)
    print("  全自動量化操盤中樞 (Unified Autopilot)")
    print(f"  標的: {args.symbol} | 槓桿: {engine.leverage}x ({engine.mode}) | 本金: ${args.capital:.2f} USDT")
    print(f"  策略: {engine.strategy.__class__.__name__} | 風控: 價格停損 -{engine.price_sl_pct:.2f}% (保證金 -{engine.margin_sl_threshold:.1f}%)")
    print("=" * 70)

    if args.arm:
        msg = engine.arm()
        print(f"[手動啟動] {msg}")
    else:
        print("[安全提示] 系統預設以【待機模式 (STANDBY)】啟動，絕不主動下單！")
        print("          若欲啟動自動交易，請帶參數 `--arm` 或於 Web 控制台點擊【啟動操盤】。")

    print("-" * 70)

    loop_count = 0
    try:
        while True:
            loop_count += 1
            step = engine.step()
            state_tag = "【ARMED 運行中】" if engine.status == AutopilotState.ARMED else "【STANDBY 待機】"
            coin_code = args.symbol.split('/')[0]
            pnl_tag = f"持倉: {step['position_side']} | 浮盈: ${step['pnl_usdt']:+,.2f} ({step['pnl_pct']:+.2f}%)" if step['position_side'] != "NONE" else "空倉待機"
            print(f"#{loop_count:04d} | {state_tag} {coin_code}: ${step['price']:,.2f} | 淨值: ${step['total_equity']:.2f} U | {pnl_tag} | {step['message']}")

            if not args.run_loop and not args.arm:
                # If neither run-loop nor arm was requested, perform one clean cycle inspection and exit
                break

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[系統關閉] 收到中斷信號，安全退出。")


if __name__ == "__main__":
    main()
