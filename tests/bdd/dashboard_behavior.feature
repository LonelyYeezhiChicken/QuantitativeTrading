# Feature: AI 量化交易免指令互動式控制台 (BDD Feature Specification)

Feature: 免指令量化交易控制台 (No-Code Quant Trading Dashboard)
  作為一名量化交易使用者
  我想透過可視化介面與一鍵按鈕完成數據下載、AI 訓練回測與模擬盤操作
  以便於免除手動輸入繁瑣終端指令與記憶參數的負擔

  Background:
    Given 交易系統環境已初始化完成
    And 初始紙上帳戶本金為 10000.0 USDT

  Scenario: 一鍵下載並檢視市場行情數據 (One-click Market Data Download)
    Given 使用者選擇交易對 "BTC/USDT" 且時間週期為 "1h"
    When 使用者觸發數據下載管線
    Then 系統應在本地儲存有效的 OHLCV 歷史數據
    And 數據總筆數應大於 50 筆
    And 應能產生包含開高低收與成交量的圖表資料

  Scenario: 一鍵執行 LightGBM 模型訓練與回測 (One-click Model Training & Backtesting)
    Given 本地已存在 "BTC/USDT" 的歷史行情數據
    And 設定交易信心閥值為 0.002
    When 使用者點擊開始訓練與回測
    Then 系統應使用時序淨化交叉驗證 (Purged CV) 完成模型訓練
    And 系統應輸出核心績效指標 (Sharpe Ratio, Max Drawdown, 勝率)
    And 系統應產生策略權益曲線 (Equity Curve) 與特徵重要性分析

  Scenario: 模擬盤即時交易與帳戶狀態更新 (Real-time Paper Trading Step Simulation)
    Given 模擬盤帳戶可用資金為 10000.0 USDT
    And 當前市場價格為 50000.0 USDT
    When 策略發出買入信號並投入 2000.0 USDT
    Then 模擬盤應自動扣除 0.05% 手續費與滑價並增加持倉部位
    And 帳戶剩餘現金應正確扣減
    And 交易紀錄流水應新增一筆 BUY 訂單紀錄

  Scenario: 手動模擬買賣與雙通道下單撮合 (Manual Order Execution & Dual Channel Safe Fallback)
    Given 交易員操作手動下單面板
    When 交易員透過本地模擬經紀商執行市價買入 100.0 USDT
    Then 買單回傳物件應具備成交數量與價格且無 KeyError 異常
    When 交易員執行市價全額平倉賣出
    Then 賣單回傳物件應具備平倉數量與實現盈虧且持倉歸零
    When 交易員切換至 BingX OpenAPI 通道發送模擬買單
    Then 網關應返回撮合成交結果與訂單識別碼

  Scenario: 多模型特徵擬合與年度滾動複利評估 (Multi-model Feature Backtesting & Rolling Evaluation)
    Given 具備完整 78+ 技術因子的特徵矩陣
    When 針對特徵數據擬合 Dual EMA 與 RSI 規則策略
    Then 策略應產出連續數值化交易訊號且無前視偏差
    When 回測引擎以自訂手續費費率 0.0006 執行推演
    Then 應回傳包含資產淨值曲線與績效指標字典的元組結構
    When 年度滾倉評估器傳入交易模型與年份
    Then 應回傳標準 RollingEvaluationResult 數據類別且可讀取期末淨值與年度收益率
