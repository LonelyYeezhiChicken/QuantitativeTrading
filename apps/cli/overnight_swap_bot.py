"""Autonomous Overnight Perpetual Swap (Futures) Trading Daemon for BingX.

Executes autonomous 24/7 leveraged perpetual futures trading on BingX (dry_run)
with dual-direction (LONG/SHORT) capability, leverage margin scaling,
trailing take-profit, and risk-controlled liquidation mitigation.
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

STATE_FILE = ROOT_DIR / "data" / "bingx_swap_100u.json"
LOG_DIR = ROOT_DIR / "logs"
LOG_FILE = LOG_DIR / "overnight_swap_bot.log"
STOP_FLAG_FILE = ROOT_DIR / "data" / "swap_stop.flag"

RUNNING = True
journal_mgr = TradeJournalManager()


def handle_exit(signum, frame):
    """Graceful shutdown handler for Ctrl+C or kill signals."""
    global RUNNING
    RUNNING = False
    log_msg("\n[系統關閉] 收到停止指令，合約守護進程即將優雅退出並結算戰報...")


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
    """Load persistent swap account state."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return {
        "initial_capital": 100.0,
        "available_margin": 100.0,
        "market_type": "SWAP",
        "leverage": 3,
        "position": {
            "symbol": "BTC/USDT",
            "side": "NONE",              # LONG, SHORT, or NONE
            "amount_btc": 0.0,
            "entry_price": 0.0,
            "margin_used": 0.0,
            "leverage": 3,
            "liquidation_price": 0.0,
            "entry_time": "",
            "highest_pnl_pct": 0.0,
        },
        "history": [],
    }


def save_state(state: dict):
    """Save persistent state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def fetch_swap_signals(gw: BingXGateway, symbol: str = "BTC/USDT") -> dict:
    """Fetch live swap ticker and compute 1h indicators (RSI 14, EMA 21, EMA 50)."""
    ticker = gw.fetch_ticker(symbol, market_type=MarketType.SWAP.value)
    price = ticker.get("price", 0.0)

    try:
        klines_resp = gw.client.fetch_klines(gw.to_bingx_symbol(symbol), interval="1h", limit=40)
        k_data = klines_resp.get("data", [])
        closes = [float(x[4]) for x in k_data][::-1] if k_data else [price]
    except Exception:
        closes = [price]

    rsi = 50.0
    ema21 = price
    ema50 = price

    if len(closes) >= 15:
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains[-14:]) / 14
        avg_loss = sum(losses[-14:]) / 14
        if avg_loss > 0:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        k21 = 2.0 / (21.0 + 1.0)
        e21 = closes[0]
        for c in closes[1:]:
            e21 = c * k21 + e21 * (1.0 - k21)
        ema21 = e21

        k50 = 2.0 / (50.0 + 1.0)
        e50 = closes[0]
        for c in closes[1:]:
            e50 = c * k50 + e50 * (1.0 - k50)
        ema50 = e50

    return {
        "price": price,
        "bid": ticker.get("bid", price),
        "ask": ticker.get("ask", price),
        "rsi": rsi,
        "ema21": ema21,
        "ema50": ema50,
    }


def execute_swap_open(state: dict, price: float, side: str, margin_amount: float, leverage: int, reason: str, sig: dict = None):
    """Execute autonomous simulated swap open position (LONG or SHORT) and register journal."""
    pos = state["position"]
    avail = state["available_margin"]
    actual_margin = min(margin_amount, avail)
    if actual_margin <= 0:
        return

    notional = actual_margin * leverage
    btc_qty = notional / price
    state["available_margin"] -= actual_margin
    side = side.upper()

    if pos["side"] == "NONE":
        entry = journal_mgr.on_trade_open(
            symbol="BTC/USDT",
            market_type="SWAP",
            side=side,
            entry_price=price,
            amount_btc=btc_qty,
            margin_used=actual_margin,
            leverage=leverage,
            raw_reason=reason,
            snapshot_dict=sig or {"price": price},
            stop_loss_pct=3.0,
            trailing_pullback_pct=1.0,
        )
        liq_price = entry.liquidation_price
        state["position"] = {
            "symbol": "BTC/USDT",
            "side": side,
            "amount_btc": btc_qty,
            "entry_price": price,
            "margin_used": actual_margin,
            "leverage": leverage,
            "liquidation_price": liq_price,
            "entry_time": entry.entry_time,
            "highest_pnl_pct": 0.0,
            "journal_id": entry.journal_id,
        }

        # Place order on Gateway with Atomic Native Stop-Loss
        try:
            gw.create_order(
                symbol="BTC/USDT",
                side="BUY" if side == "LONG" else "SELL",
                order_type="MARKET",
                size=btc_qty,
                market_type=MarketType.SWAP.value,
                position_side=side,
                leverage=leverage,
                stop_loss_price=entry.risk_plan.stop_loss_price,
            )
        except Exception as e:
            log_msg(f"[下單警示] 網關掛單異常: {e} (已由本地狀態及日誌備援紀錄)")

        log_msg(f"【合約開倉 ({side})】原因: {reason} | 價格: ${price:,.2f} | 原生硬停損: ${entry.risk_plan.stop_loss_price:,.2f} (-3.0%) | 保證金: ${actual_margin:.2f} U ({leverage}x, 名義: ${notional:,.2f}) | 數量: {btc_qty:.6f} BTC | 強平價: ${liq_price:,.2f} | 日誌: {entry.journal_id}")
    elif pos["side"] == side:
        # DCA / Add Position on same side
        old_amt = pos["amount_btc"]
        old_cost = old_amt * pos["entry_price"]
        new_amt = old_amt + btc_qty
        new_avg_price = (old_cost + notional) / new_amt
        pos["amount_btc"] = new_amt
        pos["entry_price"] = new_avg_price
        pos["margin_used"] += actual_margin
        liq_price = new_avg_price * (1.0 - (0.9 / leverage)) if side == "LONG" else new_avg_price * (1.0 + (0.9 / leverage))
        pos["liquidation_price"] = liq_price
        log_msg(f"【合約加碼補倉 ({side})】原因: {reason} | 價格: ${price:,.2f} | 加碼保證金: ${actual_margin:.2f} U | 新均價: ${new_avg_price:,.2f} | 總部位: {new_amt:.6f} BTC")

    save_state(state)


def execute_swap_close(state: dict, price: float, reason: str):
    """Execute autonomous simulated swap close position and finalize trade journal."""
    pos = state["position"]
    if pos["side"] == "NONE":
        return

    side = pos["side"]
    entry_p = pos["entry_price"]
    qty = pos["amount_btc"]
    margin = pos["margin_used"]

    if side == "LONG":
        pnl = (price - entry_p) * qty
    else:  # SHORT
        pnl = (entry_p - price) * qty

    pnl_pct = (pnl / margin) * 100 if margin > 0 else 0.0
    returned_cash = max(0.0, margin + pnl)

    state["available_margin"] += returned_cash
    record = {
        "closed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "side": side,
        "entry_price": entry_p,
        "exit_price": price,
        "amount_btc": qty,
        "margin_used": margin,
        "pnl_usdt": pnl,
        "pnl_pct": pnl_pct,
        "reason": reason,
    }
    state["history"].append(record)

    journal_id = pos.get("journal_id")
    if journal_id:
        journal_mgr.on_trade_close(journal_id, exit_price=price, exit_reason=reason)

    # Cancel native conditional stop orders on exchange upon closing
    try:
        gw.cancel_all_orders("BTC/USDT", market_type=MarketType.SWAP.value)
    except Exception as e:
        log_msg(f"[撤單警告] 取消雲端掛單失敗: {e}")

    state["position"] = {
        "symbol": "BTC/USDT",
        "side": "NONE",
        "amount_btc": 0.0,
        "entry_price": 0.0,
        "margin_used": 0.0,
        "leverage": pos.get("leverage", 3),
        "liquidation_price": 0.0,
        "entry_time": "",
        "highest_pnl_pct": 0.0,
    }
    save_state(state)
    log_msg(f"【合約平倉獲利/止損】原因: {reason} | 賣出價: ${price:,.2f} (開倉: ${entry_p:,.2f}) | 盈虧: ${pnl:+,.2f} USDT ({pnl_pct:+.2f}%) | 剩餘可用保證金: ${state['available_margin']:.2f} USDT")
    log_msg(f"【合約平倉結算 ({side})】原因: {reason} | 結算價: ${price:,.2f} (開倉: ${entry_p:,.2f}) | 盈虧: ${pnl:+,.2f} USDT ({pnl_pct:+.2f}%) | 剩餘可用保證金: ${state['available_margin']:.2f} USDT")


def main():
    global RUNNING
    parser = argparse.ArgumentParser(description="Autonomous Overnight Perpetual Swap Trading Daemon")
    parser.add_argument("--interval", type=int, default=60, help="Loop interval in seconds (default 60s)")
    parser.add_argument("--capital", type=float, default=100.0, help="Initial margin capital (default 100U)")
    parser.add_argument("--leverage", type=int, default=3, help="Leverage multiplier (default 3x)")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    if STOP_FLAG_FILE.exists():
        try:
            STOP_FLAG_FILE.unlink()
        except Exception:
            pass

    log_msg("=" * 65)
    log_msg("  Antigravity (AGY) 永續合約 (SWAP) 過夜自動操盤守護進程啟動")
    log_msg(f"  輪詢週期: 每 {args.interval} 秒 | 市場: BingX 永續合約 BTC-USDT")
    log_msg(f"  保證金本金: ${args.capital:.2f} USDT | 槓桿設定: {args.leverage}x (防插針穩健配置)")
    log_msg("  停止方式: 隨時按 Ctrl+C 或執行指令 `just swap-stop` 即可優雅結算退出")
    log_msg("=" * 65)

    gw = BingXGateway(dry_run=True, default_market_type=MarketType.SWAP.value)
    loop_count = 0

    while RUNNING:
        if STOP_FLAG_FILE.exists():
            log_msg("[信號偵測] 偵測到停止標誌檔案 (swap_stop.flag)，正在結束運行...")
            try:
                STOP_FLAG_FILE.unlink()
            except Exception:
                pass
            break

        loop_count += 1
        try:
            state = load_state()
            sig = fetch_swap_signals(gw, "BTC/USDT")
            price = sig["price"]
            rsi = sig["rsi"]
            ema21 = sig["ema21"]
            pos = state["position"]
            lev = args.leverage

            avail_margin = state["available_margin"]
            used_margin = pos.get("margin_used", 0.0)
            side = pos.get("side", "NONE")
            qty = pos.get("amount_btc", 0.0)
            entry_p = pos.get("entry_price", 0.0)

            # Compute unrealized PnL
            if side == "LONG":
                unrealized_pnl = (price - entry_p) * qty
            elif side == "SHORT":
                unrealized_pnl = (entry_p - price) * qty
            else:
                unrealized_pnl = 0.0

            unrealized_pct = (unrealized_pnl / used_margin * 100) if used_margin > 0 else 0.0
            total_equity = avail_margin + used_margin + unrealized_pnl

            # Update highest PnL achieved and journal trajectory
            if side != "NONE":
                pos["highest_pnl_pct"] = max(pos.get("highest_pnl_pct", 0.0), unrealized_pct)
                if not pos.get("journal_id"):
                    j_entry = journal_mgr.on_trade_open(
                        symbol="BTC/USDT",
                        market_type="SWAP",
                        side=side,
                        entry_price=entry_p,
                        amount_btc=qty,
                        margin_used=used_margin,
                        leverage=lev,
                        raw_reason=f"合約 {side} 部位自主追蹤",
                        entry_time_str=pos.get("entry_time"),
                        snapshot_dict=sig,
                    )
                    pos["journal_id"] = j_entry.journal_id
                journal_mgr.on_trade_update(pos["journal_id"], price)
                save_state(state)

            highest_pct = pos.get("highest_pnl_pct", 0.0)

            pnl_str = f"持倉: {side} {qty:.5f} BTC | 浮動盈虧: ${unrealized_pnl:+,.2f} ({unrealized_pct:+.2f}%)" if side != "NONE" else "空倉待機中"
            log_msg(f"#{loop_count:04d} | 合約價: ${price:,.2f} | RSI: {rsi:.1f} | EMA21: ${ema21:,.2f} | 總權益: ${total_equity:.2f} U | {pnl_str}")

            # ================= SWAP DECISION ENGINE =================
            if side == "NONE":
                # Entry Strategy:
                # 1. Bullish Trend Entry: Price > EMA21 and RSI between 45 and 58
                if price >= ema21 and 45.0 <= rsi <= 58.0:
                    execute_swap_open(state, price, side="LONG", margin_amount=50.0, leverage=lev, reason=f"均線上方多頭動量確認 (RSI={rsi:.1f}, 站穩EMA21)", sig=sig)
                # 2. Oversold Mean-Reversion Long: RSI < 35
                elif rsi < 35.0:
                    execute_swap_open(state, price, side="LONG", margin_amount=50.0, leverage=lev, reason=f"合約短線超賣反彈訊號 (RSI={rsi:.1f} < 35)", sig=sig)
                # 3. Bearish Breakdown Short: Price < EMA21 and RSI between 40 and 48
                elif price < ema21 * 0.995 and 40.0 <= rsi <= 48.0:
                    execute_swap_open(state, price, side="SHORT", margin_amount=50.0, leverage=lev, reason=f"均線跌破空頭順勢開空 (RSI={rsi:.1f}, 跌破EMA21)", sig=sig)

            else:
                pullback_from_peak = highest_pct - unrealized_pct

                # 1. Take Profit Conditions:
                # A. Extreme RSI exhaustion
                if side == "LONG" and rsi >= 73.0 and unrealized_pct >= 2.0:
                    execute_swap_close(state, price, reason=f"1h RSI 極端超買 (RSI={rsi:.1f} >= 73, 獲利 +{unrealized_pct:.2f}%)")
                elif side == "SHORT" and rsi <= 27.0 and unrealized_pct >= 2.0:
                    execute_swap_close(state, price, reason=f"1h RSI 極端超賣 (RSI={rsi:.1f} <= 27, 獲利 +{unrealized_pct:.2f}%)")

                # B. Trailing Take Profit: Gain reached >= 3.0%, pulled back 1.0% from peak
                elif highest_pct >= 3.0 and pullback_from_peak >= 1.0:
                    execute_swap_close(state, price, reason=f"動態移動停利 (波段高點 +{highest_pct:.2f}% 回撤 {pullback_from_peak:.2f}%, 鎖定 +{unrealized_pct:.2f}%)")

                # 2. Hard Stop Loss: -4.0% margin loss
                elif unrealized_pct <= -4.0:
                    execute_swap_close(state, price, reason=f"嚴格保證金停損觸發 (虧損達 {unrealized_pct:.2f}%, 截斷合約風險)")

                # 3. DCA Add Position:
                # If down -1.5% ~ -2.5% in healthy pullback, and still have >= 40U margin, add position
                elif -2.5 <= unrealized_pct <= -1.5 and avail_margin >= 40.0:
                    execute_swap_open(state, price, side=side, margin_amount=avail_margin, leverage=lev, reason=f"逆勢回檔分批攤平 (浮虧 {unrealized_pct:.2f}%, 動用剩餘 ${avail_margin:.2f} U 加碼)")

        except Exception as e:
            log_msg(f"[例外警告] 合約輪詢異常 (自動重試中): {e}")

        for _ in range(args.interval):
            if not RUNNING or STOP_FLAG_FILE.exists():
                break
            time.sleep(1)

    # Post-shutdown summary
    final_state = load_state()
    f_pos = final_state["position"]
    f_avail = final_state["available_margin"]
    f_used = f_pos.get("margin_used", 0.0)
    final_p = gw.fetch_ticker("BTC/USDT", market_type=MarketType.SWAP.value).get("price", 0.0)
    f_side = f_pos.get("side", "NONE")
    f_qty = f_pos.get("amount_btc", 0.0)
    f_entry = f_pos.get("entry_price", final_p)

    if f_side == "LONG":
        unrealized = (final_p - f_entry) * f_qty
    elif f_side == "SHORT":
        unrealized = (f_entry - final_p) * f_qty
    else:
        unrealized = 0.0

    final_equity = f_avail + f_used + unrealized

    log_msg("\n" + "=" * 65)
    log_msg("  合約操盤守護進程已安全停止 - 戰報統計")
    log_msg(f"  總執行輪次 : {loop_count} 次")
    log_msg(f"  初始保證金 : ${final_state['initial_capital']:.2f} USDT")
    log_msg(f"  結算總權益 : ${final_equity:.2f} USDT")
    log_msg(f"  總盈利率   : {((final_equity - final_state['initial_capital'])/final_state['initial_capital']*100):+.2f}%")
    log_msg(f"  累計完成合約交易筆數: {len(final_state.get('history', []))} 筆")
    log_msg(f"  詳細歷史日誌請查閱: {LOG_FILE}")
    log_msg("=" * 65)


if __name__ == "__main__":
    main()
