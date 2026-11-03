"""BDD Scenario Implementation Tests: MarketType Distinction (SPOT vs SWAP / Perpetual Futures)."""

import sys
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.execution import BingXGateway, MarketType


class TestMarketTypeBDDScenarios:
    """BDD Step implementations matching market_type_spot_swap.feature."""

    def test_scenario_spot_trading_and_asset_change(self):
        """Scenario: 現貨 (SPOT) 交易模式執行與資產變更."""
        # Given 網關配置為現貨市場 "SPOT" 演練模式
        gateway = BingXGateway(dry_run=True, default_market_type=MarketType.SPOT.value)
        assert gateway.default_market_type == "SPOT"

        # And 初始模擬錢包 USDT 餘額為 10000.0，BTC 持幣為 0.0
        assert gateway.get_balance("USDT", market_type=MarketType.SPOT.value) == 10000.0
        assert gateway.get_balance("BTC", market_type=MarketType.SPOT.value) == 0.0

        # When 策略送出市價買入現貨 "BTC/USDT" 數量 0.002 顆
        resp = gateway.create_order(
            symbol="BTC/USDT",
            side="BUY",
            order_type="MARKET",
            size=0.002,
            market_type=MarketType.SPOT.value,
        )

        # Then 網關應產生成交回執且 market_type 為 "SPOT"
        assert resp["result"] is True
        data = resp["data"]
        assert data["market_type"] == "SPOT"
        assert data["orderId"].startswith("BINGX_DRY_RUN_")

        # And 模擬現貨持幣 BTC 應增加 0.002 顆
        assert gateway.get_balance("BTC", market_type=MarketType.SPOT.value) == 0.002

        # And 現貨 USDT 可用餘額應依成交價全額扣減 (無槓桿保證金)
        expected_remaining = 10000.0 - data["cummulativeQuoteQty"]
        assert abs(gateway.get_balance("USDT", market_type=MarketType.SPOT.value) - expected_remaining) < 1e-4

    def test_scenario_swap_long_leverage_and_margin(self):
        """Scenario: 永續合約 (SWAP) 做多與槓桿保證金扣除."""
        # Given 網關配置為合約市場 "SWAP" 演練模式
        gateway = BingXGateway(dry_run=True, default_market_type=MarketType.SWAP.value)
        assert gateway.default_market_type == "SWAP"

        initial_swap_margin = gateway.get_balance("USDT", market_type=MarketType.SWAP.value)
        assert initial_swap_margin == 10000.0

        # And 設定標的 "BTC/USDT" 之合約槓桿倍數為 10 倍
        gateway.set_leverage("BTC/USDT", 10)

        # When 策略送出開多單買入 "BTC/USDT" 數量 0.01 顆，價格 50000.0
        resp = gateway.create_order(
            symbol="BTC/USDT",
            side="BUY",
            order_type="LIMIT",
            size=0.01,
            price=50000.0,
            market_type=MarketType.SWAP.value,
            position_side="LONG",
            leverage=10,
        )

        # Then 網關應產生成交回執且 market_type 為 "SWAP" 且 position_side 為 "LONG"
        assert resp["result"] is True
        order = resp["data"]
        assert order["market_type"] == "SWAP"
        assert order["positionSide"] == "LONG"
        assert order["orderId"].startswith("BINGX_SWAP_DRY_RUN_")

        # And 系統扣除的起始保證金應為名義價值除以槓桿 (0.01 * 50000 / 10 = 50.0 USDT)
        assert order["marginRequired"] == 50.0
        assert gateway.get_balance("USDT", market_type=MarketType.SWAP.value) == 9950.0

        # And 查詢合約倉位時應顯示持有多單 0.01 顆且槓桿為 10 倍
        positions = gateway.get_positions("BTC/USDT")
        assert len(positions) == 1
        pos = positions[0]
        assert pos["symbol"] == "BTC-USDT"
        assert pos["positionSide"] == "LONG"
        assert pos["positionAmt"] == 0.01
        assert pos["leverage"] == 10
        assert pos["entryPrice"] == 50000.0
        # 多頭預估強平價應低於開倉價
        assert pos["liquidationPrice"] < 50000.0

    def test_scenario_swap_short_and_liquidation_estimation(self):
        """Scenario: 永續合約 (SWAP) 做空 (SHORT) 與強平價估算."""
        # Given 網關配置為合約市場 "SWAP" 演練模式
        gateway = BingXGateway(dry_run=True, default_market_type=MarketType.SWAP.value)

        # And 設定標的 "BTC/USDT" 之合約槓桿倍數為 20 倍
        gateway.set_leverage("BTC/USDT", 20)

        # When 策略送出開空單賣出 "BTC/USDT" 數量 0.02 顆，價格 60000.0
        resp = gateway.create_order(
            symbol="BTC/USDT",
            side="SELL",
            order_type="LIMIT",
            size=0.02,
            price=60000.0,
            market_type=MarketType.SWAP.value,
            position_side="SHORT",
            leverage=20,
        )

        # Then 網關應產生成交回執且 market_type 為 "SWAP" 且 position_side 為 "SHORT"
        assert resp["result"] is True
        order = resp["data"]
        assert order["market_type"] == "SWAP"
        assert order["positionSide"] == "SHORT"

        # 名義價值: 0.02 * 60000 = 1200 USDT; 槓桿 20x => 保證金 60 USDT
        assert order["marginRequired"] == 60.0

        # And 系統應記錄該空頭倉位並計算出高於開倉價之預估強平價格 (Liquidation Price)
        positions = [p for p in gateway.get_positions("BTC/USDT") if p["positionSide"] == "SHORT"]
        assert len(positions) == 1
        short_pos = positions[0]
        assert short_pos["positionAmt"] == 0.02
        assert short_pos["entryPrice"] == 60000.0
        assert short_pos["leverage"] == 20
        # 空頭預估強平價必定大於開倉價 60000.0
        assert short_pos["liquidationPrice"] > 60000.0
