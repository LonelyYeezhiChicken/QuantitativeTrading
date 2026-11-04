"""Autonomous Overnight Quantitative Trading Daemon for BingX Paper Trading.

Monitors live BingX BTC market data 24/7, executes autonomous trading decisions
(entry, DCA, trailing take-profit, stop-loss), and persists all operations
until manually stopped by the user.
"""

import argparse
import json
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from packages.execution import BingXGateway, MarketType
from packages.journal import TradeJournalManager
from packages.core.event_bus import (
    MarketEventBus,
    TickerUpdateEvent,
    InMemoryKlineRollingCache,
)
from packages.core.autopilot_engine import (
    compute_structural_indicators_from_ohlc,
    evaluate_structural_entry,
    evaluate_three_stage_exit,
    sync_breakeven_stop_loss,
)

STATE_FILE = ROOT_DIR / "data" / "bingx_paper_100u.json"
LOG_DIR = ROOT_DIR / "logs"
LOG_FILE = LOG_DIR / "overnight_bot.log"
STOP_FLAG_FILE = ROOT_DIR / "data" / "bot_stop.flag"

RUNNING = True
journal_mgr = TradeJournalManager()


def handle_exit(signum, frame):
    """Graceful shutdown handler for Ctrl+C or kill signals."""
    global RUNNING
    RUNNING = False
    log_msg("\n[系統關閉] 收到停止指令，守護進程即將優雅退出並結算戰報...")


def log_msg(text: str):
    """Log to both stdout and persistent log file."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {text}"
    print(line)
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_state() -> dict:
    """Load persistent account state."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return {
        "initial_capital": 100.0,
        "cash_usdt": 100.0,
        "market_type": "SPOT",
        "position": {
            "symbol": "BTC/USDT",
            "side": "NONE",
            "amount_btc": 0.0,
            "entry_price": 0.0,
            "margin_used": 0.0,
            "leverage": 1,
            "entry_time": "",
            "highest_price": 0.0,
        },
        "history": [],
    }


def save_state(state: dict):
    """Save persistent state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def fetch_spot_klines_raw(gw: BingXGateway, symbol: str = "BTC/USDT") -> dict:
    """Fetch 100 1h OHLC bars from BingX REST API for the rolling in-memory cache."""
    klines_resp = gw.client.fetch_klines(gw.to_bingx_symbol(symbol), interval="1h", limit=100)
    k_data = klines_resp.get("data", [])
    if not k_data:
        return {}
    return {
        "closes": [float(x[4]) for x in k_data][::-1],
        "highs": [float(x[2]) for x in k_data][::-1],
        "lows": [float(x[3]) for x in k_data][::-1],
    }


def fetch_market_signals(
    gw: BingXGateway,
    symbol: str = "BTC/USDT",
    kline_cache: InMemoryKlineRollingCache | None = None,
    override_event: TickerUpdateEvent | None = None,
) -> dict:
    """Fetch live ticker (or use WebSocket event) and compute 1h structural indicators via rolling cache."""
    if override_event is not None and override_event.price > 0:
        price = override_event.price
        bid = override_event.bid
        ask = override_event.ask
    else:
        ticker = gw.fetch_ticker(symbol)
        price = ticker.get("price", 0.0)
        bid = ticker.get("bid", price)
        ask = ticker.get("ask", price)

    if kline_cache is not None:
        try:
            return kline_cache.compute_signals_on_tick(symbol, "SPOT", price=price, bid=bid, ask=ask)
        except Exception:
            pass

    try:
        raw = fetch_spot_klines_raw(gw, symbol)
        closes = raw.get("closes") or [price]
        highs = raw.get("highs") or [price]
        lows = raw.get("lows") or [price]
    except Exception:
        closes = [price]
        highs = [price]
        lows = [price]

    return compute_structural_indicators_from_ohlc(
        closes=closes,
        highs=highs,
        lows=lows,
        cur_price=price,
        bid=bid,
        ask=ask,
    )


def execute_buy(state: dict, price: float, trade_usdt: float, reason: str, sig: dict = None):
    """Execute autonomous simulated buy order and register in trade journal."""
    pos = state["position"]
    trade_usdt = min(trade_usdt, state["cash_usdt"])
    if trade_usdt <= 0:
        return

    btc_qty = trade_usdt / price
    state["cash_usdt"] -= trade_usdt

    if pos["side"] == "NONE":
        entry = journal_mgr.on_trade_open(
            symbol="BTC/USDT",
            market_type="SPOT",
            side="LONG",
            entry_price=price,
            amount_btc=btc_qty,
            margin_used=trade_usdt,
            leverage=1,
            raw_reason=reason,
            snapshot_dict=sig or {"price": price},
            stop_loss_pct=1.5,
            trailing_pullback_pct=0.4,
        )
        state["position"] = {
            "symbol": "BTC/USDT",
            "side": "LONG",
            "amount_btc": btc_qty,
            "entry_price": price,
            "margin_used": trade_usdt,
            "leverage": 1,
            "entry_time": entry.entry_time,
            "highest_price": price,
            "journal_id": entry.journal_id,
        }
        log_msg(f"【自動進場買入】原因: {reason} | 價格: ${price:,.2f} | 投入: ${trade_usdt:.2f} U | 數量: {btc_qty:.6f} BTC | 日誌: {entry.journal_id}")
    elif pos["side"] == "LONG":
        # DCA / Add Position
        old_amt = pos["amount_btc"]
        old_cost = old_amt * pos["entry_price"]
        new_amt = old_amt + btc_qty
        new_avg_price = (old_cost + trade_usdt) / new_amt

        pos["amount_btc"] = new_amt
        pos["entry_price"] = new_avg_price
        pos["margin_used"] += trade_usdt
        pos["highest_price"] = max(pos.get("highest_price", price), price)
        log_msg(f"【自動分批補倉】原因: {reason} | 價格: ${price:,.2f} | 加碼: ${trade_usdt:.2f} U | 新均價: ${new_avg_price:,.2f} | 總數量: {new_amt:.6f} BTC")

    save_state(state)


def execute_sell(state: dict, price: float, reason: str):
    """Execute autonomous simulated sell/close order and finalize trade journal."""
    pos = state["position"]
    if pos["side"] == "NONE":
        return

    entry_p = pos["entry_price"]
    qty = pos["amount_btc"]
    margin = pos["margin_used"]
    pnl = (price - entry_p) * qty
    pnl_pct = (pnl / margin) * 100 if margin > 0 else 0.0
    returned_cash = margin + pnl

    state["cash_usdt"] += returned_cash
    record = {
        "closed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "entry_price": entry_p,
        "exit_price": price,
        "amount_btc": qty,
        "pnl_usdt": pnl,
        "pnl_pct": pnl_pct,
        "reason": reason,
    }
    state["history"].append(record)

    journal_id = pos.get("journal_id")
    if journal_id:
        journal_mgr.on_trade_close(journal_id, exit_price=price, exit_reason=reason)

    state["position"] = {
        "symbol": "BTC/USDT",
        "side": "NONE",
        "amount_btc": 0.0,
        "entry_price": 0.0,
        "margin_used": 0.0,
        "leverage": 1,
        "entry_time": "",
        "highest_price": 0.0,
    }
    save_state(state)
    log_msg(f"【自動平倉獲利/止損】原因: {reason} | 賣出價: ${price:,.2f} (開倉: ${entry_p:,.2f}) | 盈虧: ${pnl:+,.2f} USDT ({pnl_pct:+.2f}%) | 剩餘現金: ${state['cash_usdt']:.2f} USDT")


def main():
    global RUNNING
    parser = argparse.ArgumentParser(description="Autonomous Overnight Trading Daemon")
    parser.add_argument("--interval", type=int, default=60, help="Loop interval in seconds (default 60s)")
    parser.add_argument("--capital", type=float, default=100.0, help="Total capital (default 100U)")
    args = parser.parse_args()

    # Register signal handlers
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    # Clean previous stop flag if exists
    if STOP_FLAG_FILE.exists():
        try:
            STOP_FLAG_FILE.unlink()
        except Exception:
            pass

    log_msg("=" * 65)
    log_msg("  Antigravity (AGY) 智能過夜自動操盤守護進程啟動")
    log_msg(f"  輪詢週期: 每 {args.interval} 秒 | 監控市場: BingX BTC/USDT | 演練資金: ${args.capital:.2f} USDT")
    log_msg("  停止方式: 隨時按 Ctrl+C 或執行指令 `just bot-stop` 即可優雅結算退出")
    log_msg("=" * 65)

    gw = BingXGateway(dry_run=True, enable_ws=True)
    loop_count = 0

    event_bus = MarketEventBus()
    kline_cache = InMemoryKlineRollingCache(
        kline_fetcher=lambda sym, m_type: fetch_spot_klines_raw(gw, sym),
        refresh_interval_sec=60.0,
    )
    tick_wakeup = threading.Event()
    ws_tick_box: dict = {"event": None, "last_entry_check_ts": 0.0}

    def _on_spot_ticker(ev: TickerUpdateEvent):
        if ev.price <= 0:
            return
        ws_tick_box["event"] = ev
        try:
            st = load_state()
            p_pos = st.get("position", {})
            if p_pos.get("side") == "LONG":
                p_entry = float(p_pos.get("entry_price", 0.0) or 0.0)
                p_high = max(float(p_pos.get("highest_price", ev.price) or ev.price), ev.price)
                if p_entry > 0:
                    gain_pct = ((ev.price - p_entry) / p_entry) * 100.0
                    peak_gain_pct = ((p_high - p_entry) / p_entry) * 100.0
                    act, _ = evaluate_three_stage_exit(
                        pnl_pct=gain_pct,
                        peak_pct=peak_gain_pct,
                        sl_threshold=1.5,
                        tp_threshold=1.5,
                        pullback_threshold=0.4,
                        side="LONG",
                    )
                    need_be_sync = (peak_gain_pct >= 0.75) and not p_pos.get("breakeven_synced")
                    if act is not None or need_be_sync:
                        tick_wakeup.set()
            else:
                now_ts = time.time()
                if (now_ts - ws_tick_box["last_entry_check_ts"]) >= 3.0:
                    ws_tick_box["last_entry_check_ts"] = now_ts
                    fast_sig = kline_cache.compute_signals_on_tick("BTC/USDT", "SPOT", price=ev.price, bid=ev.bid, ask=ev.ask)
                    cand_side, _ = evaluate_structural_entry("SPOT", ev.price, fast_sig, history=st.get("history", []))
                    if cand_side == "LONG":
                        tick_wakeup.set()
        except Exception:
            pass

    event_bus.subscribe(TickerUpdateEvent, _on_spot_ticker)
    market_feed = gw.create_market_feed(
        event_bus=event_bus,
        symbols=["BTC/USDT"],
        market_type=MarketType.SPOT.value,
        poll_interval_sec=min(5.0, float(args.interval)),
    )
    market_feed.start()
    log_msg(f"  [EventBus 已啟動] 資料源適配器: {market_feed.get_feed_status()['mode']} (WebSocket 毫秒級出場監聽 + 斷線自動輪詢備援)")

    while RUNNING:
        # Check stop flag file
        if STOP_FLAG_FILE.exists():
            log_msg("[信號偵測] 偵測到停止標誌檔案 (bot_stop.flag)，正在結束運行...")
            try:
                STOP_FLAG_FILE.unlink()
            except Exception:
                pass
            break

        loop_count += 1
        try:
            state = load_state()
            latest_ev = ws_tick_box.get("event")
            sig = fetch_market_signals(gw, "BTC/USDT", kline_cache=kline_cache, override_event=latest_ev)
            price = sig["price"]
            if not price or price <= 0:
                log_msg("[報價警示] 暫時無法取得有效報價 (PRICE_UNAVAILABLE)，跳過本輪決策")
                continue
            rsi = sig["rsi"]
            ema21 = sig["ema21"]
            pos = state["position"]

            # Compute current equity
            cash = state["cash_usdt"]
            margin = pos.get("margin_used", 0.0)
            qty = pos.get("amount_btc", 0.0)
            entry_p = pos.get("entry_price", 0.0)
            unrealized_pnl = (price - entry_p) * qty if pos["side"] == "LONG" else 0.0
            total_equity = cash + margin + unrealized_pnl

            # Update highest price tracked and journal trajectory
            if pos["side"] == "LONG":
                pos["highest_price"] = max(pos.get("highest_price", price), price)
                if not pos.get("journal_id"):
                    j_entry = journal_mgr.on_trade_open(
                        symbol="BTC/USDT",
                        market_type="SPOT",
                        side="LONG",
                        entry_price=pos["entry_price"],
                        amount_btc=pos["amount_btc"],
                        margin_used=pos.get("margin_used", 50.0),
                        leverage=1,
                        raw_reason="現貨自動追蹤持倉",
                        entry_time_str=pos.get("entry_time"),
                        snapshot_dict=sig,
                    )
                    pos["journal_id"] = j_entry.journal_id
                journal_mgr.on_trade_update(pos["journal_id"], price)
                save_state(state)

            highest_p = pos.get("highest_price", price)

            # Heartbeat display
            pnl_str = f"浮動盈虧: ${unrealized_pnl:+,.2f} ({((unrealized_pnl/margin)*100 if margin>0 else 0):+.2f}%)" if pos["side"] == "LONG" else "空倉待機"
            log_msg(f"#{loop_count:04d} | BTC: ${price:,.2f} | RSI: {rsi:.1f} | EMA21: ${ema21:,.2f} | 淨值: ${total_equity:.2f} USDT | {pnl_str}")

            # ================= STRATEGY DECISION ENGINE =================
            if pos["side"] == "NONE":
                candidate_side, candidate_reason = evaluate_structural_entry(
                    "SPOT", price, sig, history=state.get("history", [])
                )
                if candidate_side == "LONG":
                    execute_buy(state, price, trade_usdt=50.0, reason=candidate_reason, sig=sig)
                elif candidate_reason:
                    log_msg(f"[進場過濾] {candidate_reason}")

            elif pos["side"] == "LONG":
                gain_pct = ((price - entry_p) / entry_p) * 100 if entry_p > 0 else 0.0
                peak_gain_pct = ((highest_p - entry_p) / entry_p) * 100 if entry_p > 0 else gain_pct

                exit_action, exit_reason = evaluate_three_stage_exit(
                    pnl_pct=gain_pct,
                    peak_pct=peak_gain_pct,
                    sl_threshold=1.5,
                    tp_threshold=1.5,
                    pullback_threshold=0.4,
                    rsi=rsi,
                    side="LONG",
                )
                if exit_action is not None:
                    execute_sell(state, price, reason=exit_reason)
                else:
                    be_price = sync_breakeven_stop_loss(
                        pos=pos,
                        cur_price=price,
                        peak_pct=peak_gain_pct,
                        tp_threshold=1.5,
                        leverage=1,
                        symbol="BTC/USDT",
                        market_type=MarketType.SPOT.value,
                        gw=gw,
                        journal_mgr=journal_mgr,
                    )
                    if be_price is not None:
                        save_state(state)
                        log_msg(f"【現貨套保上移 (Break-Even Sync)】最高浮盈達 +{peak_gain_pct:.2f}%，已將保本停損價上移至 ${be_price:,.2f} (開倉均價: ${entry_p:,.2f})！")
                    # DCA Add Position: If down -0.8% ~ -1.2% near EMA, and still have >= 40U cash
                    elif -1.2 <= gain_pct <= -0.7 and cash >= 40.0 and rsi < 48:
                        execute_buy(state, price, trade_usdt=cash, reason=f"分批加碼攤平 (回跌 {gain_pct:.2f}%, 動用剩餘 ${cash:.2f} U 壓低成本)", sig=sig)

        except Exception as e:
            log_msg(f"[例外警告] 輪詢迴圈異常 (不影響運行，將自動重試): {e}")

        # Sleep with early-exit polling or instant EventBus wakeup
        tick_wakeup.clear()
        for _ in range(args.interval):
            if not RUNNING or STOP_FLAG_FILE.exists():
                break
            if tick_wakeup.wait(timeout=1.0):
                break

    market_feed.stop()

    # Post-shutdown summary
    final_state = load_state()
    f_pos = final_state["position"]
    f_cash = final_state["cash_usdt"]
    f_margin = f_pos.get("margin_used", 0.0)
    final_p = gw.fetch_ticker("BTC/USDT").get("price", 0.0)
    unrealized = (final_p - f_pos.get("entry_price", final_p)) * f_pos.get("amount_btc", 0.0) if f_pos["side"] == "LONG" else 0.0
    final_equity = f_cash + f_margin + unrealized

    log_msg("\n" + "=" * 65)
    log_msg("  過夜操盤守護進程已安全停止 - 戰報統計")
    log_msg(f"  總執行輪次 : {loop_count} 次")
    log_msg(f"  起始本金   : ${final_state['initial_capital']:.2f} USDT")
    log_msg(f"  結算總淨值 : ${final_equity:.2f} USDT")
    log_msg(f"  總獲利率   : {((final_equity - final_state['initial_capital'])/final_state['initial_capital']*100):+.2f}%")
    log_msg(f"  累計已實現交易筆數: {len(final_state.get('history', []))} 筆")
    log_msg(f"  詳細歷史日誌請查閱: {LOG_FILE}")
    log_msg("=" * 65)


if __name__ == "__main__":
    main()
