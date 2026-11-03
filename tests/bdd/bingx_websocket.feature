# Feature: BingX 官方 WebSocket 毫秒級即時行情串流與雙軌混合架構 (BDD Feature Specification)

Feature: BingX WebSocket 即時行情串流與雙軌混合架構
  為了克服 60 秒 REST 輪詢帶來的延遲與頻率限制
  身為量化交易系統
  我需要透過 WebSocket 長連線獲取毫秒級即時報價，並維持 REST 安全執行與容錯降級

  Scenario: WebSocket GZIP 二進位解壓縮與即時報價串流
    Given BingX WebSocket 客戶端配置好訂閱幣種 "BTC-USDT" 與 "XAUT-USDT"
    When 接收到 GZIP 壓縮的 24h Ticker 與 LastPrice 二進位封包
    Then 系統應自動完成 GZIP 解壓縮並解析最新市價與點差
    And 應即時更新至記憶體快取以供網關零延遲讀取

  Scenario: WebSocket 應用層 Ping/Pong 心跳應答與連線保活
    Given WebSocket 連線處於活動狀態
    When 接收到 BingX 官方送出的 "Ping" 心跳文本
    Then 客戶端應在毫秒內自動回覆 "Pong" 封包以維持長連線
    And 心跳時間戳記應獲得即時更新

  Scenario: 網關優先讀取 WebSocket 快取並具備 REST 降級備援
    Given 網關已啟用雙軌混合模式 (Hybrid Architecture)
    When 查詢 "BTC/USDT" 或 "XAUT/USDT" 即時行情且快取存在
    Then 應優先返回標記為 "WEBSOCKET" 的零延遲報價
    But 當 WebSocket 快取未命中或連線不可用時應自動降級回退至 REST API
