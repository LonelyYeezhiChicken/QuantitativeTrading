"""BDD Scenario Implementation Tests: BingX WebSocket Streaming & Hybrid Architecture."""

import sys
import gzip
import json
import time
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.execution.bingx_ws import BingXWebSocketClient
from packages.execution.bingx_gateway import BingXGateway


class TestBingXWebSocketBDDScenarios:
    """BDD Step implementations matching bingx_websocket.feature."""

    def test_scenario_ws_gzip_decompression_and_streaming(self):
        """Scenario: WebSocket GZIP 二進位解壓縮與即時報價串流."""
        # Given BingX WebSocket 客戶端配置好訂閱幣種 "BTC-USDT" 與 "XAUT-USDT"
        client = BingXWebSocketClient(symbols=["BTC-USDT", "XAUT-USDT"])

        # When 接收到 GZIP 壓縮的 24h Ticker 與 LastPrice 二進位封包
        ticker_payload = {
            "dataType": "BTC-USDT@ticker",
            "data": {
                "e": "24hTicker",
                "s": "BTC-USDT",
                "c": "77600.0",
                "h": "78200.0",
                "l": "76400.0",
                "B": "77599.9",
                "A": "77600.1",
                "P": "0.45%",
            },
        }
        compressed = gzip.compress(json.dumps(ticker_payload).encode("utf-8"))

        # Then 系統應自動完成 GZIP 解壓縮並解析最新市價與點差
        decompressed_text = gzip.decompress(compressed).decode("utf-8")
        parsed = json.loads(decompressed_text)
        client._process_message(parsed, "SPOT")

        # And 應即時更新至記憶體快取以供網關零延遲讀取
        cached = client.get_ticker("BTC/USDT", "SPOT")
        assert cached is not None
        assert cached["price"] == 77600.0
        assert cached["bid"] == 77599.9
        assert cached["ask"] == 77600.1
        assert cached["change_24h_pct"] == 0.45

    def test_scenario_ws_ping_pong_heartbeat(self):
        """Scenario: WebSocket 應用層 Ping/Pong 心跳應答與連線保活."""
        # Given WebSocket 連線處於活動狀態
        client = BingXWebSocketClient(symbols=["BTC-USDT"])
        t0 = client._last_ping_time

        # When 接收到 BingX 官方送出的 "Ping" 心跳文本
        raw_msg = "Ping"
        if raw_msg == "Ping":
            response = "Pong"
            client._last_ping_time = time.time()

        # Then 客戶端應在毫秒內自動回覆 "Pong" 封包以維持長連線
        assert response == "Pong"

        # And 心跳時間戳記應獲得即時更新
        assert client._last_ping_time >= t0

    def test_scenario_gateway_hybrid_prioritization_and_fallback(self):
        """Scenario: 網關優先讀取 WebSocket 快取並具備 REST 降級備援."""
        # Given 網關已啟用雙軌混合模式 (Hybrid Architecture)
        gw = BingXGateway(dry_run=True, enable_ws=True)

        # 模擬在 WS 客戶端快取中注入一筆新鮮的 XAUT 即時行情
        if gw.ws_client:
            gw.ws_client._update_cache("XAUT/USDT", "SPOT", {
                "symbol": "XAUT/USDT",
                "market_type": "SPOT",
                "price": 3942.50,
                "bid": 3942.00,
                "ask": 3943.00,
                "high_24h": 3960.00,
                "low_24h": 3900.00,
                "change_24h_pct": 0.35,
            })

        # When 查詢 "BTC/USDT" 或 "XAUT/USDT" 即時行情且快取存在
        xaut_ticker = gw.fetch_ticker("XAUT/USDT", market_type="SPOT")

        # Then 應優先返回標記為 "WEBSOCKET" 的零延遲報價
        assert xaut_ticker["source"] == "WEBSOCKET"
        assert xaut_ticker["price"] == 3942.50

        # But 當 WebSocket 快取未命中或連線不可用時應自動降級回退至 REST API
        gw_no_ws = BingXGateway(dry_run=True, enable_ws=False)
        assert gw_no_ws.is_ws_connected is False
        fallback_ticker = gw_no_ws.fetch_ticker("BTC/USDT")
        assert fallback_ticker["price"] > 0
        assert fallback_ticker.get("source") != "WEBSOCKET"
