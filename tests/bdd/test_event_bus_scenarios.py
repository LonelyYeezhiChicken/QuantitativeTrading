"""BDD Scenario Implementation Tests: Multi-Exchange MarketEventBus & Hybrid Feed Adapter."""

import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.core.event_bus import (
    MarketEventBus,
    TickerUpdateEvent,
    InMemoryKlineRollingCache,
)
from packages.core.autopilot_engine import UnifiedAutopilotEngine
from packages.execution import BingXGateway, PaperBroker
from packages.execution.market_feed import (
    PollingMarketFeedAdapter,
    HybridWebSocketFeedAdapter,
)
from packages.journal import TradeJournalManager


class TestEventBusAndHybridMarketFeedBDDScenarios:
    """BDD Step implementations matching event_bus_and_hybrid_market_feed.feature."""

    def test_scenario_websocket_push_triggers_instant_trailing_stop_without_polling(self, tmp_path):
        """Scenario: 支援 WebSocket 之交易所透過推播事件即時觸發毫秒級移動停利與硬停損 (零輪詢延遲)."""
        state_file = tmp_path / "autopilot_ws_event.json"
        jm = TradeJournalManager(
            db_path=str(tmp_path / "journal_db.json"),
            journals_dir=str(tmp_path / "journals"),
        )
        bus = MarketEventBus()
        gw = BingXGateway(dry_run=True, default_market_type="SWAP", enable_ws=False)

        engine = UnifiedAutopilotEngine(
            symbol="BTC/USDT",
            leverage=10,
            capital=100.0,
            gateway=gw,
            enable_ai_veto=False,
            dry_run=True,
            state_file=state_file,
            journal_mgr=jm,
            event_bus=bus,
        )
        engine.arm()

        # Given 10 倍槓桿合約持有一筆開倉價為 76000、最高浮盈曾達 +25.0% 的 "LONG" 倉位
        entry_price = 76000.0
        margin = 50.0
        qty = (margin * 10) / entry_price
        engine.cash = 50.0
        gw.create_order(
            symbol="BTC/USDT",
            side="BUY",
            order_type="MARKET",
            size=qty,
            market_type="SWAP",
            position_side="LONG",
            leverage=10,
            stop_loss_price=74860.0,
            simulation_price=entry_price,
        )
        j_entry = jm.on_trade_open(
            symbol="BTC/USDT",
            market_type="SWAP",
            side="LONG",
            entry_price=entry_price,
            amount_btc=qty,
            margin_used=margin,
            leverage=10,
            raw_reason="10x 順勢開多",
            snapshot_dict={"price": entry_price},
            stop_loss_pct=15.0,
            trailing_pullback_pct=5.0,
        )
        engine.position = {
            "side": "LONG",
            "amount": qty,
            "amount_btc": qty,
            "entry_price": entry_price,
            "margin_used": margin,
            "highest_pnl_pct": 25.0,  # Peak was +25.0% ROE (>= +20.0% TP threshold)
            "entry_time": j_entry.entry_time,
            "entry_why": "10x 順勢開多",
            "ai_decision": "EXECUTE",
            "journal_id": j_entry.journal_id,
            "native_sl_price": 76114.0,
            "breakeven_synced": True,
        }

        # And 自動操盤引擎已訂閱 MarketEventBus 且綁定 BingX 混合 WebSocket 資料源
        received_events: list[TickerUpdateEvent] = []
        bus.subscribe(TickerUpdateEvent, lambda ev: received_events.append(ev))
        feed = gw.create_market_feed(bus, symbols=["BTC/USDT"], market_type="SWAP")
        assert isinstance(feed, HybridWebSocketFeedAdapter)

        # When BingX WebSocket 推進一筆最新成交價為 77400 的即時訊息 (+18.42% ROE, 回撤 6.58% >= 5.0%)
        ws_payload = {
            "dataType": "BTC-USDT@lastPrice",
            "data": {"s": "BTC-USDT", "e": "lastPriceUpdate", "c": "77400.0", "E": 1730700000123},
        }
        feed.ingest_ws_payload(ws_payload, market_type="SWAP")

        # Then MarketEventBus 應立即發布來源標記為 "WEBSOCKET" 的 TickerUpdateEvent
        assert len(received_events) == 1
        assert received_events[0].source == "WEBSOCKET"
        assert received_events[0].price == pytest.approx(77400.0)
        assert received_events[0].symbol == "BTC/USDT"

        # And 自動操盤引擎應在不依賴定時輪詢的情況下立即響應事件完成市價移動停利平倉與權威日誌結算
        assert engine.position["side"] == "NONE"
        assert engine.cash > 100.0
        closed_entry = jm.get_entry(j_entry.journal_id)
        assert closed_entry is not None
        assert closed_entry.status == "CLOSED"
        assert closed_entry.pnl_usdt > 0
        assert "移動停利" in closed_entry.review.exit_reason

    def test_scenario_non_ws_exchange_automatically_uses_polling_feed_adapter(self, tmp_path):
        """Scenario: 不支援 WebSocket 之交易所自動透過 PollingMarketFeedAdapter 發送標準事件驅動前端."""
        # Given 交易系統連接一個不支援原生 WebSocket 的經紀商網關 (PaperBroker)
        paper_gw = PaperBroker(initial_balance=1000.0, state_file=str(tmp_path / "paper.json"))
        paper_gw.set_mock_price("BTC/USDT", 77550.0)
        assert paper_gw.supports_websocket is False

        bus = MarketEventBus()
        captured: list[TickerUpdateEvent] = []
        bus.subscribe(TickerUpdateEvent, lambda ev: captured.append(ev))

        # When 呼叫網關的 create_market_feed 工廠方法綁定 MarketEventBus 並執行單次輪詢擷取
        feed = paper_gw.create_market_feed(bus, symbols=["BTC/USDT"], market_type="SPOT", poll_interval_sec=1.0)

        # Then 網關應自動配置 PollingMarketFeedAdapter
        assert isinstance(feed, PollingMarketFeedAdapter)
        feed.poll_once()

        # And EventBus 訂閱者應收到格式完全一致且來源標記為 "POLLING" 的標準 TickerUpdateEvent
        assert len(captured) == 1
        ev = captured[0]
        assert ev.source == "POLLING"
        assert ev.exchange == paper_gw.exchange_name
        assert ev.symbol == "BTC/USDT"
        assert ev.price == pytest.approx(77550.0)

    def test_scenario_websocket_disconnect_auto_fallback_to_polling_and_recovery(self, monkeypatch):
        """Scenario: WebSocket 斷線或推播靜默時自動無縫切換至備援輪詢並在連線恢復後切回推播."""
        bus = MarketEventBus()
        gw = BingXGateway(dry_run=True, default_market_type="SWAP", enable_ws=False)
        monkeypatch.setattr(
            gw,
            "fetch_ticker",
            lambda symbol, market_type="SWAP": {
                "price": 77680.0,
                "bid": 77679.5,
                "ask": 77680.5,
                "timestamp": 1730700005000,
            },
        )

        captured: list[TickerUpdateEvent] = []
        bus.subscribe(TickerUpdateEvent, lambda ev: captured.append(ev))

        # Given BingX 混合資料源適配器處於運行狀態且 WebSocket 突然發生斷線或推播靜默超時
        feed = HybridWebSocketFeedAdapter(
            gateway=gw,
            event_bus=bus,
            symbols=["BTC/USDT"],
            market_type="SWAP",
            stale_timeout_sec=0.0,  # Immediate stale detection for deterministic test
        )

        # When 適配器健康檢查觸發備援機制時
        feed.check_health_and_fallback()

        # Then 系統應自動調用底層 REST fetch_ticker 並向 EventBus 發布來源為 "POLLING_FALLBACK" 的 TickerUpdateEvent
        assert len(captured) == 1
        assert captured[0].source == "POLLING_FALLBACK"
        assert captured[0].price == pytest.approx(77680.0)

        # And 當 WebSocket 重新恢復推播最新價格時應立即切回 "WEBSOCKET" 高速推播模式
        feed.ingest_ws_payload(
            {
                "dataType": "BTC-USDT@lastPrice",
                "data": {"s": "BTC-USDT", "e": "lastPriceUpdate", "c": "77720.0", "E": 1730700006000},
            },
            market_type="SWAP",
        )
        assert len(captured) == 2
        assert captured[1].source == "WEBSOCKET"
        assert captured[1].price == pytest.approx(77720.0)

    def test_scenario_in_memory_kline_rolling_cache_zero_extra_rest_calls(self):
        """Scenario: 記憶體 K 線滾動快取結合即時 Tick 合成實現零額外 REST 請求之結構化指標計算."""
        rest_kline_fetcher = MagicMock(
            return_value={
                "closes": [76000.0 + i * 25.0 for i in range(100)],
                "highs": [76050.0 + i * 25.0 for i in range(100)],
                "lows": [75950.0 + i * 25.0 for i in range(100)],
            }
        )
        cache = InMemoryKlineRollingCache(
            kline_fetcher=rest_kline_fetcher,
            refresh_interval_sec=60.0,
        )

        # Given InMemoryKlineRollingCache 已完成初始 100 根 1 小時 K 線之背景載入 (僅消耗 1 次 REST 請求)
        initial_signals = cache.compute_signals_on_tick("BTC/USDT", "SWAP", price=78475.0)
        assert rest_kline_fetcher.call_count == 1
        assert initial_signals["ema21"] > 0

        # When WebSocket 連續高速推入 20 筆不同價格的 TickerUpdateEvent 時
        latest_signals = initial_signals
        for i in range(1, 21):
            tick_price = 78475.0 + (i * 15.0)
            latest_signals = cache.compute_signals_on_tick(
                "BTC/USDT",
                "SWAP",
                price=tick_price,
                bid=tick_price - 0.5,
                ask=tick_price + 0.5,
            )

        # Then 快取應在記憶體中即時合成更新當根 K 線之收盤價、最高價與最低價並重算 EMA21、RSI 與乖離率
        assert latest_signals["price"] == pytest.approx(78475.0 + 300.0)
        assert latest_signals["ema21"] > initial_signals["ema21"]
        assert "bias_pct" in latest_signals
        assert latest_signals["swing_high_48"] >= latest_signals["price"]

        # And 在快取有效期間內對底層交易所 REST K 線端點的額外呼叫次數必須為 0
        assert rest_kline_fetcher.call_count == 1
