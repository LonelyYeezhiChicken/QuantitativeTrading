# Crypto AI Quant Task Runner (Justfile)
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

# 啟動全自動量化操盤中樞 (指定幣種與槓桿，其餘全自動，預設武裝開跑)
start *args:
    .venv\Scripts\python.exe -u apps/cli/autopilot.py --arm --run-loop {{args}}

# 切換操盤中樞為待機狀態 (停止開新倉)
standby *args:
    .venv\Scripts\python.exe apps/cli/autopilot.py --disarm {{args}}

# 即時查看操盤中樞狀態與最新精簡交易日誌
status *args:
    .venv\Scripts\python.exe apps/cli/autopilot.py --status {{args}}

# 執行年度滾倉複利回測 (如: just rolling --year 2025 --capital 100)
rolling *args:
    .venv\Scripts\python.exe apps/cli/run_rolling_backtest.py {{args}}

# 執行五年 (2021~2025) BTC 全策略回測與收斂矩陣
matrix *args:
    .venv\Scripts\python.exe apps/cli/run_5year_backtest_matrix.py {{args}}

# 【現貨 100U】啟動過夜自動操盤守護進程 (按 Ctrl+C 即可退出)
bot *args:
    .venv\Scripts\python.exe apps/cli/overnight_trading_bot.py {{args}}

# 【現貨 100U】停止現貨操盤守護進程 (優雅結算並輸出戰報)
bot-stop:
    powershell.exe -Command "New-Item -Path data/bot_stop.flag -ItemType File -Force | Out-Null; Write-Host '[現貨信號已送出] 已寫入停止信號，現貨守護進程將於下一次心跳結算退出。'"

# 【現貨 100U】即時查看現貨操盤日誌 (最近 25 行)
bot-log:
    powershell.exe -Command "if (Test-Path logs/overnight_bot.log) { Get-Content logs/overnight_bot.log -Tail 25 } else { Write-Host '目前尚未產生現貨操盤日誌。' }"

# 【合約 100U】啟動永續合約過夜自動操盤守護進程 (按 Ctrl+C 即可退出)
swap-bot *args:
    .venv\Scripts\python.exe apps/cli/overnight_swap_bot.py {{args}}

# 【合約 100U】停止合約操盤守護進程 (優雅結算並輸出戰報)
swap-stop:
    powershell.exe -Command "New-Item -Path data/swap_stop.flag -ItemType File -Force | Out-Null; Write-Host '[合約信號已送出] 已寫入停止信號，合約守護進程將於下一次心跳結算退出。'"

# 【合約 100U】即時查看合約操盤日誌 (最近 25 行)
swap-log:
    powershell.exe -Command "if (Test-Path logs/overnight_swap_bot.log) { Get-Content logs/overnight_swap_bot.log -Tail 25 } else { Write-Host '目前尚未產生合約操盤日誌。' }"

# 【高槓桿 10x 合約】啟動 10 倍槓桿 BTC 永續合約守護進程 (按 Ctrl+C 即可退出)
swap-10x *args:
    .venv\Scripts\python.exe -u apps/cli/overnight_swap_bot.py --leverage 10 --name swap_10x_100u {{args}}

# 【高槓桿 10x 合約】停止 10 倍槓桿合約守護進程 (優雅結算並輸出戰報)
swap-10x-stop:
    powershell.exe -Command "New-Item -Path data/swap_10x_100u_stop.flag -ItemType File -Force | Out-Null; Write-Host '[高槓桿信號已送出] 已寫入停止信號，10x 守護進程將於下一次心跳結算退出。'"

# 【高槓桿 10x 合約】即時查看 10 倍槓桿合約操盤日誌 (最近 25 行)
swap-10x-log:
    powershell.exe -Command "if (Test-Path logs/overnight_swap_10x_100u.log) { Get-Content logs/overnight_swap_10x_100u.log -Tail 25 } else { Write-Host '目前尚未產生 10x 合約操盤日誌。' }"

# 100U BTC 即時持倉狀態與戰果分析
btc *args:
    .venv\Scripts\python.exe apps/cli/bingx_paper_tracker.py {{args}}

# 查看交易自主學習日誌 (最新一筆或指定 ID 覆盤)
journal *args:
    .venv\Scripts\python.exe apps/cli/trade_journal_viewer.py {{args}}

# 歷史交易自主學習日誌清單總覽
journal-list *args:
    .venv\Scripts\python.exe apps/cli/trade_journal_viewer.py --list {{args}}

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
