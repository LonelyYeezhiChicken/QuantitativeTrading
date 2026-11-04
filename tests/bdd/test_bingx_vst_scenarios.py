"""BDD Step Implementation Tests for BingX VST Official Exchange Simulation."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from packages.execution.base import MarketType
from packages.execution.bingx_client import BingXClient
from packages.execution.bingx_gateway import BingXGateway


class TestBingXVSTBDDScenarios:
    """BDD Step implementations matching bingx_vst_exchange_simulation.feature."""

    def test_scenario_vst_gateway_initialization_and_asset_routing(self):
        """Scenario: 啟用 VST 模式時網關自動切換至官方模擬伺服器並獲取 VST 虛擬資產"""
        # Given 交易員在系統中啟用 VST 官方模擬盤模式
        # When 經紀商網關初始化 BingXGateway
        gw = BingXGateway(
            api_key="mock_key",
            api_secret="mock_secret",
            dry_run=True,
            use_vst=True,
            default_market_type="SWAP",
            enable_ws=False,
        )

        # Then 網關的 is_vst 屬性應為 True 且 is_dry_run 應為 False
        assert gw.is_vst is True
        assert gw.is_dry_run is False

        # And 網關對外的 API 基礎網址應指向 "open-api-vst.bingx.com"
        assert "open-api-vst.bingx.com" in gw.client.base_urls[0]
        assert "open-api-vst.bingx.pro" in gw.client.base_urls[1]

        # And 查詢合約保證金時應回傳大於 0 的 VST 虛擬資產餘額
        mock_balance_resp = {
            "code": 0,
            "msg": "",
            "data": [
                {
                    "asset": "VST",
                    "balance": "167186.93",
                    "availableMargin": "167186.93",
                }
            ],
        }
        with patch.object(gw.client, "get_swap_balance", return_value=mock_balance_resp):
            vst_balance = gw.get_balance(asset="USDT", market_type="SWAP")
            assert vst_balance == pytest.approx(167186.93)

    def test_scenario_vst_leverage_and_atomic_native_stop_order(self):
        """Scenario: VST 模式下設置合約槓桿與原子性硬停損下單"""
        # Given 標的為 "BTC-USDT" 且槓桿設定為 10 倍
        gw = BingXGateway(
            api_key="mock_key",
            api_secret="mock_secret",
            use_vst=True,
            enable_ws=False,
        )

        # When 網關呼叫 set_leverage 配置槓桿
        with patch.object(gw.client, "set_swap_leverage", return_value={"code": 0, "data": {"leverage": 10}}) as mock_set_lev:
            success = gw.set_leverage("BTC/USDT", 10)
            assert success is True
            # Then 請求應採用 side="ALL" 雙向模式並成功回傳
            mock_set_lev.assert_called_once_with(symbol="BTC-USDT", leverage=10, side="ALL")

        # When 網關發送 0.001 BTC 買單並附加原子性硬停損價格 75000
        mock_order_resp = {
            "code": 0,
            "msg": "",
            "data": {
                "order": {
                    "orderId": 2117793454558810112,
                    "symbol": "BTC-USDT",
                    "positionSide": "LONG",
                    "side": "BUY",
                    "type": "MARKET",
                    "quantity": 0.001,
                    "status": "FILLED",
                    "stopLoss": '{"type":"STOP_MARKET","stopPrice":75000.0,"workingType":"MARK_PRICE"}',
                }
            },
        }
        with patch.object(gw.client, "create_swap_order", return_value=mock_order_resp) as mock_order:
            order_res = gw.create_order(
                symbol="BTC/USDT",
                side="BUY",
                order_type="MARKET",
                size=0.001045, # Test 4-decimal precision clipping
                market_type="SWAP",
                position_side="LONG",
                leverage=10,
                stop_loss_price=75000.0,
            )

            # Then 交易所伺服器應返回已撮合成交之 orderId 且包含 STOP_MARKET 停損參數
            assert order_res.get("result") is True
            assert order_res["code"] == 0
            order_data = order_res["data"]["order"]
            assert order_data["orderId"] == 2117793454558810112
            assert "STOP_MARKET" in order_data["stopLoss"]
            mock_order.assert_called_once_with(
                symbol="BTC-USDT",
                side="BUY",
                position_side="LONG",
                order_type="MARKET",
                quantity=0.001,  # Clipped to 4 decimal places
                price=None,
                client_order_id=None,
                stop_loss_price=75000.0,
                take_profit_price=None,
            )

    def test_scenario_vst_position_synchronization_and_close(self):
        """Scenario: VST 模式下即時持倉查詢與平倉生命週期"""
        # Given 交易所已建立 0.001 BTC 之 VST 多頭持倉
        gw = BingXGateway(
            api_key="mock_key",
            api_secret="mock_secret",
            use_vst=True,
            enable_ws=False,
        )

        mock_positions = {
            "code": 0,
            "data": [
                {
                    "positionId": "2117793454596558850",
                    "symbol": "BTC-USDT",
                    "positionAmt": "0.0010",
                    "positionSide": "LONG",
                    "avgPrice": "77000.0",
                    "initialMargin": "7.70",
                    "leverage": 10,
                    "liquidationPrice": 69613.4,
                }
            ],
        }

        # When 系統調用 get_positions 查詢持倉
        with patch.object(gw.client, "get_swap_positions", return_value=mock_positions):
            positions = gw.get_positions("BTC/USDT")
            # Then 應成功返回包含 BTC-USDT 與 LONG 方向之真實持倉結構
            assert len(positions) == 1
            pos = positions[0]
            assert pos["symbol"] == "BTC-USDT"
            assert pos["positionSide"] == "LONG"
            assert float(pos["positionAmt"]) == 0.001

        # When 系統發送反向平倉賣單並撤銷剩餘條件單
        mock_close_resp = {
            "code": 0,
            "data": {
                "order": {
                    "orderId": 2117793487031111680,
                    "symbol": "BTC-USDT",
                    "positionSide": "LONG",
                    "side": "SELL",
                    "status": "FILLED",
                }
            },
        }
        with patch.object(gw.client, "create_swap_order", return_value=mock_close_resp):
            close_res = gw.create_order(
                symbol="BTC/USDT",
                side="SELL",
                order_type="MARKET",
                size=0.001,
                market_type="SWAP",
                position_side="LONG",
            )
            assert close_res.get("result") is True

        with patch.object(gw.client, "cancel_all_swap_orders", return_value={"code": 0, "data": {}}) as mock_cancel:
            cancel_success = gw.cancel_all_orders("BTC/USDT", market_type="SWAP")
            assert cancel_success is True
            mock_cancel.assert_called_once_with(symbol="BTC-USDT")
