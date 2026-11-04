# language: zh-TW
功能: BingX 官方 VST 交易所模擬交易與真實訂單同步 (BingX VST Official Simulation)

  作為一位量化交易員
  我希望系統能將模擬交易直接對接至 BingX 官方 VST 模擬伺服器 (open-api-vst.bingx.com)
  以便在切換真金實盤前，能在手機 BingX 官方 App 的 VST 模擬倉中即時檢視真實的委託、持倉與原生硬停損單

  場景: 啟用 VST 模式時網關自動切換至官方模擬伺服器並獲取 VST 虛擬資產
    假設 交易員在系統中啟用 VST 官方模擬盤模式
    當 經紀商網關初始化 BingXGateway
    那麼 網關的 is_vst 屬性應為 True 且 is_dry_run 應為 False
    而且 網關對外的 API 基礎網址應指向 "open-api-vst.bingx.com"
    而且 查詢合約保證金時應回傳大於 0 的 VST 虛擬資產餘額

  場景: VST 模式下設置合約槓桿與原子性硬停損下單
    假設 標的為 "BTC-USDT" 且槓桿設定為 10 倍
    當 網關呼叫 set_leverage 配置槓桿
    那麼 請求應採用 side="ALL" 雙向模式並成功回傳
    當 網關發送 0.001 BTC 買單並附加原子性硬停損價格 75000
    那麼 交易所伺服器應返回已撮合成交之 orderId 且包含 STOP_MARKET 停損參數

  場景: VST 模式下即時持倉查詢與平倉生命週期
    假設 交易所已建立 0.001 BTC 之 VST 多頭持倉
    當 系統調用 get_positions 查詢持倉
    那麼 應成功返回包含 BTC-USDT 與 LONG 方向之真實持倉結構
    當 系統發送反向平倉賣單並撤銷剩餘條件單
    那麼 該持倉應從交易所完全平倉且委託單列表歸零
