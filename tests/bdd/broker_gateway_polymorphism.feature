# language: zh-TW
功能: 經紀商抽象網關多型契約與模擬撮合（Broker Gateway Polymorphism & Paper Simulation）
  為了支援任意交易所（BingX, Pionex, Paper）隨插即用且支援純本地極速無風險撮合
  身為量化交易架構師
  我需要確保所有經紀商網關皆嚴格實現 BaseBrokerGateway 契約，並遵循里氏替換原則 (LSP)

  場景: 透過 BaseBrokerGateway 抽象契約執行模擬現貨撮合
    假設 操盤系統宣告 BaseBrokerGateway 介面並指派為 PaperBroker 實體
    當 透過標準統一之 create_order 介面發送現貨 BUY 市價單
    那麼 訂單回應應包含標準 orderId 且 status 為 "FILLED"
    而且 可用現金應扣除名目保證金與 0.05% 手續費
    而且 持倉部位應正確計入數量與滑價後之成交均價

  場景: 經紀商網關遵循里氏替換原則無縫切換
    假設 操盤中樞以依賴注入方式分別掛載 PaperBroker 與 BingXGateway
    當 透過完全相同之 create_order 方法簽名提交下單請求
    那麼 兩個網關均能正確處理請求並回傳包含 result 與 data 之標準回應
    而且 證明交易執行業務邏輯與具體交易所實作完全解耦

  場景: 模擬經紀商於資金不足時安全攔截下單
    假設 模擬經紀商可用現金僅剩 10.0 USDT
    當 嘗試透過 create_order 下達規模為 500.0 USDT 之現貨買單
    那麼 經紀商應安全拒絕該筆委託並回傳 result 為 False
    而且 現金餘額與持倉部位保持完全不變
