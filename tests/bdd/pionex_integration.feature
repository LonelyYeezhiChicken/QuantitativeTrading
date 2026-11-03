# Feature: 派網 (Pionex) OpenAPI 經紀商串接與安全網關 (BDD Feature Specification)

Feature: 派網 OpenAPI 獨立網關模組 (Pionex Broker Gateway)
  作為一名量化交易開發者
  我想將交易系統對接派網 (Pionex) 官方 OpenAPI
  以便於未來能在派網上執行實盤或模擬量化下單，同時具備 Dry-Run 安全演練機制

  Background:
    Given 派網網關客戶端已完成初始化
    And 支援標準交易對符號互轉 ("BTC/USDT" 與 "BTC_USDT")

  Scenario: 派網 HMAC-SHA256 數位簽章生成 (HMAC Request Signing)
    Given 測試用的 API Key 為 "test_api_key"
    And 測試用的 API Secret 為 "test_api_secret"
    And 請求端點為 "/api/v1/trade/allOrders" 且方法為 "GET"
    When 傳入參數包含符號 "BTC_USDT" 與時間戳
    Then 系統應依 ASCII 升冪排序參數並產生正確格式的 PATH_URL
    And 應透過 HMAC-SHA256 生成長度為 64 的十六進位簽名
    And 請求標頭應包含 "PIONEX-KEY" 與 "PIONEX-SIGNATURE"

  Scenario: 公開市場即時行情與 K 線查詢 (Public Market Data Retrieval)
    Given 尚未配置私有 API 憑證
    When 向派網公開行情端點請求 "BTC_USDT" 的即時報價 (Ticker)
    Then 系統應順暢返回包含當前最新成交價、買賣報價與時間戳
    And 回應狀態應為成功

  Scenario: 安全演練模式下的委託模擬 (Safe Dry-Run Order Placement)
    Given 派網網關已啟用 dry_run 演練模式
    When 策略呼叫市價買入 "BTC/USDT" 數量 0.001 顆
    Then 網關應直接在本地完成模擬撮合確認
    And 系統絕不會向派網交易所伺服器送出真實扣款委託
    And 應返回包含模擬訂單編號與成交價格的完整訂單物件
