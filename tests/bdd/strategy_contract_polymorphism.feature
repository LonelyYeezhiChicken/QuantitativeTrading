# language: zh-TW
功能: 策略模型統一抽象契約與動態依賴注入（Strategy Contract Polymorphism & Dependency Injection）
  為了保證任何新研發的 AI/機器學習或價格行為策略能即插即用且與交易執行引擎完全解耦
  身為量化模型研發人員
  我需要確保所有策略模型均嚴格實作 BaseTradingModel 契約，並可無縫注入自動操盤中樞

  場景: 多元策略模型滿足 BaseTradingModel 統一契約規範
    假設 系統載入多元策略模型包含雙均線、LightGBM 代理人、多體制合約模型與斐波那契黃金口袋模型
    當 對標準化行情數據特徵集調用 fit 與 predict 方法
    那麼 所有策略模型均能回傳長度完全匹配之 numpy array 預測信號
    而且 所有信號強度數值皆嚴格收斂在 [-1.0, 1.0] 區間之內

  場景: 任意 BaseTradingModel 策略模型無縫注入自動操盤中樞
    假設 開發者自訂了一個繼承自 BaseTradingModel 之斐波那契黃金口袋策略模型
    當 初始化 UnifiedAutopilotEngine 時透過 strategy 參數進行依賴注入
    那麼 操盤中樞之內部策略應成功綁定為注入之斐波那契模型
    而且 操盤中樞執行 step 評估時直接調度該注入策略產出決策信號
