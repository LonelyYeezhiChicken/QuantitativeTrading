# 🤖 AI 與協作者工程交接指南 (Project Handover & Developer Guide)

> **致未來的協作者與 AI 代理人 (AI Coding Agents)**：  
> 本文件旨在為接手本專案的工程師、量化研究員與 AI 提供完整的系統全景、設計哲學、架構規範、環境配置及開發守則。在進行任何重大改動前，請務必先通讀本指南。

---

## 1. 專案背景與設計哲學

本專案是一個現代化、模組化、高覆蓋測試的加密貨幣量化研究與交易系統。  
核心設計哲學遵循：
1. **SNEK Monorepo 多套件架構**：領域邊界清晰，套件可獨立測試與複用，所有跨模組調度統一由根目錄管理。
2. **行為驅動開發 (BDD - Behavior-Driven Development)**：所有新功能、新網關或重大架構變更，必須先撰寫 Gherkin `.feature` 規範，再實作對應的 Given-When-Then 測試步驟。
3. **安全第一 (Safety by Default)**：
   - 所有經紀商網關預設必須啟用 `dry_run = True`，未經明確授權絕不調用實盤扣款端點。
   - 所有私密金鑰（API Key, Secret Key）嚴格隔離於 `.env` 中，**嚴禁提交至 Git**。
4. **離線可運行 (Offline & Mock First)**：
   - 無論是回測、特徵工程、或外部第三方模型（如 TypeSafe AI），在缺少網路或金鑰的情況下，均必須具備本地 Mock / Fallback 機制，確保全套測試能 100% 離線通過。

---

## 2. 系統架構與模組權責 (Architecture & Packages)

系統主要由 `packages/`（領域可複用模組）、`apps/`（應用層與使用者介面）以及 `tests/`（測試層）三大支柱構成：

```text
packages/
├── core/
│   └── config.py              # 全域風控配置、ATR 停損/移動停利、Kelly 資金管理
├── data/
│   └── downloader.py          # CCXT 行情抓取器、Parquet 列式存儲與資料清洗
├── features/
│   └── pipeline.py            # 78+ 技術因子生成、標籤 Pipeline (嚴格防範前視偏差 Data Leakage)
├── models/
│   ├── base.py                # BaseTradingModel 統一預測模型抽象介面
│   ├── lgbm_model.py          # 原生 LightGBM 迴歸/分類訓練器 (Purged CV 驗證)
│   └── typesafe_agent.py      # TypeSafe AI (Jev) 短線決策引擎 (支援 System One 機率校準與 Mock)
├── backtest/
│   ├── engine.py              # 摩擦成本撮合回測引擎、Sharpe/MDD 統計
│   └── rolling_backtester.py  # 模組化年度滾動複利回測器 (Rolling Compound Backtest)
└── execution/
    ├── base.py                # BaseBrokerGateway 抽象網關 (定義 MarketType.SPOT 與 SWAP)
    ├── paper_broker.py        # 本地虛擬盤帳戶撮合器 (Paper Trading State)
    ├── pionex_client.py       # 派網 (Pionex) REST 客戶端 (HMAC-SHA256 簽名)
    ├── pionex_gateway.py      # 派網高階經紀商網關
    ├── bingx_client.py        # BingX 官方 OpenAPI 客戶端 (雙網域容災、升冪排序簽章)
    └── bingx_gateway.py       # BingX 高階經紀商網關 (支援現貨與合約雙軌獨立資產管理)
```

---

## 3. 環境準備與依賴管理

專案使用現代化高效 Python 工具鏈：
- **Python 版本**：3.14+ (相容 3.12+)
- **套件管理器**：[uv](https://github.com/astral-sh/uv) (高速解析與虛擬環境管理)
- **指令任務排程**：[just](https://github.com/casey/just)

### 快速初始化流程
```bash
# 1. 複製環境變數範本
cp .env.example .env

# 2. 自動建立虛擬環境 (.venv) 並安裝所有依賴
just sync

# 3. 執行全套測試驗證環境
just test
```

---

## 4. 環境變數配置 (.env) 指南

專案根目錄下需配置 `.env` 檔案（該檔案已被 `.gitignore` 排除）：

```env
# ==============================================================================
# BingX (盈幣) 官方 OpenAPI 憑證
# ==============================================================================
BINGX_API_KEY=your_bingx_api_key_here
BINGX_API_SECRET=your_bingx_api_secret_here

# ==============================================================================
# Pionex (派網) OpenAPI 憑證 (選填)
# ==============================================================================
PIONEX_API_KEY=your_pionex_api_key_here
PIONEX_API_SECRET=your_pionex_api_secret_here

# ==============================================================================
# TypeSafe AI (Jev) 憑證 (選填，無金鑰時自動啟用 Mock 決策)
# ==============================================================================
TYPESAFE_API_KEY=your_typesafe_api_key_here
```

> **重要說明**：
> 1. `BINGX_API_KEY` 與 `BINGX_API_SECRET` 是成對使用的。若未配置 Secret Key，私有資產查詢端點將無法計算 HMAC-SHA256 簽章。
> 2. 系統會自動讀取 `.env`，若未提供金鑰，系統將安全地回退為模擬帳戶與公開行情運作。

---

## 5. 現貨 (SPOT) 與 永續合約 (SWAP) 雙軌架構

在 `packages/execution/base.py` 中定義了核心枚舉：
```python
class MarketType(str, Enum):
    SPOT = "SPOT"      # 現貨 (Spot Asset Trading)
    SWAP = "SWAP"      # 永續合約 (Perpetual Futures / Swap)
```

### 兩者運作機制差異：
- **現貨市場 (`MarketType.SPOT`)**：
  - 以現金（USDT）全額買入基礎幣種（BTC、ETH）。
  - 不存在槓桿，無強平機制。
  - 下單調用 `/openApi/spot/v1/...`。
- **永續合約 (`MarketType.SWAP`)**：
  - 支援雙向開倉：多頭 (`position_side="LONG"`) 與 空頭 (`position_side="SHORT"`)。
  - 具備槓桿倍數 (`leverage`: 1x~100x)，僅扣除起始保證金：`Margin = (Size * Price) / Leverage`。
  - 自動追蹤持倉、計算未實現盈虧與預估強平價格 (`liquidationPrice`)。
  - 下單調用 `/openApi/swap/v2/...`，帳戶保證金調用 `/openApi/swap/v3/...`。

---

## 6. TypeSafe AI (Jev) 短線決策引擎

模組路徑：[`packages/models/typesafe_agent.py`](file:///C:/code/AIDev/QuantitativeTrading/packages/models/typesafe_agent.py)
- **定位**：針對 15m/1h 級別進行高頻突破或插針反轉決策。
- **強型別輸出合約**：
  - `action`: `BUY` / `SELL` / `HOLD`
  - `is_high_conviction`: $[0, 1]$ 嚴格校準之二元高勝率機率 (`noul`)
  - `volatility_risk`: 1~5 級波動風險評級 (`score`)
- **離線模擬機制**：
  當環境缺少 `TYPESAFE_API_KEY` 時，系統自動啟用 `mock_fallback`，依據 RSI、EMA Bias 與量能特徵在本地產出強型別預測，確保所有回測與測試皆可離線執行。

---

## 7. BDD 規格驅動開發規範

本專案全面實施 BDD 驗證，所有功能測試存放在 `tests/bdd/`：
1. **編寫 `.feature` 規格書**（例如 `tests/bdd/market_type_spot_swap.feature`）。
2. **實作 Given-When-Then 步驟腳本**（例如 `tests/bdd/test_market_type_scenarios.py`）。
3. 執行測試命令：
   ```bash
   just test
   ```
   **標準要求**：任何 PR 或提交前，必須確保測試 100% 通過（目前全套 28 個測試已全面 PASS）。

---

## 8. 安全與提交流程守則 (Security & Git Workflow)

> [!CAUTION]
> **嚴格禁止將任何 API Key 或 Secret 提交至 Git 倉庫！**

在執行 `git add` 與 `git commit` 前，必須檢查：
1. 確認 `.env` 確實被 `.gitignore` 排除：
   ```bash
   git status --ignored
   ```
2. 檢查工作區內沒有任何 hardcode 的金鑰：
   ```bash
   git grep "API_KEY"
   ```
3. 確認所有新增的單元測試均使用假字串（如 `test_key_123`），絕不使用真實私鑰。

---

## 9. 常用指令速查 (Cheat Sheet)

```bash
# 啟動 Web 視覺化控制台 (Streamlit)
just gui

# 啟動純數字互動終端選單
just menu

# 執行全套 BDD 與單元測試
just test

# 執行 BingX OpenAPI 現貨與合約雙軌連線診斷
just bingx

# 執行年度滾動複利回測 (2025 年，本金 100U)
just rolling --year 2025 --capital 100

# 測試 TypeSafe AI 決策引擎
just typesafe
```

---

## 10. 學術免責聲明 (Disclaimer)

本專案與本代碼庫僅供**學術研究、演算法驗證與程式教學**使用。任何因連接實盤交易所交易而產生的財務損失，使用者須自行完全承擔，專案開發團隊概不負責。
