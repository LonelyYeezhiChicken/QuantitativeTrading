# Feature: 交易策略五年 BTC 回測與收斂淘汰矩陣 (5-Year Strategy Convergence Matrix)

Feature: 交易策略五年 BTC 回測與收斂淘汰矩陣 (Strategy Convergence Matrix)
  作為一名量化交易架構師與操盤手
  我想對所有候選策略進行 2021~2025 五年完整週期 (牛市、熊市、震盪、突破) 的回測推演
  以便於依據夏普比率、最大回撤、獲利因子與熊市防禦力，淘汰劣質策略並收斂出實盤主力

  Background:
    Given 基準回測標的為 "BTC/USDT"
    And 初始配置本金為 10000.0 USDT
    And 考慮真實交易摩擦手續費 0.05% 與滑價 0.02%

  Scenario: 五年歷史數據特徵快取與多策略矩陣推演 (5-Year Matrix Multi-Strategy Backtesting)
    Given 系統已載入 2021 至 2025 年完整 5 年 BTC 歷史行情數據
    When 收斂分析器批量執行包含趨勢、均值回歸、多因子AI與價格行為之多個候選模型
    Then 每個策略皆應輸出完整的五年累積報酬率、年化CAGR、夏普比率與最大回撤
    And 系統應輸出歷年市場行情適應性矩陣且包含 2022 熊市崩盤期表現

  Scenario: 斐波那契 SNR 4h 黃金口袋短單模型驗證 (Fibonacci SNR Golden Pocket Model)
    Given 交易員配置 Fibonacci SNR 模型並設定回看週期與黃金口袋比例
    When 策略於時序特徵矩陣中識別關鍵高低點支撐阻力與 0.50 至 0.65 回撤區間
    Then 策略應在趨勢方向一致且回踩黃金口袋時發出進場訊號
    And 策略應於觸及前高阻力或跌破 0.786 深位止損時正確平倉離場
    And 五年回測最大回撤應受控在 20% 以內且維持正夏普比率
    # 已知未達標 (xfail strict)：修正回測引擎「停損 K 線虧損未入帳」偏差後，
    # 實測五年 BTC 為 報酬 -22.98% / MDD 39.25% / Sharpe 0.02 (舊引擎誤報 +133.95% / 14.86% / 1.89)。

  Scenario: 策略收斂規則精準識別保留與淘汰策略 (Strict Quantitative Pruning Classification)
    Given 五年策略回測指標矩陣已計算完成
    When 系統應用客觀量化收斂評定法則
    Then 5年收益優異且回撤受控的合約多空雙向與多因子AI應標註為 KEEP
    And 具備長期正期望值但需微調的現貨回踩與斐波那契SNR應標註為 OPTIMIZE
    And 五年累積虧損且回撤過深的傳統無濾網 RSI 應精準標註為 DISCARD
