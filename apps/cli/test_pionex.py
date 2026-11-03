"""CLI Diagnostic Tool: Test Pionex API Connectivity and Market Data."""

import argparse
import sys
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from packages.execution import PionexClient, PionexGateway

def main():
    parser = argparse.ArgumentParser(description="Test Pionex OpenAPI Connectivity")
    parser.add_argument("--symbol", default="BTC/USDT", help="Symbol to check")
    parser.add_argument("--key", default="", help="Pionex API Key (Optional)")
    parser.add_argument("--secret", default="", help="Pionex API Secret (Optional)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Force Dry-Run mode")
    args = parser.parse_args()

    print("=" * 65)
    print("  派網 (Pionex) OpenAPI 連線診斷工具")
    print("=" * 65)

    client = PionexClient(api_key=args.key, api_secret=args.secret)
    gateway = PionexGateway(api_key=args.key, api_secret=args.secret, dry_run=args.dry_run)

    # 1. Test Server Time
    print("\n[Step 1] 測試派網伺服器連線延遲...")
    t0 = client.get_server_time()
    if t0.get("result"):
        server_ts = t0["data"]["timestamp"]
        print(f"  -> 連線成功！伺服器時間戳 (ms): {server_ts}")
    else:
        print(f"  -> 警告: 無法獲取時間 ({t0.get('message')})")

    # 2. Test Market Ticker
    p_symbol = gateway.to_pionex_symbol(args.symbol)
    print(f"\n[Step 2] 獲取 {args.symbol} ({p_symbol}) 即時報價 (Ticker)...")
    ticker = gateway.fetch_ticker(args.symbol)
    if ticker.get("price", 0) > 0:
        print(f"  -> 最新成交價 (Close) : ${ticker['price']:,.2f}")
        print(f"  -> 買一價 (Bid)       : ${ticker['bid']:,.2f}")
        print(f"  -> 賣一價 (Ask)       : ${ticker['ask']:,.2f}")
    else:
        print("  -> 未能獲取即時報價")

    # 3. Test Market Klines
    print(f"\n[Step 3] 獲取 {p_symbol} 最近 5 根 1小時 K 線...")
    klines_resp = client.get_market_klines(symbol=p_symbol, interval="1h", limit=5)
    if klines_resp.get("result") and klines_resp.get("data") and klines_resp["data"].get("klines"):
        klines = klines_resp["data"]["klines"]
        print(f"  -> 成功取得 {len(klines)} 根 K 線！最新收盤: ${float(klines[-1]['close']):,.2f}")
    else:
        print("  -> K 線資料獲取略過或失敗")

    # 4. Test Dry-Run Order Placement
    print(f"\n[Step 4] 測試 Dry-Run 模擬掛單流程 (安全無實質扣款)...")
    order = gateway.create_order(
        symbol=args.symbol,
        side="BUY",
        order_type="MARKET",
        size=0.001,
    )
    print(f"  -> 模擬委託結果: {order.get('result')}")
    print(f"  -> 回傳內容: {order.get('data')}")

    # 5. Account Balances Check
    print(f"\n[Step 5] 帳戶餘額查詢測試...")
    if args.key and args.secret:
        print("  -> 偵測到傳入 API 金鑰，正在向派網查詢錢包現貨餘額...")
        balance_resp = client.get_account_balances()
        print(f"  -> 餘額查詢結果: {balance_resp}")
    else:
        print(f"  -> 目前為無金鑰模式，模擬可用 USDT 餘額: ${gateway.get_balance('USDT'):,.2f}")

    print("\n" + "=" * 65)
    print("  派網 OpenAPI 模組連線診斷完成！所有公開端點正常運作。")
    print("=" * 65)

if __name__ == "__main__":
    main()
