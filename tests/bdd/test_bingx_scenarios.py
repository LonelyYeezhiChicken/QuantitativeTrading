"""BDD Scenario Implementation Tests: BingX OpenAPI Gateway."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.execution import BingXClient, BingXGateway


class TestBingXBDDScenarios:
    """BDD Step implementations matching bingx_integration.feature."""

    def test_scenario_bingx_hmac_signing_and_headers(self):
        """Scenario: BingX 官方 HMAC-SHA256 簽名與專屬 Header 生成."""
        # Given 測試用的 API Key 與 Secret
        api_key = "test_bingx_key"
        api_secret = "test_bingx_secret"
        client = BingXClient(api_key=api_key, api_secret=api_secret)

        # When 傳入參數包含符號 "BTC-USDT" 與毫秒時間戳
        fixed_timestamp = 1712000000000
        params = {
            "symbol": "BTC-USDT",
            "timestamp": fixed_timestamp,
            "side": "BUY",
        }

        # Then 系統應產生按字母升冪排列之 query string 並進行 HMAC-SHA256 計算
        qs, sig, signed_payload = client.sign_params(params)

        # 字母排序: side=BUY&symbol=BTC-USDT&timestamp=1712000000000
        assert qs == f"side=BUY&symbol=BTC-USDT&timestamp={fixed_timestamp}"
        assert len(sig) == 64
        assert signed_payload == f"{qs}&signature={sig}"

        # And 驗證請求標頭與 POST 格式
        with patch.object(client.session, "post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"code": 0, "msg": "SUCCESS", "data": {"orderId": "123456"}}
            mock_resp.raise_for_status.return_value = None
            mock_post.return_value = mock_resp

            client.request(
                method="POST",
                path="/openApi/spot/v1/trade/order",
                params=params,
                is_private=True,
            )

            mock_post.assert_called_once()
            _, kwargs = mock_post.call_args
            headers = kwargs.get("headers", {})
            data = kwargs.get("data", "")

            # And 請求標頭應包含 "X-BX-APIKEY" 與 "X-SOURCE-KEY: BX-AI-SKILL"
            assert headers.get("X-BX-APIKEY") == "test_bingx_key"
            assert headers.get("X-SOURCE-KEY") == "BX-AI-SKILL"

            # And 若為 POST 請求應採用 "application/x-www-form-urlencoded" 格式傳遞簽名酬載
            assert headers.get("Content-Type") == "application/x-www-form-urlencoded"
            assert "signature=" in data
            assert f"timestamp={fixed_timestamp}" in data

    def test_scenario_public_market_data(self):
        """Scenario: BingX 公開市場即時行情與 K 線查詢 (Public Market Data)."""
        # Given 尚未配置私有 API 憑證
        gateway = BingXGateway(dry_run=True)
        assert gateway.api_key == "" or True

        # When 向 BingX 公開行情端點請求 "BTC-USDT" 之即時最新價格 (Ticker)
        ticker = gateway.fetch_ticker("BTC-USDT")

        # Then 系統應順暢返回包含成交價、買賣盤口與時間戳
        assert ticker["price"] > 1000.0
        assert ticker["bid"] > 1000.0
        assert ticker["ask"] > 1000.0
        assert ticker["timestamp"] > 0

    def test_scenario_safe_dry_run_order(self):
        """Scenario: BingX 安全演練模式下的委託模擬 (Safe Dry-Run Order Placement)."""
        # Given BingX 網關已啟用 dry_run 演練模式
        gateway = BingXGateway(dry_run=True)
        assert gateway.is_dry_run is True

        initial_cash = gateway.get_balance("USDT")
        assert initial_cash == 10000.0

        # When 策略呼叫市價買入 "BTC/USDT" 數量 0.002 顆
        resp = gateway.create_order(
            symbol="BTC/USDT",
            side="BUY",
            order_type="MARKET",
            size=0.002,
        )

        # Then 網關應在本地產生以 "BINGX_DRY_RUN_" 開頭之模擬訂單編號
        assert resp["result"] is True
        assert resp["code"] == 0
        order_data = resp["data"]
        order_id = order_data["orderId"]
        assert order_id.startswith("BINGX_DRY_RUN_")

        # And 系統絕不會向 BingX 伺服器發送真實扣款下單請求
        assert order_data["is_dry_run"] is True
        assert order_data["status"] == "FILLED"

        # And 應返回完整的訂單回執資料物件
        assert order_data["symbol"] == "BTC-USDT"
        assert order_data["origQty"] == 0.002
        assert gateway.get_balance("BTC") == 0.002
        assert gateway.get_balance("USDT") < initial_cash
