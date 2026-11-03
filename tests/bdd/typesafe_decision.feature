# Feature: TypeSafe AI (Jev) 短線交易決策模型 (BDD Feature Specification)

Feature: TypeSafe AI 結構化短線決策 Agent (TypeSafe Decision Agent)
  作為一名量化交易開發者
  我想將 TypeSafe AI (Jev) 的 System One 決策引擎整合至交易系統
  以便於利用 noul 二元機率、choice 分類與 score 評估進行高精準度的短線交易決策

  Background:
    Given 系統已載入標準特徵工程管線 (FeaturePipeline)
    And TypeSafe AI Agent 已初始化 (預設開啟 Mock / Fallback 保護模式)

  Scenario: 市場狀態字串序列化 (Market State Serialization)
    Given 一組即時市場特徵包含收益率、RSI、EMA 偏離度與成交量
    When Agent 執行 format_state 進行狀態序列化
    Then 產出的 state 字串應精確包含量化指標與趨勢資訊
    And 格式應符合 TypeSafe AI 的 Jev 決策輸入規範

  Scenario: 強型別提問合約生成 (Typed Question Contract Definition)
    When Agent 構建決策提問規格 (build_questions)
    Then 規格中應包含 "action" 的 choice 分類 (BUY, SELL, HOLD)
    And 應包含 "is_high_conviction" 的 noul 伯努利二元機率合約
    And 應包含 "volatility_risk" 的 1 到 5 分 score 階梯評級合約

  Scenario: TypeSafe AI 決策驅動之回測相容性 (Modular Backtest Execution)
    Given 存在歷史 OHLCV 測試數據
    When 將 TypeSafeAIAgent 傳入 RollingBacktestEvaluator 進行回測
    Then Agent 應正常輸出符合 BaseTradingModel 規範的預測向量
    And 回測評估器應成功計算出策略總收益率、夏普比率與月度資產成長表
