# 加密貨幣 AI 多因子量化交易平台 (Crypto AI Quant Trading Platform)

[![Python Version](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/)
[![Architecture](https://img.shields.io/badge/architecture-Modular%20Multi--Package-blueviolet.svg)]()
[![BDD Tests](https://img.shields.io/badge/BDD%20Tests-99%20Passed%20(100%25)-brightgreen.svg)]()
[![Data Leakage](https://img.shields.io/badge/Data%20Leakage-Zero%20Lookahead%20Bias-success.svg)]()
[![Trading Modes](https://img.shields.io/badge/execution-Spot%20%7C%20Swap%20(Futures)-orange.svg)]()
[![CI Workflow](https://github.com/LonelyYeezhiChicken/QuantitativeTrading/actions/workflows/ci.yml/badge.svg)](https://github.com/LonelyYeezhiChicken/QuantitativeTrading/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

本專案是一個具備企業級架構水準的獨立開源加密貨幣量化研究與交易執行平台。系統遵循 **領域驅動多套件架構 (Domain-Driven Multi-Package Architecture)** 與 **行為驅動開發 (BDD - Behavior-Driven Development)** 標準，全面整合多因子特徵工程、LightGBM 機器學習預測、TypeSafe AI (Jev) 短線機率校準決策、年度滾動複利回測評估，以及現貨 (SPOT) 與永續合約 (SWAP) 雙軌經紀商網關（原生支援 BingX OpenAPI 與 Pionex）。

---

## 學術研究與金融風險免責聲明 (Academic Disclaimer & Risk Disclosure)

> [!IMPORTANT]
> **本專案僅供學術研究、演算法驗證、程式教學與模擬交易用途（Academic and Research Purposes Only）。**
> 
> 1. **非財務建議**：本專案內所包含之所有量化模型（包含機器學習回歸/分類器、TypeSafe AI 決策模型、技術因子與回測報告）產出之所有數值與買賣訊號，**均不構成任何形式之投資、財務、法律或稅務諮詢建議**。
> 2. **加密貨幣市場極端波動風險**：加密貨幣及其衍生金融商品（包含但不限於永續合約、槓桿部位）具備高度波動性與流動性風險，槓桿交易更可能導致投資本金全額損失。
> 3. **使用者自負全責**：任何個人或機構若使用本專案程式代碼連接實盤交易所（如 BingX、Pionex 等）進行真實資金交易，**所有交易決策、槓桿設定與財務盈虧均由使用者自行承擔**，專案發起人與協作者概不承擔任何直接或間接之財產損失或法律責任。
> 4. **演練隔離機制**：為確保資金安全，本系統全模組預設啟用 **`dry_run = True`** 安全演練機制，未經明確配置絕不向交易所發送實體扣款請求。

---

## 系統架構一覽 (System Architecture)

系統採用高度解耦的模組化分層設計，各領域套件職責邊界清晰，具備高可維護性與水平擴展能力：

```text
QuantitativeTrading/
├── .github/
│   └── workflows/ci.yml         # GitHub Actions 持續整合自動化測試流程
├── pyproject.toml               # 現代化套件管理規範與 [project.scripts] 命令註冊
├── justfile                     # 統一任務排程管理器 (Task Runner)
├── .env.example                 # 環境變數安全範本檔 (複製為 .env 使用)
├── .gitignore                   # 安全過濾規則 (嚴格杜絕 .env 與私鑰提交)
├── AGENTS.md                    # 協作者與 AI 代理人工程交接手冊
├── start_dashboard.bat          # 雙擊一鍵啟動視覺化控制台 (Windows 環境)
│
├── packages/                    # 領域核心套件庫 (Core Domain Packages)
│   ├── core/                    # 風控核心、自動操盤中樞 (UnifiedAutopilotEngine) 與狀態倉庫 (BotStateRepository)
│   ├── data/                    # 行情採集與儲存 (CCXT 連線、Parquet 列式資料清洗)
│   ├── features/                # 78+ Alpha 技術因子、無前視偏差 (Leakage-Free) 特徵流水線
│   ├── models/                  # 多元預測與決策引擎 (LightGBM, TypeSafe AI Jev, Ollama, 多體制與斐波那契策略)
│   ├── backtest/                # 摩擦成本撮合引擎、績效指標統計與年度滾動複利回測模組
│   ├── execution/               # 經紀商抽象網關層 (BaseBrokerGateway, BingX, Pionex, PaperBroker)
│   └── journal/                 # 權威交易日誌、多進程並發持久化與自主學習覆盤引擎 (TradeJournalManager)
│
├── apps/                        # 應用層 (Application Endpoints)
│   ├── dashboard/               # Streamlit 金融互動視覺化儀表板 (Plotly K 線與權益曲線)
│   └── cli/                     # 純數字免指令終端控制台與各模組獨立診斷工具
│
└── tests/                       # 行為驅動測試矩陣 (BDD & Unit Tests)
    ├── bdd/                     # 17 套 Gherkin 規格書與 Given-When-Then 步驟 (全數 100% 通過)
    └── ...                      # 前視偏差防護、雙網域容災、保證金計算等單元測試
```

---

## 平台核心特性 (Key Features)

### 1. 現貨 (SPOT) 與 永續合約 (SWAP) 雙軌執行網關
- **現貨市場 (`MarketType.SPOT`)**：全額資金撮合，實體代幣持有增減，無槓桿、無強平機制。
- **永續合約 (`MarketType.SWAP`)**：
  - 支援雙向開倉：多頭 (`LONG`) 與空頭 (`SHORT`)。
  - 自訂槓桿倍數 (`1x ~ 100x`)，依據保證金公式 `(Size * Price) / Leverage` 精確扣除。
  - 動態持倉追蹤與預估強平價 (`liquidationPrice`) 嚴密風控。

### 2. BingX 官方 OpenAPI 深度對接
- **雙網域自動容災 (Failover)**：優先連線 `open-api.bingx.com`，網路異常或逾時自動無縫容災切換至備援網域 `open-api.bingx.pro`。
- **標準 HMAC-SHA256 簽署機制**：毫秒級時間戳校準、ASCII 字典升冪排序、參數注入檢驗，附帶 `X-SOURCE-KEY: BX-AI-SKILL` 標頭。
- **端點涵蓋**：即時報價、五檔深度盤口、多週期 K 線、現貨錢包餘額、合約保證金權益與活躍持倉查詢。

### 3. TypeSafe AI (Jev) 短線決策引擎
- 整合 System One 快速推理架構，輸出強型別校準機率：
  - 行動決策 (`action: BUY/SELL/HOLD`)
  - 高勝率指數 (`noul: [0, 1]`)
  - 波動風險評級 (`score: 1~5`)
- 內建本地 Mock Fallback 離線推論器，無金鑰或斷網情境下亦能保證 100% 順暢回測與測試。

### 4. 嚴格防範資料外洩 (Zero Data Leakage) 特徵工程
- 技術因子全數採用歷史時窗計算，標籤生成嚴格進行時序位移 (`shift(-1)`)。
- 配備專屬自動化測試 [`tests/test_data_leakage.py`](file:///C:/code/AIDev/QuantitativeTrading/tests/test_data_leakage.py)，杜絕任何前視偏差 (Lookahead Bias)。

### 5. 模組化年度滾動複利回測 (Rolling Compound Backtest)
- 支援任意交易模型插拔，提供跨年度（如 2024、2025 全年）、自訂起始本金（如 100 USDT 滾倉）之滑點手續費真實摩擦回測。

### 6. 極簡全自動操盤中樞 (Unified Autopilot Orchestration)
- **僅需輸入幣種與槓桿倍數**：系統全自動辨識市場體制（現貨吸籌或合約多體制）、自適應計算 ATR 價格停損與動態移動停利。
- **雲端原子性硬停損防護**：單一 API 請求直接向交易所掛上條件單，斷網亦能保證永不穿倉。
- **本地 Ollama AI 選擇題審查與極簡三問覆盤**：開倉前嚴格審查，平倉後自動產出精簡真實覆盤筆記。

### 7. BingX 官方 VST 交易所模擬盤 (Official VST Exchange Simulation)
- **直接與手機 BingX App 同步**：透過 `--vst` 參數直接連接官方模擬交易端點（`open-api-vst.bingx.com`），掛單、成交、持倉與條件單即時呈現在手機 App 模擬倉。
- **真金切換前無痛驗證**：消耗交易所免費贈送之 VST 虛擬幣（零財務風險），徹底驗證整套量化下單、追蹤停利與停損流程，確認無誤後一鍵切換真金實盤。

---

## 統一任務調度 (Task Runner)

專案整合任務排程工具 `just`，透過簡潔指令調度所有量化流水線：

| 指令 | 說明 |
| :--- | :--- |
| **`just vst`** | **啟動 BingX 官方 VST 模擬盤操盤中樞（訂單直接出現在手機 BingX App 模擬倉）** |
| **`just start`** | 啟動全自動量化操盤中樞（預設 BTC 3x 100U，可帶 `--symbol ETH/USDT --leverage 10`） |
| **`just standby`** | 將操盤中樞切換為待機模式（停止開新倉） |
| **`just status`** | 即時查詢操盤中樞持倉、未實現損益與最新精簡交易覆盤 |
| **`just journal`** | 查看最新一筆交易之深度技術快照與覆盤筆記（或指定 ID） |
| **`just gui`** | 啟動 Streamlit 視覺化金融控制台（瀏覽器開啟 `http://localhost:8501`） |
| **`just menu`** | 啟動免指令純數字終端互動選單（輸入 `0~8` 一鍵執行） |
| **`just test`** | 執行全套 99 個單元與 BDD 行為驅動測試（100% PASS） |
| **`just bingx`** | 執行 BingX 官方 OpenAPI 現貨與合約雙軌連線與認證診斷 |
| **`just pionex`** | 測試派網 (Pionex) OpenAPI 連線與即時行情 |
| **`just typesafe`** | 執行 TypeSafe AI (Jev) 短線決策模型診斷 |
| **`just rolling`** | 執行年度滾動複利回測 (如 `just rolling --year 2025 --capital 100`) |
| **`just backtest`** | 執行 LightGBM 模型特徵工程、訓練與摩擦成本回測 |
| **`just paper`** | 執行本地模擬盤撮合推演 (Paper Trading) |
| **`just download`** | 下載或更新主流加密貨幣歷史 K 線數據 |
| **`just sync`** | 初始化或同步 Python 虛擬環境 (`.venv`) |

---

## 快速上手 (Quick Start)

### 1. 系統依賴
- Python 3.12+ (支援 Python 3.14)
- [uv](https://github.com/astral-sh/uv) (極速 Python 套件管理器)
- [just](https://github.com/casey/just) (指令任務調度器)

### 2. 安裝與環境同步
```bash
# 複製環境變數範本
cp .env.example .env

# 自動建立虛擬環境並安裝所有依賴
just sync
```

### 3. 配置金鑰 (選填)
編輯 `.env` 填入您的交易所或模型金鑰（本系統所有模組具備 Mock 與 Dry-Run 防護，**不配置金鑰亦可 100% 離線運行回測與測試**）：
```env
BINGX_API_KEY=your_bingx_api_key_here
BINGX_API_SECRET=your_bingx_api_secret_here
```

### 4. 驗證與啟動
```bash
# 1. 執行全套自動化測試
just test

# 2. 啟動視覺化控制台
just gui
```

---

## 協作與工程交接 (Engineering Handover)

本專案提供專為工程師與 AI 代理人撰寫的技術交接手冊：
[AGENTS.md](file:///C:/code/AIDev/QuantitativeTrading/AGENTS.md)

涵蓋模組契約、資料流管線、BDD 規範實踐及資安準則。

---

## 授權協議 (License)

本專案採用 [MIT License](LICENSE) 開源授權協議。
