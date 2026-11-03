# Crypto AI Quant Monorepo Task Runner (Justfile)
# 使用方式：輸入 `just` 或 `just --list` 查看所有可用指令

set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# 預設動作：顯示所有指令清單
default:
    @just --list

# 同步並安裝 Python 依賴與建立虛擬環境 (.venv)
sync:
    uv venv --python 3.14 --system-site-packages --clear

# 啟動 Streamlit 視覺化控制台 (Web Dashboard)
gui:
    .venv\Scripts\python.exe -m streamlit run apps/dashboard/app.py

# 啟動免指令純數字互動選單 (Terminal Interactive Menu)
menu:
    .venv\Scripts\python.exe apps/cli/interactive_menu.py

# 下載或更新市場行情
download *args:
    .venv\Scripts\python.exe apps/cli/download_data.py {{args}}

# 訓練 LightGBM 模型並執行回測
backtest *args:
    .venv\Scripts\python.exe apps/cli/train_and_backtest.py {{args}}

# 執行年度滾倉複利回測 (如: just rolling --year 2025 --capital 100)
rolling *args:
    .venv\Scripts\python.exe apps/cli/run_rolling_backtest.py {{args}}

# 測試派網 (Pionex) OpenAPI 連線與即時報價
pionex *args:
    .venv\Scripts\python.exe apps/cli/test_pionex.py {{args}}

# 測試 BingX (盈幣) 官方 OpenAPI 連線與即時報價
bingx *args:
    .venv\Scripts\python.exe apps/cli/test_bingx.py {{args}}

# 測試 TypeSafe AI (Jev) 短線決策引擎
typesafe *args:
    .venv\Scripts\python.exe apps/cli/test_typesafe.py {{args}}

# 執行模擬盤推演
paper *args:
    .venv\Scripts\python.exe apps/cli/paper_trade.py {{args}}

# 執行全套單元與 BDD 測試案例
test *args:
    .venv\Scripts\python.exe -m pytest tests/ {{args}}
