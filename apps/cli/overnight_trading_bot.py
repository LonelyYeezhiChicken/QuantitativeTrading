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


def fetch_market_signals(gw: BingXGateway, symbol: str = "BTC/USDT") -> dict:
    """Fetch live ticker and compute instant indicators (RSI 14, EMA 21, ATR 14)."""
    ticker = gw.fetch_ticker(symbol)
    price = ticker.get("price", 0.0)

    try:
        klines_resp = gw.client.fetch_klines(gw.to_bingx_symbol(symbol), interval="1h", limit=40)
        k_data = klines_resp.get("data", [])
        closes = [float(x[4]) for x in k_data][::-1] if k_data else [price]
        highs = [float(x[2]) for x in k_data][::-1] if k_data else [price]
        lows = [float(x[3]) for x in k_data][::-1] if k_data else [price]
    except Exception:
        closes = [price]
        highs = [price]
        lows = [price]

    rsi = 50.0
    ema21 = price
    atr = price * 0.015

    if len(closes) >= 15:
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains[-14:]) / 14
        avg_loss = sum(losses[-14:]) / 14
        if avg_loss > 0:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        k = 2.0 / (21.0 + 1.0)
        ema = closes[0]
        for c in closes[1:]:
            ema = c * k + ema * (1.0 - k)
        ema21 = ema

        # ATR
        tr_list = []
        for i in range(1, len(closes)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            tr_list.append(tr)
        if len(tr_list) >= 14:
            atr = sum(tr_list[-14:]) / 14

    return {
        "price": price,
        "bid": ticker.get("bid", price),
        "ask": ticker.get("ask", price),
        "rsi": rsi,
        "ema21": ema21,
        "atr": atr,
    }


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

    gw = BingXGateway(dry_run=True)
    loop_count = 0

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
            sig = fetch_market_signals(gw, "BTC/USDT")
            price = sig["price"]
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
                # Entry Strategy:
                # 1. Healthy dip near or above EMA21 with RSI < 55
                # 2. Or Oversold rebound (RSI < 38)
                if price >= ema21 * 0.998 and rsi <= 55:
                    execute_buy(state, price, trade_usdt=50.0, reason=f"均線回踩支撐確認 (RSI={rsi:.1f}, 價貼近EMA21)", sig=sig)
                elif rsi < 38:
                    execute_buy(state, price, trade_usdt=50.0, reason=f"短線超賣低接 (RSI={rsi:.1f} < 38)", sig=sig)

            elif pos["side"] == "LONG":
                gain_pct = ((price - entry_p) / entry_p) * 100
                pullback_from_high = ((highest_p - price) / highest_p) * 100 if highest_p > 0 else 0.0

                # 1. Take Profit:
                # Condition A: RSI overbought exhaustion (RSI >= 72)
                if rsi >= 72 and gain_pct > 0.8:
                    execute_sell(state, price, reason=f"1h RSI 嚴重超買鈍化 (RSI={rsi:.1f} >= 72, 鎖定獲利 +{gain_pct:.2f}%)")

                # Condition B: Trailing Stop Profit (Gain reached >= 1.5% and pulled back 0.4% from peak)
                elif gain_pct >= 1.5 and pullback_from_high >= 0.4:
                    execute_sell(state, price, reason=f"移動停利觸發 (最高點 ${highest_p:,.2f} 回檔 {pullback_from_high:.2f}%, 鎖定 +{gain_pct:.2f}%)")

                # 2. Stop Loss:
                # Hard stop at -1.5% to protect capital
                elif gain_pct <= -1.5:
                    execute_sell(state, price, reason=f"硬停損觸發 (虧損達到 -1.5%，嚴格截斷風險)")

                # 3. DCA Add Position:
                # If down -0.8% ~ -1.2% near EMA, and still have >= 40U cash, add remaining capital to lower avg price
                elif -1.2 <= gain_pct <= -0.7 and cash >= 40.0 and rsi < 48:
                    execute_buy(state, price, trade_usdt=cash, reason=f"分批加碼攤平 (回跌 {gain_pct:.2f}%, 動用剩餘 ${cash:.2f} U 壓低成本)", sig=sig)

        except Exception as e:
            log_msg(f"[例外警告] 輪詢迴圈異常 (不影響運行，將自動重試): {e}")

        # Sleep with early-exit polling
        for _ in range(args.interval):
            if not RUNNING or STOP_FLAG_FILE.exists():
                break
            time.sleep(1)

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
