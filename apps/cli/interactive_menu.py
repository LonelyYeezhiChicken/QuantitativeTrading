"""CLI App: Interactive number-based terminal console for quick actions."""

import sys
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def print_banner():
    print("\n" + "=" * 55)
    print("  AI 量化交易控制台 (Quantitative Trading Engine)")
    print("=" * 55)
    print("  [1] 下載 / 更新比特幣歷史行情 (BTC/USDT 1h)")
    print("  [2] 下載 / 更新以太坊歷史行情 (ETH/USDT 1h)")
    print("  [3] 訓練 LightGBM 模型並產出回測報告 (BTC)")
    print("  [4] 執行模擬盤推演 (Paper Trading)")
    print("  [5] 啟動 Streamlit 視覺化 Web 控制台")
    print("  [6] 測試派網 (Pionex) OpenAPI 連線與即時行情")
    print("  [7] 測試盈幣 (BingX) 官方 OpenAPI 連線與即時行情")
    print("  [8] 執行自動化測試與 BDD 驗證")
    print("  [0] 退出系統")
    print("=" * 55)

def main():
    while True:
        print_banner()
        choice = input("請輸入功能編號 (0-8): ").strip()

        if choice == "1":
            print("\n>>> 正在抓取 BTC/USDT 數據...")
            subprocess.run([sys.executable, str(ROOT_DIR / "apps" / "cli" / "download_data.py"), "--symbol", "BTC/USDT", "--timeframe", "1h"])
        elif choice == "2":
            print("\n>>> 正在抓取 ETH/USDT 數據...")
            subprocess.run([sys.executable, str(ROOT_DIR / "apps" / "cli" / "download_data.py"), "--symbol", "ETH/USDT", "--timeframe", "1h"])
        elif choice == "3":
            print("\n>>> 正在執行特徵工程與模型回測...")
            subprocess.run([sys.executable, str(ROOT_DIR / "apps" / "cli" / "train_and_backtest.py"), "--symbol", "BTC/USDT"])
        elif choice == "4":
            print("\n>>> 正在運行模擬盤撮合...")
            subprocess.run([sys.executable, str(ROOT_DIR / "apps" / "cli" / "paper_trade.py"), "--symbol", "BTC/USDT", "--steps", "24"])
        elif choice == "5":
            print("\n>>> 正在啟動 Web 儀表板 (瀏覽器將自動開啟 http://localhost:8501)...")
            subprocess.run([sys.executable, "-m", "streamlit", "run", str(ROOT_DIR / "apps" / "dashboard" / "app.py")])
        elif choice == "6":
            print("\n>>> 正在測試派網 (Pionex) OpenAPI 連線...")
            subprocess.run([sys.executable, str(ROOT_DIR / "apps" / "cli" / "test_pionex.py")])
        elif choice == "7":
            print("\n>>> 正在測試盈幣 (BingX) 官方 OpenAPI 連線...")
            subprocess.run([sys.executable, str(ROOT_DIR / "apps" / "cli" / "test_bingx.py")])
        elif choice == "8":
            print("\n>>> 正在執行 Pytest 與 BDD 場景測試...")
            subprocess.run([sys.executable, "-m", "pytest", "tests", "-v"])
        elif choice == "0":
            print("\n感謝使用，系統已安全退出！")
            break
        else:
            print("\n[提示] 輸入無效，請輸入 0 到 8 之間的數字。")

        input("\n按 Enter 鍵返回主選單...")

if __name__ == "__main__":
    main()
