"""BDD Scenario Implementation Tests: Multi-process Journal Concurrency, Test Isolation & Swap Close Safety."""

import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from packages.journal.manager import TradeJournalManager
from packages.core.autopilot_engine import UnifiedAutopilotEngine
from packages.execution import BingXGateway
from apps.cli.overnight_swap_bot import execute_swap_close, execute_swap_open


class TestMultiprocessAndLifecycleBDDScenarios:
    """BDD Step implementations matching multiprocess_journal_and_swap_lifecycle.feature."""

    def test_scenario_multiprocess_journal_concurrent_merge_no_data_loss(self, tmp_path):
        """Scenario: 多支守護進程並發更新交易日誌時自動合併磁碟狀態絕不遺失紀錄"""
        db_file = tmp_path / "shared_journal_db.json"
        j_dir = tmp_path / "journals"

        # Given 進程 A 與進程 B 分別獨立初始化 TradeJournalManager 並指向同一日誌資料庫
        mgr_proc_a = TradeJournalManager(db_path=str(db_file), journals_dir=str(j_dir))
        mgr_proc_b = TradeJournalManager(db_path=str(db_file), journals_dir=str(j_dir))

        # When 進程 A 開立一筆 3x 合約多單且進程 B 隨後開立一筆 50x 合約多單
        entry_a = mgr_proc_a.on_trade_open(
            symbol="BTC/USDT",
            market_type="SWAP",
            side="LONG",
            entry_price=76500.0,
            amount_btc=0.002,
            margin_used=50.0,
            leverage=3,
            raw_reason="3x 順勢多單",
            custom_id="SWAP_20261104_021851_LONG",
        )
        entry_b = mgr_proc_b.on_trade_open(
            symbol="BTC/USDT",
            market_type="SWAP",
            side="LONG",
            entry_price=76600.0,
            amount_btc=0.032,
            margin_used=50.0,
            leverage=50,
            raw_reason="50x 超賣反彈",
            custom_id="SWAP_20261104_033213_LONG",
        )

        # And 進程 A 觸發 on_trade_update 更新其 3x 部位之盤中最高價軌跡
        mgr_proc_a.on_trade_update(entry_a.journal_id, current_price=77200.0)

        # Then 磁碟資料庫中應同時完整保留進程 A 與進程 B 之兩筆交易日誌
        mgr_reader = TradeJournalManager(db_path=str(db_file), journals_dir=str(j_dir))
        all_ids = {e.journal_id for e in mgr_reader.get_entries()}
        assert entry_a.journal_id in all_ids
        assert entry_b.journal_id in all_ids
        assert len(all_ids) == 2

        # And 進程 B 的交易日誌絕不會被進程 A 的舊記憶體快取覆蓋抹除
        updated_a = mgr_reader.get_entry(entry_a.journal_id)
        assert updated_a is not None
        assert updated_a.trajectory.highest_price == 77200.0

    def test_scenario_same_second_journal_id_collision_prevention(self, tmp_path):
        """Scenario: 同一秒內多支守護進程同時開倉時日誌編號自動防碰撞"""
        db_file = tmp_path / "collision_db.json"
        j_dir = tmp_path / "journals"

        mgr_10x = TradeJournalManager(db_path=str(db_file), journals_dir=str(j_dir))
        mgr_50x = TradeJournalManager(db_path=str(db_file), journals_dir=str(j_dir))

        # When 兩者於同一秒時間戳依序調用 on_trade_open 寫入交易日誌
        e1 = mgr_10x.on_trade_open(
            symbol="BTC/USDT",
            market_type="SWAP",
            side="LONG",
            entry_price=76500.0,
            amount_btc=0.0065,
            margin_used=50.0,
            leverage=10,
            entry_time_str="2026-11-04 03:00:00 UTC",
        )
        e2 = mgr_50x.on_trade_open(
            symbol="BTC/USDT",
            market_type="SWAP",
            side="LONG",
            entry_price=76500.0,
            amount_btc=0.0325,
            margin_used=50.0,
            leverage=50,
            entry_time_str="2026-11-04 03:00:00 UTC",
        )

        # Then 系統產出之兩筆 journal_id 必須唯一且不互相覆蓋
        assert e1.journal_id != e2.journal_id
        mgr_check = TradeJournalManager(db_path=str(db_file), journals_dir=str(j_dir))
        assert len(mgr_check.get_entries()) == 2

    def test_scenario_autopilot_test_directory_journal_isolation(self, tmp_path):
        """Scenario: 自動操盤中樞於臨時測試目錄運行時自動隔離日誌資料庫"""
        prod_db = ROOT_DIR / "data" / "trade_journal_db.json"
        prod_mtime_before = prod_db.stat().st_mtime_ns if prod_db.exists() else None

        # Given 測試程序以臨時目錄之 state_file 初始化 UnifiedAutopilotEngine 且未顯式傳入 journal_mgr
        temp_state = tmp_path / "autopilot_test_state.json"
        engine = UnifiedAutopilotEngine(
            mode="SWAP_3X",
            capital=100.0,
            symbol="BTC/USDT",
            leverage=3,
            state_file=temp_state,
            dry_run=True,
            enable_ai_veto=False,
        )

        # Then 日誌資料庫與 Markdown 覆盤檔案應自動指向該臨時目錄下
        assert engine.journal_mgr.db_path.parent == tmp_path
        assert engine.journal_file.parent == tmp_path

        # And 正式環境之 data/trade_journal_db.json 保持完全不被污染
        if prod_mtime_before is not None:
            assert prod_db.stat().st_mtime_ns == prod_mtime_before

    def test_scenario_swap_bot_close_sends_market_order_and_guards_failure(self, tmp_path, monkeypatch):
        """Scenario: 合約守護進程平倉時必先向交易所發送反向平倉單並驗證結果"""
        import apps.cli.overnight_swap_bot as swap_bot

        temp_db = tmp_path / "bot_journal.json"
        temp_j_dir = tmp_path / "journals"
        temp_state_file = tmp_path / "bingx_swap_test.json"
        monkeypatch.setattr(swap_bot, "STATE_FILE", temp_state_file)
        monkeypatch.setattr(swap_bot, "journal_mgr", TradeJournalManager(db_path=str(temp_db), journals_dir=str(temp_j_dir)))

        # Given 合約守護進程持有一筆 10x LONG 部位（數量 0.0065 BTC）
        state = {
            "initial_capital": 100.0,
            "available_margin": 50.0,
            "market_type": "SWAP",
            "leverage": 10,
            "position": {
                "symbol": "BTC/USDT",
                "side": "LONG",
                "amount_btc": 0.0065,
                "entry_price": 76000.0,
                "margin_used": 50.0,
                "leverage": 10,
                "liquidation_price": 69160.0,
                "entry_time": "2026-11-04 03:00:00 UTC",
                "highest_pnl_pct": 12.0,
                "journal_id": "",
            },
            "history": [],
        }

        # Case 1: Exchange returns failure (result=False) on non-dry-run gateway
        mock_gw_fail = MagicMock(spec=BingXGateway)
        mock_gw_fail.is_dry_run = False
        mock_gw_fail.create_order.return_value = {"result": False, "msg": "Network timeout"}

        # When 交易所網關回傳平倉失敗（result 為 False）
        execute_swap_close(state, price=77000.0, reason="移動停利", gw=mock_gw_fail)

        # Then 本地持倉狀態必須保留不得清空以待下次重試
        mock_gw_fail.create_order.assert_called_once()
        call_kwargs = mock_gw_fail.create_order.call_args.kwargs
        assert call_kwargs["side"] == "SELL"
        assert call_kwargs["order_type"] == "MARKET"
        assert call_kwargs["position_side"] == "LONG"
        assert state["position"]["side"] == "LONG"
        assert state["available_margin"] == 50.0

        # Case 2: Exchange confirms close order succeeded (result=True)
        mock_gw_ok = MagicMock(spec=BingXGateway)
        mock_gw_ok.is_dry_run = False
        mock_gw_ok.create_order.return_value = {"result": True, "data": {"orderId": "12345", "status": "FILLED"}}

        execute_swap_close(state, price=77000.0, reason="移動停利", gw=mock_gw_ok)

        # Then 持倉狀態清空且保證金與實現盈虧回流
        assert state["position"]["side"] == "NONE"
        assert state["available_margin"] > 50.0
        assert len(state["history"]) == 1
