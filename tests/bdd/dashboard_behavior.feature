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
