#!/usr/bin/env python3
"""Live Position and Order Inspector for BingX Perpetual Futures.

Performs read-only inspection of live exchange positions vs local bot states.
Provides immediate situational awareness for autonomous agent interventions.
"""

from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from packages.execution.bingx_gateway import BingXGateway
from packages.core.autopilot_engine import compute_structural_indicators_from_ohlc

TZ_TAIPEI = timezone(timedelta(hours=8))


def inspect_live_status():
    gw = BingXGateway(dry_run=False, enable_ws=False)
    
    # 1. Fetch Real Positions from BingX
    raw_positions = gw.get_positions("BTC/USDT")
    active_exch_positions = [p for p in raw_positions if float(p.get("positionAmt", 0.0)) != 0]

    # 2. Fetch Live Market Ticker & K-lines
    ticker = gw.fetch_ticker("BTC/USDT", market_type="SWAP")
    cur_p = float(ticker.get("price") or 80000.0)

    try:
        resp = gw.client.fetch_swap_klines("BTC-USDT", interval="1h", limit=50)
        k_data = resp.get("data", [])
        if k_data:
            closes = [float(x[4]) for x in k_data][::-1]
            highs = [float(x[2]) for x in k_data][::-1]
            lows = [float(x[3]) for x in k_data][::-1]
            sig = compute_structural_indicators_from_ohlc(closes, highs, lows, cur_p)
        else:
            sig = {"rsi": 50.0, "ema21": cur_p, "bias_pct": 0.0}
    except Exception:
        sig = {"rsi": 50.0, "ema21": cur_p, "bias_pct": 0.0}

    now_tp = datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d %H:%M:%S")

    print("=" * 75)
    print(f"  🔍 【AI 代理人即時單況戰情診斷】 ({now_tp} 台北時間)")
    print(f"  📈 BTC 現價: ${cur_p:,.2f} ｜ 1H RSI: {sig.get('rsi', 50):.1f} ｜ EMA21 乖離: {sig.get('bias_pct', 0):+.2f}%")
    print("=" * 75)

    if not active_exch_positions:
        print("\n  🟢 【交易所持倉】: 目前無真實持倉 (空倉待命中)")
    else:
        for p in active_exch_positions:
            side = p.get("positionSide", "LONG")
            amt = float(p.get("positionAmt", 0.0))
            avg_p = float(p.get("avgPrice", 0.0))
            lev = int(p.get("leverage", 3))
            margin = float(p.get("margin", 0.0))
            liq_p = float(p.get("liquidationPrice", 0.0))
            upnl = float(p.get("unrealizedProfit", 0.0))
            roe = (upnl / margin * 100.0) if margin > 0 else 0.0

            liq_dist = ((cur_p - liq_p) / cur_p * 100.0) if side == "LONG" else ((liq_p - cur_p) / cur_p * 100.0)
            cost_diff = ((cur_p - avg_p) / avg_p * 100.0) if side == "LONG" else ((avg_p - cur_p) / avg_p * 100.0)

            print(f"\n  🔥 【BingX 官方真實持倉 (單一聚合部位)】:")
            print(f"     方向/標的:  {side} BTC-USDT ({lev}x 槓桿)")
            print(f"     持倉總量:  {amt:.4f} BTC (名義價值約 ${amt * cur_p:,.2f} USDT)")
            print(f"     開倉均價:  ${avg_p:,.2f}")
            print(f"     當前市價:  ${cur_p:,.2f} (價格變化: {cost_diff:+.2f}%)")
            print(f"     保證金佔用: ${margin:,.2f} USDT")
            print(f"     浮動損益:  {'+' if upnl>=0 else ''}${upnl:,.2f} USDT ({'+' if roe>=0 else ''}{roe:.2f}% ROE)")
            print(f"     強平防線:  ${liq_p:,.2f} (距離現價安全裕度: {liq_dist:+.1f}%)")

    # 3. Check Local State Files
    print("\n  📋 【本地守護容器狀態對照】:")
    for bot_file in sorted((ROOT_DIR / "data").glob("autopilot_*swap*.json")):
        if "control" in bot_file.name or "journal" in bot_file.name:
            continue
        try:
            with open(bot_file, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            pos = data.get("position", {})
            b_side = pos.get("side", "NONE")
            b_qty = pos.get("amount", 0.0)
            b_cost = pos.get("entry_price", 0.0)
            b_sl = pos.get("native_sl_price", 0.0)
            sl_dist = ((cur_p - b_sl) / cur_p * 100.0) if (b_sl > 0 and b_side == "LONG") else 0.0
            print(f"     • {bot_file.stem:<32}: 狀態={data.get('status')} | 部位={b_side} {b_qty:.4f} BTC | 停損線=${b_sl:,.1f} (距現價 {sl_dist:+.2f}%)")
        except Exception:
            pass

    print("=" * 75)


if __name__ == "__main__":
    inspect_live_status()
