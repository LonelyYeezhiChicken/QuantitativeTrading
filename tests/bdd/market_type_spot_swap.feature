# Feature: 現貨 (SPOT) 與 永續合約 (SWAP) 交易分離架構 (BDD Feature Specification)

Feature: 交易系統現貨 (Spot) 與合約 (Swap / Perpetual Futures) 分離機制
  作為一名量化交易開發者
  我想在交易網關與客戶端中明確區分現貨交易與合約交易
  以便於策略能夠精確執行現貨買賣、合約多空開平倉、設定槓桿倍數與保證金計算

  Background:
    Given 交易網關支援 MarketType 枚舉 (包含 "SPOT" 與 "SWAP")
    And 支援標準交易對符號互轉與演練防護機制

  Scenario: 現貨 (SPOT) 交易模式執行與資產變更
    Given 網關配置為現貨市場 "SPOT" 演練模式
    And 初始模擬錢包 USDT 餘額為 10000.0，BTC 持幣為 0.0
    When 策略送出市價買入現貨 "BTC/USDT" 數量 0.002 顆
    Then 網關應產生成交回執且 market_type 為 "SPOT"
    And 模擬現貨持幣 BTC 應增加 0.002 顆
    And 現貨 USDT 可用餘額應依成交價全額扣減 (無槓桿保證金)

  Scenario: 永續合約 (SWAP) 做多與槓桿保證金扣除
    Given 網關配置為合約市場 "SWAP" 演練模式
    And 設定標的 "BTC/USDT" 之合約槓桿倍數為 10 倍
    When 策略送出開多單買入 "BTC/USDT" 數量 0.01 顆，價格 50000.0
    Then 網關應產生成交回執且 market_type 為 "SWAP" 且 position_side 為 "LONG"
    And 系統扣除的起始保證金應為名義價值除以槓桿 (約 50.0 USDT)
    And 查詢合約倉位時應顯示持有多單 0.01 顆且槓桿為 10 倍

  Scenario: 永續合約 (SWAP) 做空 (SHORT) 與強平價估算
    Given 網關配置為合約市場 "SWAP" 演練模式
    And 設定標的 "BTC/USDT" 之合約槓桿倍數為 20 倍
    When 策略送出開空單賣出 "BTC/USDT" 數量 0.02 顆，價格 60000.0
    Then 網關應產生成交回執且 market_type 為 "SWAP" 且 position_side 為 "SHORT"
    And 系統應記錄該空頭倉位並計算出高於開倉價之預估強平價格 (Liquidation Price)
