# 🤖 系統工程架構與協作交接手冊 (Engineering Handover & Architecture Specification)

> **致接手工程師、量化研究員與 AI 代理人 (AI Coding Agents)**：  
> 本手冊為本專案的權威技術規格書。詳細說明系統的整體設計哲學、分層領域模組契約、環境設定規範、雙軌交易機制與測試準則。在進行任何架構擴充或程式碼異動前，請務必詳閱本手冊。

---

## 1. 系統設計哲學 (Design Principles)

本系統是一套獨立、模組化、高可靠性的現代化加密貨幣量化研究與交易執行平台，整體設計恪守四大核心原則：

1. **領域驅動模組化架構 (Domain-Driven Multi-Package Design)**：
   各業務領域獨立封裝於 `packages/`，彼此透過抽象介面（如 [`BaseTradingModel`](file:///C:/code/AIDev/QuantitativeTrading/packages/models/base.py)、[`BaseBrokerGateway`](file:///C:/code/AIDev/QuantitativeTrading/packages/execution/base.py)）解耦，支援高度可測試性與任意新模型/交易所的隨插即用。
2. **行為驅動開發 (BDD - Behavior-Driven Development)**：
   所有核心業務邏輯、經紀商通訊與交易流程均以 Gherkin 語言撰寫 `.feature` 規範，並以 `pytest-bdd` 實作 Given-When-Then 測試步驟，實現「規格即測試、測試即文檔」。
3. **無資料外洩原則 (Zero Data Leakage)**：
   所有特徵工程（Alpha Factors）嚴格使用過去時序數據計算，預測標籤採用未來位移 (`shift(-1)`)，絕不發生任何前視偏差 (Lookahead Bias)。
4. **安全演練優先 (Safety & Dry-Run First)**：
   所有對外經紀商網關預設強制啟用 `dry_run = True`，未經明確授權絕不調用交易所扣款端點。所有私密金鑰嚴格由 `.env` 託管並納入 `.gitignore`，**嚴禁提交至版本控制系統**。

---

## 2. 領域模組分層與協議契約 (Package Contracts)

```text
packages/
├── core/             # 全域配置與風控層
│   └── config.py     # 集中管理手續費、滑點、ATR 停損乘數、動態部位縮放演算法
│
├── data/             # 行情數據工程層
│   ├── ccxt_fetcher.py # CCXT 異步/同步行情採集器，支援自動重試與速率限制
│   └── data_manager.py # Parquet 列式存儲管線，支援增量更新與高效率歷史快取
│
├── features/         # 因子特徵工程層
│   ├── indicators.py # 78+ 項技術指標庫 (RSI, MACD, Bollinger, ATR, EMA Trend)
│   └── pipeline.py   # 時序因子清洗流水線，自動進行標準化與時序平移防漏
│
├── models/           # 預測與決策模型層
│   ├── base.py       # BaseTradingModel 抽象基類 (定義 train, predict, predict_proba)
│   ├── lgbm_agent.py # 原生 LightGBM 機器學習模型 (支援 Purged K-Fold 時序交叉驗證)
│   ├── rule_based.py # 經典動量與雙均線規則模型 (作為基準 Baseline)
│   └── typesafe_agent.py # TypeSafe AI (Jev) 短線決策引擎 (支援強型別機率校準與 Mock Fallback)
│
├── backtest/         # 回測評估與績效分析層
│   ├── engine.py     # 包含滑點與手續費摩擦之回測撮合引擎
│   ├── metrics.py    # 年化報酬率、Sharpe Ratio、最大回撤 (MDD)、Profit Factor 計算
│   └── rolling_evaluator.py # 年度滾動複利回測器 (Rolling Compound Backtest)
│
└── execution/        # 經紀商執行網關層
    ├── base.py       # BaseBrokerGateway 抽象介面 (定義 MarketType.SPOT 與 MarketType.SWAP)
    ├── paper_broker.py # 本地虛擬撮合錢包 (模擬真實行情下的掛單成交)
    ├── pionex_client.py / pionex_gateway.py # 派網 (Pionex) OpenAPI REST 客戶端與網關
    └── bingx_client.py / bingx_gateway.py   # BingX 官方 OpenAPI 雙網域容災客戶端與網關
```

---

## 3. 現貨 (SPOT) 與 永續合約 (SWAP) 雙軌執行機制

系統在 [`packages/execution/base.py`](file:///C:/code/AIDev/QuantitativeTrading/packages/execution/base.py) 定義了標準枚舉：
```python
class MarketType(str, Enum):
    SPOT = "SPOT"      # 現貨 (Spot Asset Trading)
    SWAP = "SWAP"      # 永續合約 (Perpetual Futures / Swap)
```

### 業務邏輯與風控區隔：
| 維度 | 現貨 (SPOT) | 永續合約 (SWAP) |
| :--- | :--- | :--- |
| **倉位方向** | 僅多頭持幣 (持有現貨資產) | 雙向持倉 ([`LONG`](file:///C:/code/AIDev/QuantitativeTrading/packages/execution/bingx_gateway.py) / [`SHORT`](file:///C:/code/AIDev/QuantitativeTrading/packages/execution/bingx_gateway.py)) |
| **資金佔用** | 扣除 `數量 × 成交價` 全額資金 | 僅扣除起始保證金 `(數量 × 成交價) / 槓桿倍數` |
| **槓桿倍數** | 無 (固定 1x) | 支援 `1x ~ 100x`，透過 `set_leverage()` 動態配置 |
| **強平風控** | 無強平風險 | 動態計算預估強平價格 (`liquidationPrice`) |
| **BingX API** | `/openApi/spot/v1/...` | `/openApi/swap/v2/...` & `/openApi/swap/v3/...` |

---

## 4. 外部通訊與安全規範 (External APIs & Security)

### 1. BingX 官方 OpenAPI 整合規範
- **雙網域容災機制 (Domain Fallback)**：
  - 主要網域：`https://open-api.bingx.com`
  - 備援網域：`https://open-api.bingx.pro`（遭遇連線失敗或超時自動平滑切換）。
- **認證簽名演算法**：
  - 注入毫秒級時間戳 (`timestamp`)。
  - 所有 Query 參數依 ASCII 字典升冪排序：`qs = "&".join(f"{k}={v}" for k in sorted(params.keys()))`。
  - 透過 `API Secret` 計算 HMAC-SHA256 16 進位簽章：`&signature={hex}`。
  - 必備自訂標頭：`X-SOURCE-KEY: BX-AI-SKILL` 與 `X-BX-APIKEY`。

### 2. 環境變數配置規程
根目錄 `.env` 檔案格式（詳見 [`.env.example`](file:///C:/code/AIDev/QuantitativeTrading/.env.example)）：
```env
# BingX 官方憑證
BINGX_API_KEY=your_key_here
BINGX_API_SECRET=your_secret_here

# 派網憑證 (選填)
PIONEX_API_KEY=your_pionex_key_here
PIONEX_API_SECRET=your_pionex_secret_here

# TypeSafe AI 憑證 (選填，無金鑰自動啟用本地 Mock 決策)
TYPESAFE_API_KEY=your_typesafe_key_here
```

> [!CAUTION]
> **絕對禁止**在任何 Commit、測試腳本或文檔中 Hardcode 真實金鑰！`.gitignore` 已嚴格設置排除規則。

---

## 5. BDD 規格驅動測試矩陣 (BDD Test Matrix)

所有核心功能皆包含可執行的 BDD 規格：

| 規格檔案 | 測試實作檔案 | 驗證範疇 |
| :--- | :--- | :--- |
| `tests/bdd/dashboard_behavior.feature` | `test_dashboard_scenarios.py` | 視覺化控制台載入、交易對切換、回測圖表渲染 |
| `tests/bdd/market_type_spot_swap.feature` | `test_market_type_scenarios.py` | 現貨全額扣款、合約槓桿保證金、做多/做空與強平估算 |
| `tests/bdd/bingx_integration.feature` | `test_bingx_scenarios.py` | BingX HMAC 簽名升冪排序、專屬 Header、演練下單 |
| `tests/bdd/pionex_integration.feature` | `test_pionex_scenarios.py` | 派網 Ticker 抓取、符號互轉、模擬撮合 |
| `tests/bdd/typesafe_decision.feature` | `test_typesafe_scenarios.py` | Jev 短線決策模型、強型別合約、Mock Fallback |

執行全套測試指令：
```bash
just test
```
**當前基準**：全套 28 項單元與 BDD 測試 **100% PASS**。

---

## 6. 協作與開發常用指令 (Developer Cheat Sheet)

```bash
# 1. 虛擬環境建立與同步
just sync

# 2. 執行全套自動化測試
just test

# 3. 執行 BingX 現貨/合約連線與認證診斷
just bingx

# 4. 啟動 Streamlit 視覺化金融儀表板
just gui

# 5. 啟動終端互動選單 (純數字按鍵操作)
just menu

# 6. 執行年度滾動複利回測 (例如 2025 年，本金 100U)
just rolling --year 2025 --capital 100
```

---

## 7. 學術免責聲明 (Academic Disclaimer)

本專案由開源社群維護，旨在進行**演算法驗證、機器學習時序研究與量化系統架構教學**。使用者於真實金融市場進行之任何操作決策與盈虧風險，概由使用者自行承擔。
