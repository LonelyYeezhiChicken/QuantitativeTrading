# Feature: BingX (盈幣) 交易所 OpenAPI 經紀商串接與安全網關 (BDD Feature Specification)

Feature: BingX OpenAPI 獨立網關模組 (BingX Broker Gateway)
  作為一名量化交易開發者
  我想將交易系統對接 BingX 官方 OpenAPI (支援官方 AI Skill 規範)
  以便於未來能在 BingX 上執行現貨/合約自動化量化交易，並具備雙網域容災與 Dry-Run 演練

  Background:
    Given BingX 網關客戶端已完成初始化
    And 支援標準交易對符號互轉 ("BTC/USDT" 與 "BTC-USDT")

  Scenario: BingX 官方 HMAC-SHA256 簽名與專屬 Header 生成
    Given 測試用的 API Key 為 "test_bingx_key"
    And 測試用的 API Secret 為 "test_bingx_secret"
    When 傳入參數包含符號 "BTC-USDT" 與毫秒時間戳
    Then 系統應產生按字母升冪排列之 query string 並進行 HMAC-SHA256 計算
    And 請求標頭應包含 "X-BX-APIKEY" 與 "X-SOURCE-KEY: BX-AI-SKILL"
    And 若為 POST 請求應採用 "application/x-www-form-urlencoded" 格式傳遞簽名酬載

  Scenario: BingX 公開市場即時行情與 K 線查詢 (Public Market Data)
    Given 尚未配置私有 API 憑證
    When 向 BingX 公開行情端點請求 "BTC-USDT" 之即時最新價格 (Ticker)
    Then 系統應順暢返回包含成交價、買賣盤口與時間戳
    And 回應狀態代碼應為 0 (成功)

  Scenario: BingX 安全演練模式下的委託模擬 (Safe Dry-Run Order Placement)
    Given BingX 網關已啟用 dry_run 演練模式
    When 策略呼叫市價買入 "BTC/USDT" 數量 0.002 顆
    Then 網關應在本地產生以 "BINGX_DRY_RUN_" 開頭之模擬訂單編號
    And 系統絕不會向 BingX 伺服器發送真實扣款下單請求
    And 應返回完整的訂單回執資料物件
