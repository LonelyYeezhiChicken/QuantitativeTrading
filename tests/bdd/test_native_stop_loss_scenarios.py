"""BDD Step Implementation Tests: Native Exchange Stop-Loss & Disconnection Resilience."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import requests

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.execution import BingXClient, BingXGateway, MarketType
from packages.core.autopilot_engine import UnifiedAutopilotEngine, AutopilotState
from packages.journal import TradeJournalManager


class TestNativeStopLossAndDisconnectionBDDScenarios:
    """BDD Step implementations matching native_stop_loss_and_disconnect_resilience.feature."""

    def test_scenario_atomic_native_stop_loss_attached_on_entry(self):
        """Scenario: 合約開倉時原子性附加原生硬停損條件單至交易所."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            state_file = tmp_path / "autopilot_state.json"
            db_file = tmp_path / "trade_journal_db.json"
            journals_dir = tmp_path / "journals"

            jm = TradeJournalManager(db_path=str(db_file), journals_dir=str(journals_dir))

            # Given 交易員武裝操盤引擎且設定槓桿為 3x
            engine = UnifiedAutopilotEngine(
                mode="SWAP_3X",
                capital=100.0,
                leverage=3,
                state_file=state_file,
                journal_mgr=jm,
                dry_run=True,
            )
            engine.arm()
            assert engine.status == AutopilotState.ARMED
            assert engine.leverage == 3

            # When 引擎發出開多 "LONG" 訊號並向交易所提交市價開倉
            entry_price = 77000.0
            margin_used = 50.0
            # 4.0% margin stop loss on 3x leverage corresponds to 4.0 / 3 = 1.333% price distance
            expected_sl_price = round(entry_price * (1.0 - (4.0 / 100.0 / 3)), 2)

            res = engine.gw.create_order(
                symbol="BTC/USDT",
                side="BUY",
                order_type="MARKET",
                size=0.00194,
                market_type="SWAP",
                position_side="LONG",
                leverage=3,
                stop_loss_price=expected_sl_price,
            )

            # Then 訂單記錄必須包含原生硬停損參數 "stopLossPrice"
            assert res.get("result") is True
            data = res.get("data", {})
            assert "stopLossPrice" in data
            assert abs(data["stopLossPrice"] - expected_sl_price) < 0.1

            # And 驗證底層 BingXClient 生成的 HTTP 請求參數包含合規的 STOP_MARKET JSON
            client = BingXClient(api_key="mock_key", api_secret="mock_secret")
            with patch.object(client, "request", return_value={"code": 0, "data": {"orderId": "12345"}}) as mock_req:
                client.create_swap_order(
                    symbol="BTC-USDT",
                    side="BUY",
                    position_side="LONG",
                    order_type="MARKET",
                    quantity=0.00194,
                    stop_loss_price=expected_sl_price,
                )

                call_kwargs = mock_req.call_args[1]
                params = call_kwargs["params"]
                assert "stopLoss" in params
                sl_obj = json.loads(params["stopLoss"])
                assert sl_obj["type"] == "STOP_MARKET"
                assert sl_obj["workingType"] == "MARK_PRICE"
                assert sl_obj["stopPrice"] == expected_sl_price

    def test_scenario_network_disconnect_and_domain_fallback(self):
        """Scenario: 遭遇本機斷網與連線異常時系統具備雙網域自動容災切換."""
        client = BingXClient(api_key="mock_key", api_secret="mock_secret")

        # Given 主網域 open-api.bingx.com 遭遇連線異常 (ConnectionError)
        # When 發送公開行情請求
        # Then 系統應自動容災切換至備援網域 open-api.bingx.pro
        def mock_dispatch(url, **kwargs):
            if "open-api.bingx.com" in url:
                raise requests.exceptions.ConnectionError("Primary domain connection timed out")
            # Fallback domain succeeds
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "code": 0,
                "msg": "success",
                "data": {"symbol": "BTC-USDT", "price": "77500.00", "time": 1700000000000},
            }
            mock_resp.raise_for_status = MagicMock()
            return mock_resp

        with patch.object(client.session, "get", side_effect=mock_dispatch):
            ticker = client.fetch_ticker_price("BTC-USDT")
            assert ticker["code"] == 0
            assert float(ticker["data"]["price"]) == 77500.0

        # And 若雙網域全部斷網，則優雅拋出完整診斷訊息
        with patch.object(client.session, "get", side_effect=requests.exceptions.ConnectionError("No internet")):
            with pytest.raises(RuntimeError, match="All BingX domains failed"):
                client.fetch_ticker_price("BTC-USDT")

    def test_scenario_reconnection_state_reconciliation(self):
        """Scenario: 網路恢復後自動狀態對齊與日誌結算 (斷網保底對齊)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            state_file = tmp_path / "autopilot_state.json"
            db_file = tmp_path / "trade_journal_db.json"
            journals_dir = tmp_path / "journals"

            jm = TradeJournalManager(db_path=str(db_file), journals_dir=str(journals_dir))

            engine = UnifiedAutopilotEngine(
                mode="SWAP_3X",
                capital=100.0,
                leverage=3,
                state_file=state_file,
                journal_mgr=jm,
                dry_run=False,  # Test real reconciliation flow
            )

            # Given 引擎本機持倉記錄為 "OPEN"
            entry = jm.on_trade_open(
                symbol="BTC/USDT",
                market_type="SWAP",
                side="LONG",
                entry_price=77000.0,
                amount_btc=0.00194,
                margin_used=50.0,
                leverage=3,
                raw_reason="均線多頭確認",
            )
            journal_id = entry.journal_id
            engine.position = {
                "side": "LONG",
                "amount_btc": 0.00194,
                "entry_price": 77000.0,
                "margin_used": 50.0,
                "highest_pnl_pct": 1.0,
                "entry_time": entry.entry_time,
                "entry_why": "均線多頭確認",
                "ai_decision": "AI 核准進場",
                "journal_id": journal_id,
            }

            # When 本機恢復連線且查詢交易所發現部位已歸零 (active_exchange_positions = [])
            # (代表在斷網期間，交易所的原生硬停損條件單已在雲端成功平倉)
            reconciled = engine.reconcile_with_exchange(active_exchange_positions=[])

            # Then 引擎應立即感知交易所部位已歸零並完成對齊
            assert reconciled is True
            assert engine.position["side"] == "NONE"

            # And 權威交易日誌自動更新為 CLOSED 並註明原生停損生效
            closed_entry = jm.get_entry(journal_id)
            assert closed_entry.status == "CLOSED"
            assert "交易所原生硬停損觸發平倉" in closed_entry.review.exit_reason

    def test_scenario_clean_cancellation_on_trailing_close(self):
        """Scenario: 本機動態移動停利平倉時自動撤銷交易所遺留之硬停損掛單."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            state_file = tmp_path / "autopilot_state.json"
            db_file = tmp_path / "trade_journal_db.json"
            journals_dir = tmp_path / "journals"

            jm = TradeJournalManager(db_path=str(db_file), journals_dir=str(journals_dir))

            engine = UnifiedAutopilotEngine(
                mode="SWAP_3X",
                capital=100.0,
                leverage=3,
                state_file=state_file,
                journal_mgr=jm,
                dry_run=True,
            )

            # Given 引擎持有獲利倉位且在交易所存在模擬掛單
            engine.gw.create_order(
                symbol="BTC/USDT",
                side="BUY",
                order_type="MARKET",
                size=0.00194,
                market_type="SWAP",
                position_side="LONG",
                leverage=3,
                stop_loss_price=76000.0,
                simulation_price=77000.0,
            )
            # Add a pending mock conditional order
            engine.gw._simulated_orders.append({
                "orderId": "COND_SL_999",
                "symbol": "BTC-USDT",
                "status": "PENDING",
            })

            engine.position = {
                "side": "LONG",
                "amount_btc": 0.00194,
                "entry_price": 77000.0,
                "margin_used": 50.0,
                "highest_pnl_pct": 5.0,
                "entry_time": "2026-11-04 00:00:00 UTC",
                "entry_why": "動能突破",
                "ai_decision": "AI 核准",
                "journal_id": "",
            }

            # When 本機執行平倉 (例如移動停利觸發)
            engine._close_position(exit_price=78500.0, reason="動態移動停利鎖定利潤")

            # Then 系統應自動取消所有未成交的條件單
            pending_orders = [o for o in engine.gw._simulated_orders if o.get("status") in ["PENDING", "NEW"]]
            assert len(pending_orders) == 0, "平倉後交易所遺留之條件單必須全部被取消"
            assert engine.position["side"] == "NONE"

    def test_scenario_restart_requires_manual_rearm_and_keeps_position(self):
        """A persisted ARMED state must never auto-arm a restarted process."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            state_file = tmp_path / "autopilot_state.json"
            jm = TradeJournalManager(db_path=str(tmp_path / "journal.json"), journals_dir=str(tmp_path / "journals"))
            engine = UnifiedAutopilotEngine(
                mode="SWAP_3X", capital=100.0, state_file=state_file, journal_mgr=jm, dry_run=True,
            )
            engine.arm()
            engine.position = {
                "side": "LONG", "amount_btc": 0.01, "entry_price": 100.0,
                "margin_used": 1.0, "highest_pnl_pct": 0.0, "journal_id": "",
            }
            engine.save_state()

            restarted = UnifiedAutopilotEngine(
                mode="SWAP_3X", capital=100.0, state_file=state_file, journal_mgr=jm, dry_run=True,
            )
            assert restarted.status == AutopilotState.STANDBY
            assert restarted.position["side"] == "LONG"
            assert restarted.position["amount_btc"] == pytest.approx(0.01)

    def test_scenario_position_query_error_is_not_treated_as_flat(self):
        """An unavailable exchange position endpoint must not close local state."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            jm = TradeJournalManager(db_path=str(tmp_path / "journal.json"), journals_dir=str(tmp_path / "journals"))
            engine = UnifiedAutopilotEngine(
                mode="SWAP_3X", capital=100.0, state_file=tmp_path / "state.json",
                journal_mgr=jm, dry_run=False,
            )
            entry = jm.on_trade_open(
                symbol="BTC/USDT", market_type="SWAP", side="LONG", entry_price=100.0,
                amount_btc=0.01, margin_used=1.0, leverage=3, raw_reason="BDD 對帳測試",
            )
            engine.position = {
                "side": "LONG", "amount_btc": 0.01, "entry_price": 100.0,
                "margin_used": 1.0, "highest_pnl_pct": 0.0, "journal_id": entry.journal_id,
            }
            with patch.object(engine.gw.client, "get_swap_positions", side_effect=RuntimeError("Endpoint unavailable")):
                result = engine.reconcile_with_exchange()
                assert result is None
            assert engine.position["side"] == "LONG"
            assert jm.get_entry(entry.journal_id).status == "OPEN"

    def test_scenario_live_success_response_without_result_is_normalized(self):
        """BingX's code/data response is normalized and its fill details retained."""
        engine = UnifiedAutopilotEngine(mode="SWAP_3X", dry_run=False)
        with patch.object(
            engine.gw.client,
            "create_swap_order",
            return_value={
                "code": 0,
                "data": {"orderId": "live-123", "status": "FILLED", "executedQty": "0.01", "avgPrice": "100"},
            },
        ):
            response = engine.gw.create_order(
                symbol="BTC/USDT", side="BUY", order_type="MARKET", size=0.01,
                market_type="SWAP", position_side="LONG", leverage=3,
            )
        assert response["result"] is True
        assert response["data"]["orderId"] == "live-123"
        assert engine._confirm_market_fill(response, 0.01, "SWAP") == (True, 0.01, 100.0, "FILLED")

    def test_scenario_failed_close_keeps_open_position_and_disk_journal(self):
        """A rejected close must not be written as a completed trade."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            jm = TradeJournalManager(db_path=str(tmp_path / "journal.json"), journals_dir=str(tmp_path / "journals"))
            engine = UnifiedAutopilotEngine(
                mode="SWAP_3X", capital=100.0, state_file=tmp_path / "state.json",
                journal_mgr=jm, dry_run=True,
            )
            entry = jm.on_trade_open(
                symbol="BTC/USDT", market_type="SWAP", side="LONG", entry_price=100.0,
                amount_btc=0.01, margin_used=1.0, leverage=3, raw_reason="BDD 平倉失敗測試",
            )
            engine.position = {
                "side": "LONG", "amount_btc": 0.01, "entry_price": 100.0,
                "margin_used": 1.0, "highest_pnl_pct": 0.0, "journal_id": entry.journal_id,
            }
            engine.save_state()

            assert engine._close_position(110.0, "測試平倉") is False
            assert engine.position["side"] == "LONG"
            assert jm.get_entry(entry.journal_id).status == "OPEN"
            restarted = UnifiedAutopilotEngine(
                mode="SWAP_3X", capital=100.0, state_file=tmp_path / "state.json",
                journal_mgr=jm, dry_run=True,
            )
            assert restarted.position["side"] == "LONG"
