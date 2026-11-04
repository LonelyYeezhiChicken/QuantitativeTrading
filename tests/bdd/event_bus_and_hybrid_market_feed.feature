# language: zh-TW
功能: 跨交易所統一事件匯流排與混合資料源適配器 (Multi-Exchange MarketEventBus & Hybrid Feed Adapter)
  為了讓前端量化決策與三階段出場風控完全由即時事件驅動 (Event-Driven)
  並且能無縫相容具備 WebSocket 的交易所 (如 BingX) 與僅支援 REST 輪詢的交易所 (如 Pionex、PaperBroker)
  身為量化系統架構師
  我必須提供統一的 MarketEventBus、HybridWebSocketFeedAdapter 與 PollingMarketFeedAdapter
  並結合記憶體 K 線滾動快取實現零額外 API 消耗之毫秒級指標運算與出場保護

  場景: 支援 WebSocket 之交易所透過推播事件即時觸發毫秒級移動停利與硬停損 (零輪詢延遲)
    假設 10 倍槓桿合約持有一筆開倉價為 76000、最高浮盈曾達 +25.0% 的 "LONG" 倉位
    而且 自動操盤引擎已訂閱 MarketEventBus 且綁定 BingX 混合 WebSocket 資料源
    當 BingX WebSocket 推進一筆最新成交價為 77400 的即時訊息 (高點回撤超過 5.0% 移動停利門檻)
    那麼 MarketEventBus 應立即發布來源標記為 "WEBSOCKET" 的 TickerUpdateEvent
    而且 自動操盤引擎應在不依賴定時輪詢的情況下立即響應事件完成市價移動停利平倉與權威日誌結算

  場景: 不支援 WebSocket 之交易所自動透過 PollingMarketFeedAdapter 發送標準事件驅動前端
    假設 交易系統連接一個不支援原生 WebSocket 的經紀商網關 (如 PaperBroker 或 PionexGateway)
    當 呼叫網關的 create_market_feed 工廠方法綁定 MarketEventBus 並執行單次輪詢擷取
    那麼 網關應自動配置 PollingMarketFeedAdapter (supports_websocket 為 False)
    而且 EventBus 訂閱者應收到格式完全一致且來源標記為 "POLLING" 的標準 TickerUpdateEvent

  場景: WebSocket 斷線或推播靜默時自動無縫切換至備援輪詢並在連線恢復後切回推播 (Fallback Resilience)
    假設 BingX 混合資料源適配器處於運行狀態且 WebSocket 突然發生斷線或推播靜默超時
    當 適配器健康檢查觸發備援機制時
    那麼 系統應自動調用底層 REST fetch_ticker 並向 EventBus 發布來源為 "POLLING_FALLBACK" 的 TickerUpdateEvent 以確保風控不中斷
    而且 當 WebSocket 重新恢復推播最新價格時應立即切回 "WEBSOCKET" 高速推播模式

  場景: 記憶體 K 線滾動快取結合即時 Tick 合成實現零額外 REST 請求之結構化指標計算
    假設 InMemoryKlineRollingCache 已完成初始 100 根 1 小時 K 線之背景載入 (僅消耗 1 次 REST 請求)
    當 WebSocket 連續高速推入 20 筆不同價格的 TickerUpdateEvent 時
    那麼 快取應在記憶體中即時合成更新當根 K 線之收盤價、最高價與最低價並重算 EMA21、RSI 與乖離率
    而且 在快取有效期間內對底層交易所 REST K 線端點的額外呼叫次數必須為 0
