"""CLI Diagnostic Tool: Test BingX OpenAPI Connectivity for SPOT and SWAP (Futures)."""

import argparse
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Automatically load environment variables from .env
load_dotenv(ROOT_DIR / ".env")

from packages.execution import BingXClient, BingXGateway, MarketType


def mask_key(k: str) -> str:
    """Mask key for safe logging (e.g., T12o...ybfA)."""
    if not k:
        return "None"
    if len(k) <= 8:
        return "****"
    return f"{k[:4]}...{k[-4:]}"


def main():
    parser = argparse.ArgumentParser(description="Test BingX OpenAPI Connectivity for Spot and Swap")
    parser.add_argument("--symbol", default="BTC/USDT", help="Trading symbol (e.g. BTC/USDT)")
    parser.add_argument("--market-type", choices=["all", "spot", "swap"], default="all", help="Market type (spot, swap, all)")
    parser.add_argument("--key", default="", help="BingX API Key (Defaults to env BINGX_API_KEY)")
    parser.add_argument("--secret", default="", help="BingX API Secret (Defaults to env BINGX_API_SECRET)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Force Dry-Run mode")
    args = parser.parse_args()

    api_key = args.key or os.getenv("BINGX_API_KEY", "")
    api_secret = args.secret or os.getenv("BINGX_API_SECRET", "")

    print("=" * 70)
    print("  盈幣 (BingX) OpenAPI 連線診斷工具 [現貨 SPOT / 合約 SWAP 雙軌]")
    print("=" * 70)

    print(f"\n[金鑰載入檢查 (Credentials Check)]")
    print(f"  -> BINGX_API_KEY    : {mask_key(api_key)}")
    print(f"  -> BINGX_API_SECRET : {mask_key(api_secret)}")
    has_credentials = bool(api_key and api_secret)
    if has_credentials:
        print("  -> 狀態: 成功載入完整金鑰！即將進行真實帳戶資產與保證金授權查詢。")
    else:
        print("  -> 狀態: 尚未配置完整金鑰，將以公開行情端點與模擬帳戶運作。")

    client = BingXClient(api_key=api_key, api_secret=api_secret)
    gateway = BingXGateway(api_key=api_key, api_secret=api_secret, dry_run=args.dry_run)
    bx_symbol = gateway.to_bingx_symbol(args.symbol)

    test_spot = args.market_type in ["all", "spot"]
    test_swap = args.market_type in ["all", "swap"]

    # ================= 1. 現貨 (SPOT) 測試 =================
    if test_spot:
        print("\n" + "─" * 30 + " 【現貨市場 (SPOT) 診斷】 " + "─" * 30)
        # 1.1 Ticker
        print(f"\n[SPOT-1] 查詢 {args.symbol} 現貨即時報價...")
        spot_ticker = gateway.fetch_ticker(args.symbol, market_type=MarketType.SPOT.value)
        if spot_ticker.get("price", 0) > 0:
            print(f"  -> 現貨成交價 : ${spot_ticker['price']:,.2f}")
            print(f"  -> 現貨買一價 : ${spot_ticker['bid']:,.2f} | 賣一價: ${spot_ticker['ask']:,.2f}")
        else:
            print("  -> 未能獲取現貨即時報價")

        # 1.2 Depth
        print(f"\n[SPOT-2] 獲取 {bx_symbol} 現貨盤口深度 (Depth 5 檔)...")
        try:
            depth_resp = client.fetch_depth(symbol=bx_symbol, limit=5)
            depth_data = depth_resp.get("data", {})
            bids = depth_data.get("bids", [])
            asks = depth_data.get("asks", [])
            print(f"  -> 買盤檔數: {len(bids)}, 賣盤檔數: {len(asks)}")
        except Exception as e:
            print(f"  -> 現貨盤口查詢失敗: {e}")

        # 1.3 Real Spot Balances (if credentials exist)
        if has_credentials:
            print(f"\n[SPOT-3] 正在向 BingX 查詢真實現貨錢包餘額 (HMAC 簽章認證)...")
            try:
                spot_balance_resp = client.get_account_balance()
                raw_data = spot_balance_resp.get("data", {})
                balances = raw_data.get("balances", []) if isinstance(raw_data, dict) else (raw_data if isinstance(raw_data, list) else [])
                non_zero = [b for b in balances if float(b.get("free", 0.0)) > 0 or float(b.get("locked", 0.0)) > 0]
                print(f"  -> 現貨錢包認證成功！持有非零幣種數: {len(non_zero)}")
                for b in non_zero[:5]:
                    coin = b.get("asset") or b.get("coin", "")
                    free_amt = float(b.get("free", 0.0))
                    locked_amt = float(b.get("locked", 0.0))
                    print(f"     * {coin}: 可用={free_amt:.6f}, 凍結={locked_amt:.6f}")
                if not non_zero:
                    print("     * (錢包資產均為 0 或尚未充值)")
            except Exception as e:
                print(f"  -> 現貨錢包餘額查詢失敗: {e}")
        else:
            print(f"\n[SPOT-3] 目前為模擬模式，模擬現貨 USDT 餘額: ${gateway.get_balance('USDT', market_type=MarketType.SPOT.value):,.2f}")

        # 1.4 Dry-Run Spot Order
        print(f"\n[SPOT-4] 測試現貨 Dry-Run 買入 0.001 BTC (安全演練，絕不真實扣款)...")
        spot_order = gateway.create_order(
            symbol=args.symbol,
            side="BUY",
            order_type="MARKET",
            size=0.001,
            market_type=MarketType.SPOT.value,
        )
        print(f"  -> 演練委託結果: {spot_order.get('result')}")
        print(f"  -> 模擬訂單單號: {spot_order.get('data', {}).get('orderId')}")

    # ================= 2. 永續合約 (SWAP) 測試 =================
    if test_swap:
        print("\n" + "─" * 30 + " 【永續合約 (SWAP) 診斷】 " + "─" * 30)
        # 2.1 Swap Ticker
        print(f"\n[SWAP-1] 查詢 {args.symbol} 合約即時最新行情與指數標記價...")
        swap_ticker = gateway.fetch_ticker(args.symbol, market_type=MarketType.SWAP.value)
        if swap_ticker.get("price", 0) > 0:
            print(f"  -> 合約最新成交價 : ${swap_ticker['price']:,.2f}")
            print(f"  -> 合約買一價     : ${swap_ticker['bid']:,.2f} | 賣一價: ${swap_ticker['ask']:,.2f}")
        else:
            print("  -> 未能獲取合約即時報價")

        # 2.2 Swap Depth
        print(f"\n[SWAP-2] 查詢 {bx_symbol} 永續合約深度盤口...")
        try:
            s_depth = client.fetch_swap_depth(symbol=bx_symbol, limit=5)
            s_data = s_depth.get("data", {})
            bids = s_data.get("bids", [])
            asks = s_data.get("asks", [])
            print(f"  -> 合約買盤檔數: {len(bids)}, 賣盤檔數: {len(asks)}")
            if bids:
                print(f"  -> 合約最高買價: ${float(bids[0][0]):,.2f}")
            if asks:
                print(f"  -> 合約最低賣價: ${float(asks[0][0]):,.2f}")
        except Exception as e:
            print(f"  -> 合約盤口查詢失敗: {e}")

        # 2.3 Real Swap Balances & Positions (if credentials exist)
        if has_credentials:
            print(f"\n[SWAP-3] 正在向 BingX 查詢真實永續合約保證金與淨值 (HMAC 簽章認證)...")
            try:
                swap_balance_resp = client.get_swap_balance()
                s_bal_data = swap_balance_resp.get("data", {})
                if isinstance(s_bal_data, list):
                    bal_obj = next((b for b in s_bal_data if b.get("asset") == "USDT"), s_bal_data[0] if s_bal_data else {})
                else:
                    bal_obj = s_bal_data.get("balance", s_bal_data) if isinstance(s_bal_data, dict) else {}
                equity = float(bal_obj.get("equity", bal_obj.get("balance", 0.0)))
                avail_margin = float(bal_obj.get("availableMargin", 0.0))
                unrealized_pnl = float(bal_obj.get("unrealizedProfit", 0.0))
                print(f"  -> 合約帳戶認證成功！")
                print(f"     * 合約帳戶淨值 (Equity)       : ${equity:,.2f} USDT")
                print(f"     * 可用保證金 (Available Margin) : ${avail_margin:,.2f} USDT")
                print(f"     * 未實現盈虧 (Unrealized PnL)   : ${unrealized_pnl:,.2f} USDT")
            except Exception as e:
                print(f"  -> 合約帳戶餘額查詢失敗: {e}")

            print(f"\n[SWAP-4] 正在向 BingX 查詢真實當前永續合約持倉 (HMAC 簽章認證)...")
            try:
                pos_resp = client.get_swap_positions()
                pos_data = pos_resp.get("data", [])
                active_pos = [p for p in pos_data if float(p.get("positionAmt", 0.0)) != 0.0]
                print(f"  -> 合約持倉查詢成功！當前活躍持倉筆數: {len(active_pos)}")
                for p in active_pos:
                    print(f"     * 標的: {p.get('symbol')} | 方向: {p.get('positionSide')} | 數量: {p.get('positionAmt')}")
                    print(f"       開倉均價: ${float(p.get('avgPrice', 0.0)):,.2f} | 槓桿: {p.get('leverage')}x | 強平價: ${float(p.get('liquidationPrice', 0.0)):,.2f}")
                if not active_pos:
                    print("     * (目前合約帳戶無活躍在倉部位)")
            except Exception as e:
                print(f"  -> 合約持倉查詢失敗: {e}")

            print(f"\n[SWAP-4.1] 正在向 BingX 查詢真實當前未成交掛單/條件單 (HMAC 簽章認證)...")
            try:
                open_orders_resp = client.get_swap_open_orders(symbol=bx_symbol)
                orders_list = open_orders_resp.get("data", {}).get("orders", [])
                print(f"  -> 未成交訂單查詢成功！當前在掛訂單數: {len(orders_list)}")
                for od in orders_list:
                    print(f"     * 單號: {od.get('orderId')} | 類型: {od.get('type')} | 觸發價: {od.get('stopPrice')} | 數量: {od.get('origQty')}")
                if not orders_list:
                    print("     * (目前合約帳戶無任何在掛條件單或限價單)")
            except Exception as e:
                print(f"  -> 未成交訂單查詢失敗: {e}")
        else:
            print(f"\n[SWAP-3] 目前為模擬模式，模擬可用合約保證金: ${gateway.get_balance('USDT', market_type=MarketType.SWAP.value):,.2f}")

        # 2.4 Dry-Run Swap LONG Order
        print(f"\n[SWAP-5] 測試合約 Dry-Run 開多單 (LONG) 0.01 BTC (安全演練，絕不真實下單)...")
        swap_order = gateway.create_order(
            symbol=args.symbol,
            side="BUY",
            order_type="MARKET",
            size=0.01,
            market_type=MarketType.SWAP.value,
            position_side="LONG",
            leverage=10,
        )
        order_info = swap_order.get("data", {})
        print(f"  -> 演練單號: {order_info.get('orderId')}")
        print(f"  -> 模擬方向: {order_info.get('positionSide')}")
        print(f"  -> 模擬扣除保證金: ${order_info.get('marginRequired', 0):,.2f} USDT")

    print("\n" + "=" * 70)
    print("  BingX 現貨與合約雙軌金鑰連線診斷完成！所有認證請求與安全演練正常。")
    print("=" * 70)


if __name__ == "__main__":
    main()
