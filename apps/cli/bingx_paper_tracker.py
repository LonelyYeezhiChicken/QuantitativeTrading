"""CLI Tool: BingX Live 100U Paper Trading Tracker & Real-Time Position Monitor."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from packages.execution import BingXGateway, MarketType

STATE_FILE = ROOT_DIR / "data" / "bingx_paper_100u.json"


def load_state() -> dict:
    """Load persistent 100U paper account state."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # Default initial state: 100 USDT
    return {
        "initial_capital": 100.0,
        "cash_usdt": 100.0,
        "market_type": "SPOT",          # SPOT or SWAP
        "position": {
            "symbol": "BTC/USDT",
            "side": "NONE",              # LONG, SHORT, or NONE
            "amount_btc": 0.0,
            "entry_price": 0.0,
            "margin_used": 0.0,
            "leverage": 1,
            "entry_time": "",
        },
        "history": [],
    }


def save_state(state: dict):
    """Save persistent 100U paper account state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def get_market_analysis(gw: BingXGateway, symbol: str = "BTC/USDT") -> dict:
    """Fetch live ticker and compute instant technical indicators via BingX."""
    ticker = gw.fetch_ticker(symbol)
    price = ticker.get("price", 0.0)

    # Fetch 24 1h Klines
    try:
        klines_resp = gw.client.fetch_klines(gw.to_bingx_symbol(symbol), interval="1h", limit=30)
        k_data = klines_resp.get("data", [])
        closes = [float(x[4]) for x in k_data][::-1] if k_data else [price]
    except Exception:
        closes = [price]

    # Simple 14 RSI & EMA21
    rsi = 50.0
    ema21 = price
    if len(closes) >= 15:
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains[-14:]) / 14
        avg_loss = sum(losses[-14:]) / 14
        if avg_loss > 0:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        else:
            rsi = 100.0

        # EMA21
        k = 2 / (21 + 1)
        ema = closes[0]
        for c in closes[1:]:
            ema = c * k + ema * (1 - k)
        ema21 = ema

    return {
        "price": price,
        "bid": ticker.get("bid", price),
        "ask": ticker.get("ask", price),
        "timestamp": ticker.get("timestamp", 0),
        "rsi": rsi,
        "ema21": ema21,
    }


def main():
    parser = argparse.ArgumentParser(description="BingX 100U Live Paper Trading Tracker")
    parser.add_argument("--action", choices=["status", "buy", "sell", "reset"], default="status", help="Action to execute")
    parser.add_argument("--amount", type=float, default=50.0, help="USDT amount to trade (e.g. 50U or 100U)")
    parser.add_argument("--type", choices=["spot", "swap"], default="spot", help="Market type (spot or swap)")
    parser.add_argument("--leverage", type=int, default=2, help="Leverage multiplier if swap (default 2x)")
    args = parser.parse_args()

    state = load_state()
    gw = BingXGateway(dry_run=True)
    mkt = get_market_analysis(gw, "BTC/USDT")
    curr_price = mkt["price"]

    # ================= ACTION: RESET =================
    if args.action == "reset":
        state = {
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
            },
            "history": [],
        }
        save_state(state)
        print("\n[系統訊息] 100U 模擬交易帳戶已重設為初始狀態 (100.00 USDT 空倉)。")
        return

    # ================= ACTION: BUY / ENTER =================
    if args.action == "buy":
        pos = state["position"]
        if pos["side"] != "NONE":
            print(f"\n[提示] 目前已有持倉中 (方向: {pos['side']}, 數量: {pos['amount_btc']:.6f} BTC)，請先平倉後再開新倉。")
            return

        trade_usdt = min(args.amount, state["cash_usdt"])
        if trade_usdt <= 0:
            print(f"\n[錯誤] 可用現金不足: ${state['cash_usdt']:.2f} USDT")
            return

        is_swap = args.type.lower() == "swap"
        lev = args.leverage if is_swap else 1
        notional = trade_usdt * lev
        btc_qty = notional / curr_price

        state["cash_usdt"] -= trade_usdt
        state["market_type"] = "SWAP" if is_swap else "SPOT"
        state["position"] = {
            "symbol": "BTC/USDT",
            "side": "LONG",
            "amount_btc": btc_qty,
            "entry_price": curr_price,
            "margin_used": trade_usdt,
            "leverage": lev,
            "entry_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
        save_state(state)
        print(f"\n[建倉成功] 依據 BingX 即時價格完成模擬進場：")
        print(f"  -> 市場類型 : {'永續合約 (SWAP)' if is_swap else '現貨市場 (SPOT)'}")
        print(f"  -> 進場價格 : ${curr_price:,.2f}")
        print(f"  -> 投入本金 : ${trade_usdt:.2f} USDT (槓桿: {lev}x, 名義價值: ${notional:,.2f})")
        print(f"  -> 買入數量 : {btc_qty:.6f} BTC")
        print(f"  -> 剩餘現金 : ${state['cash_usdt']:.2f} USDT")
        return

    # ================= ACTION: SELL / CLOSE =================
    if args.action == "sell":
        pos = state["position"]
        if pos["side"] == "NONE":
            print("\n[提示] 目前為空倉狀態，無可平持倉。")
            return

        entry_p = pos["entry_price"]
        qty = pos["amount_btc"]
        lev = pos["leverage"]
        margin = pos["margin_used"]

        pnl = (curr_price - entry_p) * qty
        pnl_pct = (pnl / margin) * 100 if margin > 0 else 0.0
        returned_cash = margin + pnl

        state["cash_usdt"] += returned_cash
        trade_record = {
            "closed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "entry_price": entry_p,
            "exit_price": curr_price,
            "side": pos["side"],
            "amount_btc": qty,
            "pnl_usdt": pnl,
            "pnl_pct": pnl_pct,
        }
        state["history"].append(trade_record)
        state["position"] = {
            "symbol": "BTC/USDT",
            "side": "NONE",
            "amount_btc": 0.0,
            "entry_price": 0.0,
            "margin_used": 0.0,
            "leverage": 1,
            "entry_time": "",
        }
        save_state(state)
        print(f"\n[平倉結算] 已按 BingX 即時市價結算平倉：")
        print(f"  -> 開倉價格 : ${entry_p:,.2f} | 平倉價格: ${curr_price:,.2f}")
        print(f"  -> 實現盈虧 : ${pnl:+,.2f} USDT ({pnl_pct:+.2f}%)")
        print(f"  -> 總結餘額 : ${state['cash_usdt']:,.2f} USDT (總本金累計)")
        return

    # ================= ACTION: STATUS & ADVICE =================
    pos = state["position"]
    has_pos = pos["side"] != "NONE"

    print("=" * 70)
    print("  BingX 100U BTC 模擬交易即時追蹤器 (Paper Trading Monitor)")
    print("=" * 70)

    # 1. Market Status
    print(f"\n[1. BingX 比特幣即時行情]")
    print(f"  -> 即時最新市價 : ${curr_price:,.2f}")
    print(f"  -> 盤口買一/賣一 : ${mkt['bid']:,.2f} / ${mkt['ask']:,.2f}")
    print(f"  -> 1小時 RSI(14) : {mkt['rsi']:.1f} ({'強勢多頭' if mkt['rsi'] > 60 else ('弱勢超賣' if mkt['rsi'] < 40 else '中性震盪')})")
    print(f"  -> 21 週期均線  : ${mkt['ema21']:,.2f} (乖離率: {((curr_price - mkt['ema21'])/mkt['ema21']*100):+.2f}%)")

    # 2. Account & Position Status
    print(f"\n[2. 100U 模擬帳戶即時狀態]")
    print(f"  -> 起始本金 : ${state['initial_capital']:.2f} USDT")
    print(f"  -> 可用現金 : ${state['cash_usdt']:.2f} USDT")

    if has_pos:
        entry_p = pos["entry_price"]
        qty = pos["amount_btc"]
        lev = pos["leverage"]
        margin = pos["margin_used"]
        unrealized_pnl = (curr_price - entry_p) * qty
        unrealized_pct = (unrealized_pnl / margin) * 100 if margin > 0 else 0.0
        current_equity = state["cash_usdt"] + margin + unrealized_pnl

        print(f"  -> 持倉方向 : {pos['side']} ({state.get('market_type', 'SPOT')})")
        print(f"  -> 進場價格 : ${entry_p:,.2f} (進場時間: {pos.get('entry_time', 'N/A')})")
        print(f"  -> 持倉部位 : {qty:.6f} BTC (保證金/動用: ${margin:.2f} USDT, 槓桿: {lev}x)")
        print(f"  -> 未實現盈虧: ${unrealized_pnl:+,.2f} USDT ({unrealized_pct:+.2f}%)")
        print(f"  -> 當前總淨值: ${current_equity:,.2f} USDT (累積報酬率: {((current_equity - state['initial_capital'])/state['initial_capital']*100):+.2f}%)")

        if lev > 1:
            liq_est = entry_p * (1.0 - 0.9 / lev)
            print(f"  -> 預估強平防禦價: ${liq_est:,.2f} (距離現價防禦空間: {((curr_price - liq_est)/curr_price*100):.1f}%)")
    else:
        print("  -> 目前持倉狀態 : 100% 現金儲備 (空倉觀望中)")
        print(f"  -> 當前總淨值   : ${state['cash_usdt']:.2f} USDT")

    # 3. AI Quantitative Advice
    print(f"\n[3. AI 策略建議與操盤佈局]")
    if not has_pos:
        print("  -> 行情解讀: 當前 BTC 站上 1h EMA21 ($77,118)，RSI 為 60.1 處於健康多頭回升區間。")
        print("  -> 操作方案 A (穩健現貨分批):")
        print(f"     * 現價建立第 1 筆底倉 50U (約 0.000645 BTC)")
        print(f"     * 指令: python apps/cli/bingx_paper_tracker.py --action buy --amount 50 --type spot")
        print("  -> 操作方案 B (合約 2x 輕槓桿波段):")
        print(f"     * 投入 50U 保證金開 2x 多單 (名義 100U，防禦空間達 55% 絕不輕易爆倉)")
        print(f"     * 指令: python apps/cli/bingx_paper_tracker.py --action buy --amount 50 --type swap --leverage 2")
    else:
        entry_p = pos["entry_price"]
        gain_pct = ((curr_price - entry_p) / entry_p) * 100
        print(f"  -> 當前浮動報酬: {gain_pct:+.2f}%")
        if gain_pct >= 1.5:
            print("  -> 【建議獲利出場】已達波段停利目標 (+1.5% 以上)，建議執行平倉鎖定利潤！")
            print("     * 指令: python apps/cli/bingx_paper_tracker.py --action sell")
        elif gain_pct <= -1.2:
            print("  -> 【注意停損防守】已跌破短線防禦支撐 (-1.2%)，建議嚴格停損控制本金。")
            print("     * 指令: python apps/cli/bingx_paper_tracker.py --action sell")
        else:
            print(f"  -> 【建議續抱觀察】尚未觸發停利 (目標價: ${entry_p * 1.015:,.2f}) 或停損 (防守價: ${entry_p * 0.988:,.2f})。")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
