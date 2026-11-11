"""Autonomous Quantitative Autopilot CLI (Production Entrypoint).

Usage:
    python apps/cli/autopilot.py                # Boots in STANDBY mode (Safe)
    python apps/cli/autopilot.py --arm          # Boots and immediately arms
    python apps/cli/autopilot.py --status       # Prints current status and exits
    python apps/cli/autopilot.py --mode SPOT    # Spot asset mode
"""

import argparse
import os
import sys
import threading
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from packages.core.autopilot_engine import UnifiedAutopilotEngine, AutopilotState
from packages.core.event_bus import MarketEventBus, TickerUpdateEvent
from packages.core.heartbeat import record_heartbeat

# A pushed price older than this is considered stale and is not used for risk decisions.
MAX_TICK_AGE_SEC = 15.0


def print_status(engine: UnifiedAutopilotEngine):
    """Print clean terminal status summary.

    Read-only: a status query runs in a separate process from the trading daemon,
    so it must never resolve orders, reconcile, or rewrite the shared state file.
    """
    engine.load_state(restore_status=True)
    step_data = engine.peek()
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
    parser.add_argument("--vst", action="store_true", help="Route orders to BingX official VST simulation server (appears on BingX App)")
    parser.add_argument("--live", action="store_true", help="Execute real orders on live exchange with REAL MONEY")
    parser.add_argument("--margin-ratio", type=float, default=0.75, help="Capital allocation ratio per trade (e.g. 0.75 for 75%%)")
    parser.add_argument("--max-loss-pct", type=float, default=50.0, help="Circuit breaker threshold: stop if loss exceeds this pct of capital (e.g. 50.0)")
    parser.add_argument("--risk-pct", type=float, default=0.02, help="Fixed fractional risk per trade (e.g. 0.02 for 2.0%% total capital risk)")
    parser.add_argument("--fixed-margin-sizing", action="store_true", help="Use legacy fixed margin ratio sizing instead of ATR risk-based sizing")
    parser.add_argument("--bot-id", type=str, default="", help="Custom identifier for container healthcheck probe (e.g. swap_3x)")
    args = parser.parse_args()

    bot_id = args.bot_id.strip() if args.bot_id else (f"swap_{args.leverage}x" if args.leverage > 1 else "spot_1x")

    env_vst = os.getenv("BINGX_USE_VST", "false").lower() in ("true", "1") or os.getenv("VPS_BURN_IN_MODE", "false").lower() in ("true", "1")
    use_vst_mode = bool(args.vst or env_vst)
    is_real_live = bool(args.live and not use_vst_mode)

    engine = UnifiedAutopilotEngine(
        symbol=args.symbol,
        leverage=args.leverage,
        capital=args.capital,
        mode=args.mode,
        enable_ai_veto=not args.no_ai,
        dry_run=not (is_real_live or use_vst_mode),
        use_vst=use_vst_mode,
        capital_allocation_ratio=args.margin_ratio,
        max_loss_pct=args.max_loss_pct,
        risk_per_trade_pct=args.risk_pct,
        use_risk_based_sizing=not args.fixed_margin_sizing,
    )

    if args.status:
        print_status(engine)
        return

    if args.disarm:
        # disarm() persists STANDBY and broadcasts it to any running daemon via the control file.
        msg = engine.disarm()
        print(f"[系統指令] {msg}")
        print("          若操盤中樞正在運行，將於下一個心跳 (最長 --interval 秒) 內切換為待機。")
        return

    print("=" * 70)
    print("  全自動量化操盤中樞 (Unified Autopilot)")
    print(f"  標的: {args.symbol} | 槓桿: {engine.leverage}x ({engine.mode}) | 本金: ${args.capital:.2f} USDT")
    print(f"  環境: {'【⚠️ 實盤真金 (REAL MONEY)】' if is_real_live else ('【🔥 VST 燒機模擬盤 (本金鎖定)】' if use_vst_mode else '【本地模擬】')}")
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
    event_bus = MarketEventBus()
    wakeup_event = threading.Event()
    latest_tick: dict = {"price": None, "ts": 0.0}

    def _on_bus_tick(ev: TickerUpdateEvent):
        # Runs on the WebSocket / watchdog threads: only record the price and wake the
        # main loop. The engine itself is driven exclusively from the main thread, so
        # feed threads can never submit concurrent orders or block the WS event loop.
        if ev.price > 0:
            latest_tick["price"] = ev.price
            latest_tick["ts"] = time.time()
            if engine.position.get("side", "NONE") != "NONE":
                wakeup_event.set()

    event_bus.subscribe(TickerUpdateEvent, _on_bus_tick)
    m_type = "SWAP" if "SWAP" in engine.mode else "SPOT"
    market_feed = engine.gw.create_market_feed(
        event_bus=event_bus,
        symbols=[args.symbol],
        market_type=m_type,
        poll_interval_sec=min(5.0, float(args.interval)),
    )
    if args.run_loop or args.arm:
        market_feed.start()
        print(f"[EventBus 已啟動] 資料源適配器: {market_feed.get_feed_status()['mode']} (WebSocket 即時監聽 + 斷線自動輪詢備援)")

    coin_code = args.symbol.split('/')[0]
    next_heartbeat = 0.0
    try:
        while True:
            # Clear before stepping so ticks arriving during the step are not lost.
            wakeup_event.clear()
            now = time.monotonic()
            is_heartbeat = now >= next_heartbeat
            if is_heartbeat:
                loop_count += 1
                next_heartbeat = now + max(1, args.interval)

            # Only trust a feed price that is fresh; a dead feed must not freeze the price
            # the risk loop sees. Stale -> None -> the engine queries REST itself.
            tick_age = time.time() - float(latest_tick.get("ts") or 0.0)
            fresh_price = latest_tick.get("price") if tick_age <= MAX_TICK_AGE_SEC else None
            try:
                step = engine.step(override_price=fresh_price)
            except Exception as exc:
                # Never let a single failed tick kill the daemon and orphan an open position.
                print(f"#{loop_count:04d} | [錯誤] 本次心跳執行失敗，將於下一次心跳重試: {exc!r}")
                step = None

            # Record healthcheck heartbeat for container probe
            record_heartbeat(
                name=bot_id,
                metadata={
                    "loop_count": loop_count,
                    "symbol": args.symbol,
                    "leverage": engine.leverage,
                    "status": str(engine.status),
                    "action": step.get("action_taken") if step else "STEP_ERROR",
                    "price": fresh_price,
                },
            )

            if step is not None and (is_heartbeat or step.get("action_taken") not in ("NONE", None)):
                state_tag = "【ARMED 運行中】" if engine.status == AutopilotState.ARMED else "【STANDBY 待機】"
                pnl_tag = f"持倉: {step['position_side']} | 浮盈: ${step['pnl_usdt']:+,.2f} ({step['pnl_pct']:+.2f}%)" if step['position_side'] != "NONE" else "空倉待機"
                print(f"#{loop_count:04d} | {state_tag} {coin_code}: ${step['price']:,.2f} | 淨值: ${step['total_equity']:.2f} U | {pnl_tag} | {step['message']}")

            if not args.run_loop and not args.arm:
                # If neither run-loop nor arm was requested, perform one clean cycle inspection and exit
                break

            # Sleep until the next heartbeat, or wake immediately on a price tick while in position.
            wakeup_event.wait(timeout=max(0.0, next_heartbeat - time.monotonic()))
    except KeyboardInterrupt:
        print("\n[系統關閉] 收到中斷信號，安全退出。")
    finally:
        market_feed.stop()


if __name__ == "__main__":
    main()
