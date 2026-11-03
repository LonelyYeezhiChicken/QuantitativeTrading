"""BDD Scenario Implementation Tests: Pionex OpenAPI Gateway."""

import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.execution import PionexClient, PionexGateway

class TestPionexBDDScenarios:
    """BDD Step implementations matching pionex_integration.feature."""

    def test_scenario_pionex_hmac_signing(self):
        """Scenario: 派網 HMAC-SHA256 數位簽章生成"""
        # Given 測試用的 API Key 與 Secret
        api_key = "test_pionex_key_123"
        api_secret = "test_pionex_secret_456"
        client = PionexClient(api_key=api_key, api_secret=api_secret)

        # When 傳入參數包含符號 "BTC_USDT" 與時間戳
        endpoint = "/api/v1/trade/allOrders"
        params = {
            "symbol": "BTC_USDT",
            "limit": 5,
            "timestamp": 1655896754515,
        }

        # Then 系統應依 ASCII 升冪排序參數並產生正確格式的 PATH_URL
        path_url, signature = client.generate_signature("GET", endpoint, params=params)

        # 排序後 limit -> symbol -> timestamp
        assert "limit=5&symbol=BTC_USDT&timestamp=1655896754515" in path_url
        assert path_url.startswith("/api/v1/trade/allOrders?")

        # And 應透過 HMAC-SHA256 生成長度為 64 的十六進位簽名
        assert len(signature) == 64
        assert isinstance(signature, str)
        # Verify hex string characters
        int(signature, 16)

    def test_scenario_public_market_data(self):
        """Scenario: 公開市場即時行情與 K 線查詢"""
        # Given 尚未配置私有 API 憑證
        client = PionexClient()
        gateway = PionexGateway(dry_run=True)

        # When 向派網公開行情端點請求 "BTC_USDT" 的即時報價 (Ticker)
        ticker = gateway.fetch_ticker("BTC/USDT")

        # Then 系統應順暢返回包含當前最新成交價與時間戳
        assert ticker["price"] > 1000.0
        assert ticker["bid"] > 1000.0
        assert ticker["ask"] > 1000.0
        assert ticker["timestamp"] > 0

    def test_scenario_safe_dry_run_order(self):
        """Scenario: 安全演練模式下的委託模擬"""
        # Given 派網網關已啟用 dry_run 演練模式
        gateway = PionexGateway(dry_run=True)
        assert gateway.is_dry_run is True

        # When 策略呼叫市價買入 "BTC/USDT"
        resp = gateway.create_order(
            symbol="BTC/USDT",
            side="BUY",
            order_type="MARKET",
            size=0.005,
        )

        # Then 網關應直接在本地完成模擬撮合確認
        assert resp["result"] is True
        order_data = resp["data"]
        assert order_data["side"] == "BUY"
        assert order_data["pionex_symbol"] == "BTC_USDT"
        assert order_data["size"] == 0.005
        assert order_data["is_dry_run"] is True
        assert order_data["order_id"].startswith("DRY_RUN_")
