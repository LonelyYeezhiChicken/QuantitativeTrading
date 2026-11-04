"""BDD Scenario Implementation Tests: Broker Gateway Polymorphism & Paper Simulation."""

import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.execution.base import BaseBrokerGateway, MarketType
from packages.execution.paper_broker import PaperBroker
from packages.execution.bingx_gateway import BingXGateway


class TestBrokerGatewayPolymorphismBDDScenarios:
    """BDD Step implementations matching broker_gateway_polymorphism.feature."""

    def test_scenario_base_broker_gateway_paper_execution(self, tmp_path):
        """Scenario: 透過 BaseBrokerGateway 抽象契約執行模擬現貨撮合"""
        # Given 操盤系統宣告 BaseBrokerGateway 介面並指派為 PaperBroker 實體
        state_file = tmp_path / "paper_poly_test.json"
        gw: BaseBrokerGateway = PaperBroker(
            initial_balance=1000.0,
            fee_rate=0.0005,
            slippage=0.0002,
            state_file=str(state_file),
        )
        assert isinstance(gw, BaseBrokerGateway)
        assert gw.get_balance("USDT") == 1000.0

        # When 透過標準統一之 create_order 介面發送現貨 BUY 市價單
        gw.set_mock_price("BTC/USDT", 50000.0)
        res = gw.create_order(
            symbol="BTC/USDT",
            side="BUY",
            order_type="MARKET",
            size=0.01,  # 0.01 BTC = $500 notional
            market_type=MarketType.SPOT.value,
        )

        # Then 訂單回應應包含標準 orderId 且 status 為 "FILLED"
        assert res.get("result") is True
        order_data = res.get("data", {})
        assert "orderId" in order_data
        assert order_data.get("status") == "FILLED"

        # And 可用現金應扣除名目保證金與 0.05% 手續費
        # 0.01 BTC * (50000 * 1.0002) = 500.10, fee = 500.10 * 0.0005 = 0.25005
        expected_cash = 1000.0 - 500.10 - 0.25005
        assert gw.get_balance("USDT") == pytest.approx(expected_cash, abs=0.01)

        # And 持倉部位應正確計入數量與滑價後之成交均價
        positions = gw.get_positions("BTC/USDT")
        assert len(positions) == 1
        assert positions[0]["positionAmt"] == pytest.approx(0.01)
        assert positions[0]["entryPrice"] == pytest.approx(50010.0)

    def test_scenario_liskov_substitution_paper_and_bingx(self, tmp_path):
        """Scenario: 經紀商網關遵循里氏替換原則無縫切換"""
        state_file = tmp_path / "paper_lsp.json"

        # Given 操盤中樞以依賴注入方式分別掛載 PaperBroker 與 BingXGateway
        gateways: list[BaseBrokerGateway] = [
            PaperBroker(initial_balance=5000.0, state_file=str(state_file)),
            BingXGateway(dry_run=True, enable_ws=False),
        ]

        # When 透過完全相同之 create_order 方法簽名提交下單請求
        for broker in gateways:
            # Polymorphic execution
            assert isinstance(broker, BaseBrokerGateway)
            assert broker.is_dry_run is True

            res = broker.create_order(
                symbol="BTC/USDT",
                side="BUY",
                order_type="MARKET",
                size=0.001,
                market_type=MarketType.SPOT.value,
            )

            # Then 兩個網關均能正確處理請求並回傳包含 result 與 data 之標準回應
            assert isinstance(res, dict)
            assert "result" in res
            assert res["result"] is True
            assert "data" in res

        # And 證明交易執行業務邏輯與具體交易所實作完全解耦

    def test_scenario_insufficient_funds_rejection(self, tmp_path):
        """Scenario: 模擬經紀商於資金不足時安全攔截下單"""
        state_file = tmp_path / "paper_broke.json"
        gw: BaseBrokerGateway = PaperBroker(initial_balance=10.0, state_file=str(state_file))

        # Given 模擬經紀商可用現金僅剩 10.0 USDT
        assert gw.get_balance("USDT") == 10.0

        # When 嘗試透過 create_order 下達規模為 500.0 USDT 之現貨買單
        gw.set_mock_price("BTC/USDT", 50000.0)
        res = gw.create_order(
            symbol="BTC/USDT",
            side="BUY",
            order_type="MARKET",
            size=0.01,  # 0.01 * 50000 = 500 USDT > 10.0 USDT
            market_type=MarketType.SPOT.value,
        )

        # Then 經紀商應安全拒絕該筆委託並回傳 result 為 False
        assert res.get("result") is False
        assert "Insufficient funds" in res.get("msg", "")

        # And 現金餘額與持倉部位保持完全不變
        assert gw.get_balance("USDT") == 10.0
        assert len(gw.get_positions()) == 0
