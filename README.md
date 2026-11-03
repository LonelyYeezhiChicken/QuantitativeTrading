# 🚀 加密貨幣 AI 多因子量化交易系統 (Crypto AI Monorepo)

[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/)
[![Architecture Monorepo](https://img.shields.io/badge/architecture-SNEK%20Monorepo-orange.svg)]()
[![BDD Verified](https://img.shields.io/badge/tests-BDD%2028%20Passed-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

本專案是一個遵循 **SNEK Monorepo 現代化多套件架構** 與 **BDD (行為驅動開發)** 原則打造的加密貨幣量化研究與自動化交易系統。支援多因子機器學習預測（LightGBM）、TypeSafe AI (Jev) 短線高勝率決策、年度滾動複利回測，以及現貨 (SPOT) 與永續合約 (SWAP) 雙軌經紀商網關（BingX、Pionex）。

---

## ⚠️ 學術研究與風險免責聲明 (Academic Disclaimer)

> [!IMPORTANT]
> **本專案僅供學術研究、程式設計教學、演算法驗證與模擬交易用途（Academic and Research Purposes Only）。**
> 
> 1. **非投資建議**：本專案內所包含之所有量化模型（含機器學習、TypeSafe AI 決策引擎、指標與回測腳本）產出之數據與買賣訊號，**均不構成任何形式之財務、投資、法律或稅務建議**。
> 2. **加密貨幣市場高風險性**：加密貨幣及其衍生性金融商品（含永續合約、槓桿代幣）具有極高之市場價格波動風險，可能導致投資本金全額損失。
> 3. **自負盈虧**：任何使用者若使用本專案程式代碼連接實盤交易所（包含但不限於 BingX、Pionex 等）進行真實資金交易，**一切操作決策與盈虧風險均由使用者自行完全承擔**，專案作者及所有協作者概不承擔任何直接、間接或衍生之財務損失與法律責任。
> 4. **安全演練模式**：本系統所有交易模組預設啟用 `dry_run = True` 安全演練機制，絕不會在未經確認下動用實體資產。

---

## 🏗️ 系統架構一覽 (Monorepo Architecture)

```text
QuantitativeTrading/
├── pyproject.toml               # 現代化套件管理與 [project.scripts] 進入點
├── justfile                     # 統一任務排程器 (Task Runner)
├── .env.example                 # 環境變數安全範本檔 (複製為 .env 使用)
├── .gitignore                   # 資安防護配置 (嚴格忽略 .env 與高敏私鑰)
├── AI_HANDOVER.md               # 🤖 AI 與團隊協作交接指南 (必讀)
├── start_dashboard.bat          # 雙擊一鍵啟動視覺化控制台 (Windows)
│
├── packages/                    # 📦 領域核心套件庫 (Domain Packages)
│   ├── core/                    # 全域配置與風控模型 (ATR 停損停利、Kelly 資金管理)
│   ├── data/                    # CCXT 行情下載器、Parquet 與 DuckDB 存儲
│   ├── features/                # 78 項技術因子庫、時序 Pipeline 與標籤生成 (防止前視偏差)
│   ├── models/                  # 原生 LightGBM 模型與 TypeSafe AI (Jev) 短線決策引擎
│   ├── backtest/                # 摩擦成本回測、Sharpe/MDD 評估與年度滾動複利模組
│   └── execution/               # 交易網關層 (BaseBrokerGateway, BingX, Pionex, PaperBroker)
│
├── apps/                        # 🚀 終端應用程式層 (Applications)
│   ├── dashboard/               # Streamlit 視覺化控制台與 Plotly 金融互動圖表
│   └── cli/                     # 免指令終端選單與各模組專用診斷工具
│
└── tests/                       # 🧪 自動化測試與 BDD 規格
    ├── bdd/                     # Gherkin .feature 規格書與 Given-When-Then 步驟
    │   ├── bingx_integration.feature
    │   ├── dashboard_behavior.feature
    │   ├── market_type_spot_swap.feature
    │   ├── pionex_integration.feature
    │   └── typesafe_decision.feature
    └── ...                      # 28 項單元與集成測試 (100% 通過)
```

---

## ✨ 核心特性

- **現貨 (SPOT) / 永續合約 (SWAP) 雙軌交易**：
  - 現貨交易全額扣減現金，實體持幣增減（無槓桿/無強平）。
  - 合約交易支援多單（`LONG`）與空單（`SHORT`）、槓桿倍數自訂（`1x~100x`）、起始保證金扣減與動態強平價（`liquidationPrice`）估算。
- **BingX (盈幣) 官方 OpenAPI 經紀商對接**：
  - 完整支援官方 AI Skill 規範，雙網域自動容災 (`open-api.bingx.com` / `.pro`)。
  - 毫秒級時間戳與 ASCII 升冪排序 HMAC-SHA256 簽署機制。
- **派網 (Pionex) OpenAPI 獨立網關**：
  - 模組化介面，支援最新行情、深度盤口與安全演練下單。
- **TypeSafe AI (Jev) 短線決策引擎預留**：
  - 基於強型別校準機率，輸出 `action` (`BUY/SELL/HOLD`)、高勝率指標 (`noul`) 與風險評級 (`score`)。
  - 內建本地 Mock Fallback 模擬器，無金鑰亦可完整離線回測與測試。
- **年度滾動複利回測模組**：
  - 支援設定初始本金、摩擦成本與年度滾倉複利試算（如從 100 USDT 起滾）。
- **雙擊一鍵啟動 & 免指令終端選單**：
  - 支援 Web GUI 控制台 (`apps/dashboard`) 與純數字互動終端 (`interactive_menu.py`)。

---

## ⚡ 常用快捷指令 (`just`)

本專案使用 `just` 工具快速調度所有任務（輸入 `just` 或 `just --list` 查看所有命令）：

| 指令 | 說明 |
| :--- | :--- |
| **`just gui`** | 啟動 Streamlit 視覺化 Web 控制台（自動開啟 `http://localhost:8501`） |
| **`just menu`** | 啟動免指令純數字終端互動選單（按數字 `0~8` 一鍵操作） |
| **`just test`** | 執行全套 28 個單元與 BDD 行為驅動測試案例 |
| **`just bingx`** | 執行 BingX OpenAPI 現貨與合約雙軌即時連線診斷 |
| **`just pionex`** | 測試派網 (Pionex) OpenAPI 連線與即時行情 |
| **`just typesafe`** | 測試 TypeSafe AI (Jev) 短線決策模型診斷 |
| **`just rolling`** | 執行年度滾倉複利回測 (如 `just rolling --year 2025 --capital 100`) |
| **`just backtest`** | 執行 LightGBM 模型特徵工程、訓練與摩擦成本回測 |
| **`just paper`** | 執行本地模擬盤撮合推演 (Paper Trading) |
| **`just download`** | 下載主流幣種歷史 K 線行情資料 |
| **`just sync`** | 初始化或重建虛擬環境 (`.venv`) |

---

## 🚀 快速上手 (Quick Start)

### 1. 環境需求
- Python 3.14+ (或 3.12+)
- [uv](https://github.com/astral-sh/uv) (高速 Python 套件管理器)
- [just](https://github.com/casey/just) (任務排程器)

### 2. 環境安裝
```bash
# 複製環境變數範本
cp .env.example .env

# 安裝依賴並建立虛擬環境
just sync
```

### 3. 配置 API 金鑰 (選填)
編輯 `.env` 填入您的交易所或模型金鑰（注意：系統具備 Mock 與 Dry-Run 機制，**不填寫亦可離線完整運行所有回測與測試**）：
```env
BINGX_API_KEY=your_key_here
BINGX_API_SECRET=your_secret_here
```

### 4. 執行驗證
```bash
# 執行全套測試
just test

# 啟動 Web 控制台
just gui
```

---

## 🤝 協作與 AI 交接指南

若您是團隊新成員、外部協作者或 AI Agent，請務必先閱讀完整的交接文件：
👉 **[AI_HANDOVER.md](file:///C:/code/AIDev/QuantitativeTrading/AI_HANDOVER.md)**

文件內包含：
- 完整的模組相依關係與核心 Class 介面
- BDD 規格增修規範
- 策略新增與回測流水線實作指南
- 資安防護準則（禁止提交任何私密金鑰）

---

## 📄 授權條款 (License)

本專案基於 [MIT License](LICENSE) 條款開源發布。
